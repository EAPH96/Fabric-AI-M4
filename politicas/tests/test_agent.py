"""Pruebas del agente de Políticas con un modelo de guion y el catálogo real.

El bucle es el del HR; aquí se prueban las dos herramientas nuevas, sus avisos
y el tope de pasos.
"""

import json

from app.agent import Agent
from app.llm import Completion

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."
TOOL_PREFIX = "Resultado de la herramienta: "


def tool(name, **args):
    """Texto del modelo que pide la herramienta ``name`` con ``args``."""
    return json.dumps({"tool": name, "args": args})


def answer(text):
    """Texto del modelo que responde con ``text``."""
    return json.dumps({"answer": text})


class ScriptedModel:  # pylint: disable=too-few-public-methods
    """Modelo de prueba: devuelve respuestas fijas y guarda lo que recibe.

    Cuando se acaban las respuestas repite la última.

    :param replies: Textos que devuelve, en orden
    :type replies: list[str]
    """

    def __init__(self, replies):
        self._replies = list(replies)
        self.received = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta del guion con tokens fijos.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :return: Respuesta del guion
        :rtype: Completion
        """
        self.received.append([dict(message) for message in messages])
        index = min(len(self.received), len(self._replies)) - 1
        return Completion(text=self._replies[index], input_tokens=10, output_tokens=4)

    def tool_results(self):
        """Resultados de herramienta que recibió el modelo, sin el prefijo.

        :return: Un texto por cada vuelta después de la primera
        :rtype: list[str]
        """
        return [
            messages[-1]["content"].removeprefix(TOOL_PREFIX)
            for messages in self.received[1:]
        ]


def run_agent(model, catalog, max_steps=3):
    """Corre un agente nuevo sin historial."""
    agent = Agent(model=model, catalog=catalog, max_steps=max_steps)
    return agent.run("¿Qué dice la política?", [])


def test_search_policies_returns_json_with_id_and_title(catalog):
    model = ScriptedModel([tool("search_policies", topic="aguinaldo"), answer("Ok")])

    result = run_agent(model, catalog)

    assert result.tools_used == ["search_policies"]
    (found,) = model.tool_results()
    assert json.loads(found) == [{"id": "POL-003", "title": "Aguinaldo"}]


def test_unknown_policy_and_unknown_topic_are_reported_to_the_model(catalog):
    model = ScriptedModel(
        [
            tool("get_policy", policy_id="POL-999"),
            tool("search_policies", topic="astronautas"),
            answer("Ok"),
        ]
    )

    result = run_agent(model, catalog)

    assert result.answer == "Ok"
    assert model.tool_results() == [
        "Policy POL-999 not found",
        "No policies found for topic astronautas",
    ]


def test_arguments_that_are_not_text_are_rejected_and_not_counted(catalog):
    model = ScriptedModel(
        [
            tool("get_policy", policy_id=3),
            tool("search_policies", topic=["aguinaldo"]),
            answer("Ok"),
        ]
    )

    result = run_agent(model, catalog)

    assert not result.tools_used
    assert all(text.startswith("Invalid arguments") for text in model.tool_results())


def test_model_that_always_asks_for_a_tool_hits_the_step_cap(catalog):
    model = ScriptedModel([tool("get_policy", policy_id="POL-001")])

    result = run_agent(model, catalog, max_steps=2)

    assert result.answer == CAP_MESSAGE
    assert result.steps == 2
    assert result.stopped is True
