"""Pruebas de la validación de citas de Políticas (spec 09, punto 3).

Solo se cita una política que devolvió una herramienta en la misma petición.
El agente anota esos id en ``policy_ids`` a partir del catálogo, no del texto
del resultado: un «not found» no cuenta como devuelto.
"""

import json

from app.agent import Agent
from app.citations import check_citations
from app.llm import Completion

NOT_FOUND_TEXT = (
    "No encontré esa información en las políticas. Pregunta por una política "
    "(POL-001) o un tema, como vacaciones."
)


def tool(name, **args):
    """Texto del modelo que pide la herramienta ``name`` con ``args``."""
    return json.dumps({"tool": name, "args": args})


def answer(text):
    """Texto del modelo que responde con ``text``."""
    return json.dumps({"answer": text})


class ScriptedModel:  # pylint: disable=too-few-public-methods
    """Modelo de prueba: devuelve sus respuestas en orden.

    :param replies: Textos que devuelve, uno por llamada
    :type replies: list[str]
    """

    def __init__(self, replies):
        self._replies = iter(replies)

    def complete(self, messages):  # pylint: disable=unused-argument
        """Devuelve la siguiente respuesta del guion con tokens fijos.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :return: Respuesta del guion
        :rtype: Completion
        """
        return Completion(text=next(self._replies), input_tokens=10, output_tokens=4)


def run_agent(catalog, replies):
    """Corre un agente nuevo sin historial con el guion dado."""
    agent = Agent(model=ScriptedModel(replies), catalog=catalog, max_steps=3)
    return agent.run("¿Qué dice la política?", [])


def test_a_citation_no_tool_returned_replaces_the_whole_answer():
    text = "Según la POL-001 tienes 12 días y según la POL-002 una prima."

    assert check_citations(text, ("POL-001",)) == NOT_FOUND_TEXT


def test_citations_returned_by_a_tool_keep_the_answer():
    text = "Según la POL-001 tienes 12 días y según la POL-002 una prima."

    assert check_citations(text, ("POL-001", "POL-002")) == text


def test_an_answer_without_citations_is_unchanged():
    text = "Solo respondo preguntas sobre las políticas de RH."

    assert check_citations(text, ()) == text


def test_an_id_with_four_digits_is_not_a_citation():
    text = "El folio POL-0001 no es una política."

    assert check_citations(text, ()) == text


def test_the_agent_records_the_policies_returned_by_both_tools(catalog):
    replies = [
        tool("search_policies", topic="aguinaldo"),
        tool("get_policy", policy_id="POL-005"),
        answer("Ok"),
    ]

    result = run_agent(catalog, replies)

    assert set(result.policy_ids) == {"POL-003", "POL-005"}


def test_a_policy_or_topic_that_was_not_found_is_not_recorded(catalog):
    replies = [
        tool("get_policy", policy_id="POL-999"),
        tool("search_policies", topic="astronautas"),
        answer("Ok"),
    ]

    result = run_agent(catalog, replies)

    assert result.tools_used == ["get_policy", "search_policies"]
    assert not result.policy_ids
