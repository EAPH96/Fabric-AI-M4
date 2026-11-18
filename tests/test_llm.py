"""Pruebas del modelo simulado (``MODEL_PROVIDER=fake``).

Las reglas que no se prueban aquí (pedir ``get_employee`` y la ayuda) se cubren
de punta a punta en ``features/ask.feature``.
"""

import json

from app.config import load_settings
from app.llm import FakeModel, build_models

DEPARTMENTS = ["Tecnología", "Ventas", "Finanzas"]
TOOL_PREFIX = "Resultado de la herramienta: "


def user(content):
    """Mensaje de la persona."""
    return {"role": "user", "content": content}


def test_tool_result_is_answered_even_if_it_mentions_an_employee_id():
    result = '{"id": "EMP-0004", "name": "Jorge Díaz"}'
    messages = [
        user("¿Quién es EMP-0004?"),
        {"role": "assistant", "content": '{"tool": "get_employee"}'},
        user(TOOL_PREFIX + result),
    ]

    completion = FakeModel(DEPARTMENTS).complete(messages)

    assert json.loads(completion.text) == {"answer": "Según el directorio: " + result}


def test_department_mention_asks_for_search_by_department_ignoring_case():
    completion = FakeModel(DEPARTMENTS).complete([user("¿quiénes están en finanzas?")])

    request = json.loads(completion.text)
    assert request["tool"] == "search_by_department"
    assert request["args"]["department"].casefold() == "finanzas"


def test_tokens_are_counted_as_words():
    messages = [
        user("Hola equipo"),
        {"role": "assistant", "content": "Hola"},
        user("¿Quién es EMP-0001?"),
    ]

    completion = FakeModel(DEPARTMENTS).complete(messages)

    assert completion.input_tokens == 6
    assert completion.output_tokens == len(completion.text.split())


def test_both_fake_models_are_named_after_the_settings_and_answer_the_same(
    directory,
):
    settings = load_settings({"MODEL_SMALL": "tiny-model", "MODEL_LARGE": "huge-model"})
    messages = [user("¿Quién es EMP-0004?")]

    models = build_models(settings, directory)

    assert set(models) == {"tiny-model", "huge-model"}
    assert models["tiny-model"].name == "tiny-model"
    assert models["huge-model"].name == "huge-model"
    small, large = models["tiny-model"], models["huge-model"]
    assert small.complete(messages) == large.complete(messages)
