"""Pruebas del bucle con tope del agente, con un modelo de prueba a medida."""

import json

from app.agent import Agent
from app.llm import Completion

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."
TOOL_PREFIX = "Resultado de la herramienta: "
ASK_FOR_JORGE = json.dumps(
    {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}
)


def answer(text):
    """Texto del modelo que responde con ``text``."""
    return json.dumps({"answer": text})


class ScriptedModel:
    """Modelo de prueba: devuelve respuestas fijas y guarda lo que recibe.

    Cuando se acaban las respuestas repite la última. Cada llamada cuenta
    10 tokens de entrada y 4 de salida.

    :param replies: Textos que devuelve, en orden
    :type replies: list[str]
    """

    def __init__(self, replies):
        self._replies = list(replies)
        self.received = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta del guion.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :return: Respuesta del guion con tokens fijos
        :rtype: Completion
        """
        self.received.append([dict(message) for message in messages])
        index = min(len(self.received), len(self._replies)) - 1
        return Completion(text=self._replies[index], input_tokens=10, output_tokens=4)


class RecordingObserver:
    """Observador de prueba: anota qué se envuelve y cada herramienta avisada.

    ``wrap`` devuelve la misma función, como hace el tracer apagado.
    """

    def __init__(self):
        self.run_types = []
        self.tool_calls = []

    def wrap(self, function, run_type):
        """Anota el tipo de traza y devuelve la función sin cambios.

        :param function: Función que el agente quiere trazar
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza: ``llm`` o ``tool``
        :type run_type: str
        :return: La misma función
        :rtype: collections.abc.Callable
        """
        self.run_types.append(run_type)
        return function

    def tool_called(self, name, args):
        """Anota una herramienta ejecutada y sus argumentos.

        :param name: Nombre de la herramienta
        :type name: str
        :param args: Argumentos con los que se ejecutó
        :type args: dict
        """
        self.tool_calls.append((name, args))


def run_agent(model, directory, question="¿Quién es EMP-0004?", max_steps=3):
    """Corre un agente nuevo sin historial."""
    agent = Agent(model=model, directory=directory, max_steps=max_steps)
    return agent.run(question, [])


def test_tokens_are_summed_across_steps(directory):
    model = ScriptedModel([ASK_FOR_JORGE, answer("Listo")])

    result = run_agent(model, directory)

    assert result.answer == "Listo"
    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    assert (result.input_tokens, result.output_tokens) == (20, 8)


def test_unknown_tool_does_not_break_the_loop(directory):
    unknown_tool = json.dumps({"tool": "delete_employee", "args": {}})
    model = ScriptedModel([unknown_tool, answer("Sigo aquí")])

    result = run_agent(model, directory)

    assert result.answer == "Sigo aquí"
    assert result.steps == 2
    assert "delete_employee" not in result.tools_used
    assert model.received[1][-1]["content"].startswith(TOOL_PREFIX)


def test_model_that_always_asks_for_a_tool_hits_the_step_cap(directory):
    model = ScriptedModel([ASK_FOR_JORGE])

    result = run_agent(model, directory, max_steps=3)

    assert result.answer == CAP_MESSAGE
    assert result.steps == 3
    assert result.tools_used == ["get_employee"] * 3
    assert len(model.received) == 3


def test_output_that_is_not_json_ends_with_the_cap_message(directory):
    model = ScriptedModel(["lo siento, no entiendo"])

    result = run_agent(model, directory)

    assert result.answer == CAP_MESSAGE
    assert result.steps == 1
    assert isinstance(result.tools_used, list)
    assert not result.tools_used


def test_agent_reports_stopped_only_when_it_has_no_answer(directory):
    capped = run_agent(ScriptedModel([ASK_FOR_JORGE]), directory, max_steps=1)
    answered = run_agent(ScriptedModel([answer("Listo")]), directory)

    assert capped.stopped is True
    assert answered.stopped is False


def test_observer_is_told_about_each_executed_tool_with_its_args(directory):
    unknown_tool = json.dumps({"tool": "delete_employee", "args": {}})
    model = ScriptedModel([ASK_FOR_JORGE, unknown_tool, answer("Listo")])
    observer = RecordingObserver()
    agent = Agent(model=model, directory=directory, max_steps=3, observer=observer)

    result = agent.run("¿Quién es EMP-0004?", [])

    assert result.answer == "Listo"
    assert observer.tool_calls == [("get_employee", {"employee_id": "EMP-0004"})]
    assert {"llm", "tool"} <= set(observer.run_types)
