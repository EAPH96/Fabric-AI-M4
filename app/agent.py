"""Agente único con bucle con tope y herramientas de solo lectura.

En cada vuelta el modelo pide una herramienta o responde. Los errores de
herramienta vuelven al modelo como texto; una salida que no es JSON válido o
que no trae ``answer`` ni ``tool`` termina con el mensaje de tope.

El agente no conoce el log ni LangSmith: recibe un observador opcional que
envuelve el modelo y las herramientas (trazas) y recibe un aviso por cada
herramienta ejecutada (auditoría).
"""

import json
from dataclasses import dataclass, field

from app.llm import TOOL_RESULT_PREFIX

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."


@dataclass(frozen=True)
class AgentResult:
    """Resultado de una pregunta al agente.

    :param answer: Respuesta final para la persona
    :type answer: str
    :param steps: Número de llamadas al modelo
    :type steps: int
    :param tools_used: Herramientas ejecutadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Suma de tokens de entrada de todas las vueltas
    :type input_tokens: int
    :param output_tokens: Suma de tokens de salida de todas las vueltas
    :type output_tokens: int
    :param stopped: ``True`` si terminó sin respuesta del modelo (tope agotado
        o salida inválida)
    :type stopped: bool
    """

    answer: str
    steps: int
    tools_used: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: bool = False


class ToolError(Exception):
    """Error al ejecutar una herramienta; su mensaje vuelve al modelo."""


class SilentObserver:
    """Observador que no hace nada: el agente funciona igual sin observar."""

    def wrap(self, function, run_type):  # pylint: disable=unused-argument
        """Devuelve la misma función, sin trazar.

        :param function: Función a envolver
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza (``llm`` o ``tool``)
        :type run_type: str
        :return: La misma función
        :rtype: collections.abc.Callable
        """
        return function

    def tool_called(self, name, args):
        """Ignora el aviso de una herramienta ejecutada.

        :param name: Nombre de la herramienta
        :type name: str
        :param args: Argumentos con los que se ejecutó
        :type args: dict
        """


class Agent:  # pylint: disable=too-few-public-methods
    """Agente que responde preguntas usando el directorio de empleados.

    Se crea uno por petición: no guarda nada entre preguntas.

    :param model: Modelo que cumple ``complete(messages)``
    :type model: app.llm.ChatModel
    :param directory: Directorio de empleados de solo lectura
    :type directory: app.directory.EmployeeDirectory
    :param max_steps: Tope de llamadas al modelo
    :type max_steps: int
    :param observer: Observador con ``wrap(function, run_type)`` y
        ``tool_called(name, args)``; si es ``None`` no se observa nada
    :type observer: app.observability.RequestObserver or None
    """

    def __init__(self, model, directory, max_steps, observer=None):
        self._observer = SilentObserver() if observer is None else observer
        self._complete = self._observer.wrap(model.complete, run_type="llm")
        self._directory = directory
        self._max_steps = max_steps
        self._tools = {
            "get_employee": self._observer.wrap(
                self._get_employee, run_type="tool"
            ),
            "search_by_department": self._observer.wrap(
                self._search_by_department, run_type="tool"
            ),
        }

    def run(self, question, history):
        """Responde una pregunta con el historial que manda el cliente.

        :param question: Pregunta de la persona
        :type question: str
        :param history: Mensajes previos con ``role`` y ``content``
        :type history: list[dict]
        :return: Respuesta, pasos, herramientas usadas, tokens y si se detuvo
        :rtype: AgentResult
        """
        messages = [
            {"role": message["role"], "content": message["content"]}
            for message in history
        ]
        messages.append({"role": "user", "content": question})
        tools_used = []
        steps = input_tokens = output_tokens = 0
        answer = None
        while steps < self._max_steps:
            completion = self._complete(messages)
            steps += 1
            input_tokens += completion.input_tokens
            output_tokens += completion.output_tokens
            reply = _parse(completion.text)
            if reply is None:
                break
            if "answer" in reply:
                answer = reply["answer"]
                break
            result = self._call_tool(reply["tool"], reply.get("args"), tools_used)
            messages.append({"role": "assistant", "content": completion.text})
            messages.append({"role": "user", "content": TOOL_RESULT_PREFIX + result})
        return AgentResult(
            answer=CAP_MESSAGE if answer is None else answer,
            steps=steps,
            tools_used=tools_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stopped=answer is None,
        )

    def _call_tool(self, name, args, tools_used):
        """Ejecuta una herramienta del registro y devuelve su resultado como texto.

        Solo se anota en ``tools_used`` y se avisa al observador si la
        herramienta se ejecutó.

        :param name: Nombre de la herramienta
        :type name: str
        :param args: Argumentos pedidos por el modelo
        :type args: dict or None
        :param tools_used: Lista donde se anotan las herramientas ejecutadas
        :type tools_used: list[str]
        :return: Resultado o mensaje de error para el modelo
        :rtype: str
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown tool {name!r}. Available: {', '.join(self._tools)}"
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return f"Invalid arguments for tool {name!r}: args must be an object"
        try:
            result = tool(**args)
        except (TypeError, ToolError) as error:
            return f"Invalid arguments for tool {name!r}: {error}"
        tools_used.append(name)
        self._observer.tool_called(name, args)
        return result

    def _get_employee(self, employee_id):
        """Herramienta ``get_employee``: un empleado por id.

        :param employee_id: Id del empleado, por ejemplo ``EMP-0004``
        :type employee_id: str
        :return: Empleado en JSON o un aviso de que no existe
        :rtype: str
        :raises ToolError: Si el id no es texto
        """
        if not isinstance(employee_id, str):
            raise ToolError("employee_id must be a string")
        employee = self._directory.get_employee(employee_id)
        if employee is None:
            return f"Employee {employee_id} not found"
        return json.dumps(employee, ensure_ascii=False)

    def _search_by_department(self, department):
        """Herramienta ``search_by_department``: los empleados de un departamento.

        :param department: Nombre del departamento
        :type department: str
        :return: Lista de empleados en JSON o un aviso si no hay ninguno
        :rtype: str
        :raises ToolError: Si el departamento no es texto
        """
        if not isinstance(department, str):
            raise ToolError("department must be a string")
        employees = self._directory.search_by_department(department)
        if not employees:
            return f"No employees found in department {department}"
        return json.dumps(employees, ensure_ascii=False)


def recent_history(history, window):
    """Palanca 2: deja solo los últimos ``window`` mensajes del historial.

    Recorta solo el historial que manda el cliente, nunca los mensajes de
    herramienta del bucle actual. Con ``window`` igual a 0 no se manda nada
    (``history[-0:]`` devolvería todo, por eso se trata aparte).

    :param history: Mensajes previos con ``role`` y ``content``
    :type history: list[dict]
    :param window: Número de mensajes que se conservan (0 o más)
    :type window: int
    :return: Lista nueva con los últimos mensajes; el original no cambia
    :rtype: list[dict]
    """
    if window <= 0:
        return []
    return list(history[-window:])


def _parse(text):
    """Interpreta el texto del modelo según el protocolo.

    :param text: Texto devuelto por el modelo
    :type text: str
    :return: ``{"answer": str}``, ``{"tool": str, "args": ...}`` o ``None`` si el
        texto no cumple el protocolo
    :rtype: dict or None
    """
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("answer"), str):
        return {"answer": data["answer"]}
    if isinstance(data.get("tool"), str):
        return {"tool": data["tool"], "args": data.get("args")}
    return None
