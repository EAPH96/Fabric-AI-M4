"""Pruebas del modelo simulado (``MODEL_PROVIDER=fake``) de Políticas.

El modelo recibe los términos del catálogo real (``catalog.terms()``) y aplica
las cuatro reglas de la especificación 06, en orden, sobre el último mensaje.
La regla 4 (la ayuda) se prueba de punta a punta en ``features/policies.feature``.
"""

import json

from app.llm import FakeModel

TOOL_PREFIX = "Resultado de la herramienta: "


def user(content):
    """Mensaje de la persona."""
    return {"role": "user", "content": content}


def decide(catalog, *messages):
    """Pide al modelo simulado el siguiente paso y lo devuelve decodificado."""
    completion = FakeModel(catalog.terms()).complete(list(messages))
    return json.loads(completion.text)


def test_tool_result_is_answered_citing_the_policies(catalog):
    result = '[{"id": "POL-001", "title": "Vacaciones"}]'

    reply = decide(
        catalog,
        user("¿Cuántos días de vacaciones me tocan?"),
        {"role": "assistant", "content": '{"tool": "search_policies"}'},
        user(TOOL_PREFIX + result),
    )

    assert reply == {"answer": "Según las políticas: " + result}


def test_policy_id_wins_over_a_topic_in_the_same_message(catalog):
    reply = decide(catalog, user("¿La POL-003 habla de vacaciones?"))

    assert reply == {"tool": "get_policy", "args": {"policy_id": "POL-003"}}


def test_topic_without_accents_asks_for_the_term_as_written_in_the_file(catalog):
    reply = decide(catalog, user("¿Cómo compruebo mis viaticos?"))

    assert reply == {"tool": "search_policies", "args": {"topic": "viáticos"}}


def test_prima_vacacional_is_not_taken_as_vacaciones(catalog):
    reply = decide(catalog, user("¿Cuándo pagan la prima vacacional?"))

    assert reply == {"tool": "search_policies", "args": {"topic": "prima vacacional"}}
