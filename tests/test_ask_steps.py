"""Pasos de los escenarios de ``features/ask.feature``.

Cada escenario arma su propia aplicación con dependencias inyectadas y guarda
las respuestas en ``context`` para que los pasos ``Then`` las revisen.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/ask.feature")

PREVIOUS_CONVERSATION = [
    {"role": "user", "content": "Hola, necesito datos de una persona del equipo"},
    {"role": "assistant", "content": "Claro, dime el id del empleado."},
]


@pytest.fixture
def context():
    """Estado de un escenario: el cliente y las respuestas recibidas.

    :return: Diccionario con la lista ``responses``
    :rtype: dict
    """
    return {"responses": []}


def _ask(context, question, history=None):
    """Envía ``POST /ask`` y guarda la respuesta en el contexto."""
    body = {"question": question}
    if history is not None:
        body["history"] = history
    context["responses"].append(context["client"].post("/ask", json=body))


def _last_body(context):
    """Devuelve el JSON de la última respuesta."""
    return context["responses"][-1].json()


@given("the assistant is running with the default settings")
def assistant_with_default_settings(context, make_client):
    """Aplicación con la configuración por omisión."""
    context["client"] = make_client()


@given(parsers.parse("the assistant is running with a step cap of {cap:d}"))
def assistant_with_step_cap(context, make_client, cap):
    """Aplicación con ``AGENT_MAX_STEPS`` fijado por el escenario."""
    context["client"] = make_client(AGENT_MAX_STEPS=str(cap))


@when(parsers.parse('I ask "{question}"'))
def ask_question(context, question):
    """Pregunta sin historial."""
    _ask(context, question)


@when(parsers.parse('I ask "{question}" with a previous conversation'))
def ask_question_with_history(context, question):
    """Pregunta enviando un historial que guarda el cliente."""
    _ask(context, question, history=PREVIOUS_CONVERSATION)


@when("I send an empty question")
def send_empty_question(context):
    """Pregunta vacía."""
    _ask(context, "")


@when(parsers.parse("I ask a question of {length:d} characters"))
def ask_long_question(context, length):
    """Pregunta con el largo indicado."""
    _ask(context, "a" * length)


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(context, status):
    """Revisa el código HTTP de la última respuesta."""
    assert context["responses"][-1].status_code == status


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(context, text):
    """Revisa que la respuesta contenga el texto."""
    assert text in _last_body(context)["answer"]


@then(parsers.parse('the answer is "{text}"'))
def answer_is(context, text):
    """Revisa que la respuesta sea exactamente el texto."""
    assert _last_body(context)["answer"] == text


@then(parsers.parse('the tools used are "{names}"'))
def tools_used_are(context, names):
    """Revisa las herramientas usadas, en orden."""
    assert _last_body(context)["tools_used"] == names.split(", ")


@then("no tools were used")
def no_tools_were_used(context):
    """Revisa que no se haya usado ninguna herramienta."""
    assert _last_body(context)["tools_used"] == []


@then(parsers.parse("the number of steps is {steps:d}"))
def number_of_steps_is(context, steps):
    """Revisa cuántas veces se llamó al modelo."""
    assert _last_body(context)["steps"] == steps


@then("both answers are the same")
def both_answers_are_the_same(context):
    """La segunda pregunta no depende de la primera."""
    first, second = context["responses"]
    assert first.status_code == second.status_code == 200
    for field in ("answer", "steps", "tools_used"):
        assert first.json()[field] == second.json()[field]


@then("the second question counted fewer input tokens than the first")
def second_question_counted_fewer_tokens(context):
    """Si la API guardara el historial, la segunda pregunta contaría más palabras."""
    first, second = (response.json() for response in context["responses"])
    assert second["input_tokens"] < first["input_tokens"]
