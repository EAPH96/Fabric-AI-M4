"""Pasos de los escenarios de ``features/policies.feature``.

Cada escenario arma su propia aplicación con dependencias inyectadas y guarda
las respuestas en ``scenario_state`` para que los pasos ``Then`` las revisen.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/policies.feature")

VACATIONS = "¿Cuántos días de vacaciones me tocan?"
API_KEY_HEADER = "X-API-Key"
STAFF_KEY = "staff-key-for-tests-0001"


@pytest.fixture
def scenario_state():
    """Estado de un escenario: el cliente HTTP y las respuestas recibidas.

    :return: Diccionario con la lista ``responses``
    :rtype: dict
    """
    return {"responses": []}


def _last_response(scenario_state):
    """Devuelve la última respuesta HTTP del escenario."""
    return scenario_state["responses"][-1]


def _ask(scenario_state, question, headers=None):
    """Envía ``POST /ask`` y guarda la respuesta en el estado."""
    response = scenario_state["client"].post(
        "/ask", json={"question": question}, headers=headers
    )
    scenario_state["responses"].append(response)


@given("the assistant is running with the default settings")
def assistant_with_default_settings(scenario_state, make_client):
    """Aplicación con la configuración por omisión y la clave de prueba."""
    scenario_state["client"] = make_client()


@given(parsers.parse('the assistant is running with the companion URL "{url}"'))
def assistant_with_companion(scenario_state, make_client, url):
    """Aplicación con ``COMPANION_URL`` y el nombre por omisión, sin clave."""
    scenario_state["client"] = make_client(api_key=None, COMPANION_URL=url)


@given("the assistant is running for one client")
def assistant_for_one_client(scenario_state, make_client):
    """Aplicación con un cliente; el ``TestClient`` no manda clave por omisión."""
    scenario_state["client"] = make_client(
        api_key=None, API_KEYS=f"staff:{STAFF_KEY}"
    )


@given(parsers.parse("the assistant allows {limit:d} questions per minute"))
def assistant_with_rate_limit(scenario_state, make_client, limit):
    """Aplicación con un límite pequeño por minuto."""
    scenario_state["client"] = make_client(RATE_LIMIT_PER_MINUTE=str(limit))


@when(parsers.parse('I ask "{question}"'))
def ask_question(scenario_state, question):
    """Pregunta sin historial."""
    _ask(scenario_state, question)


@when("I open the home page without a key")
def open_home_page(scenario_state):
    """Pide ``GET /`` sin clave."""
    scenario_state["responses"].append(scenario_state["client"].get("/"))


@when("I ask about vacations without a key")
def ask_without_key(scenario_state):
    """Pregunta sin encabezado ``X-API-Key``."""
    _ask(scenario_state, VACATIONS)


@when(parsers.parse('I ask about vacations with the key "{key}"'))
def ask_with_key(scenario_state, key):
    """Pregunta con la clave indicada."""
    _ask(scenario_state, VACATIONS, headers={API_KEY_HEADER: key})


@when(parsers.parse("I ask about vacations {count:d} times"))
def ask_many_times(scenario_state, count):
    """Hace varias preguntas seguidas con la clave de prueba."""
    for _ in range(count):
        _ask(scenario_state, VACATIONS)


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(scenario_state, status):
    """Revisa el código HTTP de la última respuesta."""
    assert _last_response(scenario_state).status_code == status


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(scenario_state, text):
    """Revisa que la respuesta contenga el texto."""
    assert text in _last_response(scenario_state).json()["answer"]


@then(parsers.parse('the answer is "{text}"'))
def answer_is(scenario_state, text):
    """Revisa que la respuesta sea exactamente el texto."""
    assert _last_response(scenario_state).json()["answer"] == text


@then(parsers.parse('the tools used are "{names}"'))
def tools_used_are(scenario_state, names):
    """Revisa las herramientas usadas, en orden."""
    assert _last_response(scenario_state).json()["tools_used"] == names.split(", ")


@then("no tools were used")
def no_tools_were_used(scenario_state):
    """Revisa que no se haya usado ninguna herramienta."""
    assert _last_response(scenario_state).json()["tools_used"] == []


@then(parsers.parse("the number of steps is {steps:d}"))
def number_of_steps_is(scenario_state, steps):
    """Revisa cuántas veces se llamó al modelo."""
    assert _last_response(scenario_state).json()["steps"] == steps


@then(parsers.parse('the page says "{text}"'))
def page_says(scenario_state, text):
    """El texto aparece en el HTML de la página."""
    assert text in _last_response(scenario_state).text


@then(
    parsers.parse('the page header has a companion link named "{name}" to "{url}"')
)
def header_has_companion_link(scenario_state, companion_links, name, url):
    """Un solo enlace, dentro del ``<header>``, con el nombre y la URL dados."""
    (link,) = companion_links(_last_response(scenario_state).text)
    assert link["in_header"]
    assert link["text"] == name
    assert link["attrs"]["href"] == url


@then(parsers.parse("every response has status {status:d}"))
def every_response_has_status(scenario_state, status):
    """Todas las respuestas del escenario tienen el mismo código."""
    statuses = [response.status_code for response in scenario_state["responses"]]
    assert statuses == [status] * len(statuses)


@then(parsers.parse('the statuses are "{statuses}"'))
def statuses_are(scenario_state, statuses):
    """Los códigos de las respuestas, en orden."""
    expected = [int(status) for status in statuses.split(", ")]
    actual = [response.status_code for response in scenario_state["responses"]]
    assert actual == expected


@then("the last response has a positive Retry-After header")
def retry_after_is_positive(scenario_state):
    """``Retry-After`` dice en cuántos segundos se puede volver a preguntar."""
    assert int(_last_response(scenario_state).headers["Retry-After"]) > 0
