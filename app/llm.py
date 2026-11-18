"""Interfaz del modelo de lenguaje, modelo simulado y fábrica de modelos.

El agente solo conoce ``ChatModel.complete(messages)``. El modelo responde
siempre un único objeto JSON: ``{"tool": ..., "args": {...}}`` para pedir una
herramienta o ``{"answer": ...}`` para responder.

``build_models`` crea un modelo por nombre (``MODEL_SMALL`` y ``MODEL_LARGE``),
simulado o real, para que el enrutador elija por nombre en los dos casos.
"""

import json
import re
from typing import Protocol

from app.config import FAKE_PROVIDER, GATEWAY_PROVIDER, ConfigError
from app.gateway import GatewayModel, build_http_client
from app.protocol import TOOL_RESULT_PREFIX, Completion

__all__ = [
    "ChatModel",
    "Completion",
    "FakeModel",
    "TOOL_RESULT_PREFIX",
    "build_models",
    "count_words",
]

DIRECTORY_ANSWER_PREFIX = "Según el directorio: "
HELP_ANSWER = "Pregúntame por un empleado (EMP-0001) o un departamento."
EMPLOYEE_ID_PATTERN = re.compile(r"EMP-[0-9]{4}")
FAKE_MODEL_NAME = "fake"


class ChatModel(Protocol):  # pylint: disable=too-few-public-methods
    """Interfaz que debe cumplir cualquier modelo que use el agente."""

    def complete(self, messages: list[dict]) -> Completion:
        """Pide al modelo el siguiente paso de la conversación.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Texto del modelo y tokens usados
        :rtype: Completion
        """


def count_words(text):
    """Cuenta palabras separadas por espacios, como aproximación de tokens.

    :param text: Texto a contar
    :type text: str
    :return: Número de palabras
    :rtype: int
    """
    return len(str(text).split())


class FakeModel:  # pylint: disable=too-few-public-methods
    """Modelo simulado: decide con reglas fijas sobre el último mensaje.

    Las reglas se evalúan en orden estricto: resultado de herramienta, id de
    empleado, departamento conocido y, si nada aplica, la ayuda. El nombre no
    cambia las respuestas: solo sirve para buscar su precio.

    :param departments: Departamentos que existen en los datos
    :type departments: list[str]
    :param name: Nombre del modelo simulado
    :type name: str
    """

    def __init__(self, departments, name=FAKE_MODEL_NAME):
        self._departments = tuple(departments)
        self.name = name

    def complete(self, messages):
        """Responde según las reglas de la especificación.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Objeto JSON con ``tool`` o ``answer`` y el conteo de tokens
        :rtype: Completion
        """
        last = str(messages[-1]["content"]) if messages else ""
        text = json.dumps(self._decide(last), ensure_ascii=False)
        input_tokens = sum(count_words(message["content"]) for message in messages)
        return Completion(
            text=text, input_tokens=input_tokens, output_tokens=count_words(text)
        )

    def _decide(self, last):
        """Aplica las cuatro reglas al último mensaje.

        :param last: Contenido del último mensaje
        :type last: str
        :return: Petición de herramienta o respuesta
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            result = last[len(TOOL_RESULT_PREFIX):]
            return {"answer": DIRECTORY_ANSWER_PREFIX + result}
        match = EMPLOYEE_ID_PATTERN.search(last)
        if match:
            return {"tool": "get_employee", "args": {"employee_id": match.group()}}
        department = self._find_department(last)
        if department:
            args = {"department": department}
            return {"tool": "search_by_department", "args": args}
        return {"answer": HELP_ANSWER}

    def _find_department(self, text):
        """Busca un departamento mencionado en el texto, sin distinguir mayúsculas.

        :param text: Texto donde buscar
        :type text: str
        :return: Nombre del departamento o ``None``
        :rtype: str or None
        """
        folded = text.casefold()
        for department in self._departments:
            if department.casefold() in folded:
                return department
        return None


def build_models(settings, directory, http_client=None):
    """Construye un modelo por cada nombre de ``MODEL_SMALL`` y ``MODEL_LARGE``.

    Con ``fake`` son dos modelos simulados que responden igual; con
    ``gateway`` son dos ``GatewayModel`` que comparten el cliente HTTP.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param directory: Directorio de empleados (da la lista de departamentos)
    :type directory: app.directory.EmployeeDirectory
    :param http_client: Cliente HTTP para el gateway; si es ``None`` se crea
        uno con ``build_http_client``. El modelo simulado no lo usa.
    :type http_client: httpx.Client or None
    :return: Modelos por nombre
    :rtype: dict[str, ChatModel]
    :raises ConfigError: Si el proveedor no está soportado
    """
    routing = settings.costs.routing
    names = (routing.model_small, routing.model_large)
    if settings.model_provider == FAKE_PROVIDER:
        departments = directory.departments()
        return {name: FakeModel(departments, name) for name in names}
    if settings.model_provider == GATEWAY_PROVIDER:
        client = build_http_client() if http_client is None else http_client
        return {name: GatewayModel(name, settings.costs, client) for name in names}
    raise ConfigError(
        f"MODEL_PROVIDER {settings.model_provider!r} is not supported"
    )
