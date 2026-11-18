"""Pasos de los escenarios de ``features/security.feature``.

Cada escenario arma su aplicación sin clave en el ``TestClient``: los pasos
mandan ``X-API-Key`` a mano, para probar tanto la falta de clave como la clave
de cada cliente. El reloj falso de ``conftest.py`` mueve la ventana del límite.
"""

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import ConfigError

scenarios("features/security.feature")

QUESTION = "¿Quién es EMP-0004?"
API_KEY_HEADER = "X-API-Key"
CLIENT_KEYS = {
    "hr": "hr-key-for-tests-0001",
    "payroll": "payroll-key-for-tests-0002",
}
API_KEYS = ",".join(f"{name}:{key}" for name, key in CLIENT_KEYS.items())
OPEN_PATHS = ("/", "/health", "/docs")
METRICS_PATH = "/metrics"


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente HTTP, respuestas y error de arranque.

    :return: Diccionario con la lista ``responses``
    :rtype: dict
    """
    return {"responses": []}


def _last_response(scenario_state):
    """Devuelve la última respuesta HTTP del escenario."""
    return scenario_state["responses"][-1]


def _events_named(log_events, name):
    """Devuelve los eventos del log con el nombre indicado."""
    return [event for event in log_events() if event["event"] == name]


def _ask(scenario_state, headers):
    """Envía ``POST /ask`` con los encabezados dados y guarda la respuesta."""
    response = scenario_state["client"].post(
        "/ask", json={"question": QUESTION}, headers=headers
    )
    scenario_state["responses"].append(response)


@given('the assistant is running for the clients "hr" and "payroll"')
def assistant_for_two_clients(scenario_state, make_client):
    """Aplicación con dos clientes y el límite por omisión."""
    scenario_state["client"] = make_client(api_key=None, API_KEYS=API_KEYS)


@given(
    parsers.parse("the assistant allows {limit:d} questions per minute to each client")
)
def assistant_with_rate_limit(scenario_state, make_client, limit):
    """Aplicación con dos clientes y un límite pequeño por minuto."""
    scenario_state["client"] = make_client(
        api_key=None, API_KEYS=API_KEYS, RATE_LIMIT_PER_MINUTE=str(limit)
    )


@given("the environment is production with the fake model")
def production_with_fake_model(scenario_state):
    """Entorno de producción que incumple una sola regla: el modelo simulado."""
    scenario_state["env"] = {
        "ENVIRONMENT": "production",
        "MODEL_PROVIDER": "fake",
        "API_KEYS": API_KEYS,
    }


@when("I ask without a key")
def ask_without_key(scenario_state):
    """Pregunta sin encabezado ``X-API-Key``."""
    _ask(scenario_state, headers={})


@when(parsers.parse('I ask with the wrong key "{key}"'))
def ask_with_wrong_key(scenario_state, key):
    """Pregunta con una clave que no es de ningún cliente."""
    _ask(scenario_state, headers={API_KEY_HEADER: key})


@when(
    parsers.re(r'client "(?P<name>\w+)" asks (?P<count>\d+) questions?'),
    converters={"count": int},
)
def client_asks(scenario_state, name, count):
    """El cliente indicado hace varias preguntas seguidas con su clave."""
    for _ in range(count):
        _ask(scenario_state, headers={API_KEY_HEADER: CLIENT_KEYS[name]})


@when(parsers.parse("the clock moves {seconds:d} seconds"))
def clock_moves(clock, seconds):
    """Adelanta el reloj que comparten la aplicación y la prueba."""
    clock.advance(seconds)


@when("I open the page, the health check, the docs and the metrics without a key")
def open_paths_without_key(scenario_state):
    """Pide cada ruta sin clave y guarda su código por ruta."""
    client = scenario_state["client"]
    paths = (*OPEN_PATHS, METRICS_PATH)
    scenario_state["opened"] = {path: client.get(path).status_code for path in paths}


@when("the assistant starts")
def assistant_starts(scenario_state, make_client):
    """Intenta armar la aplicación y guarda el error de configuración."""
    try:
        make_client(api_key=None, **scenario_state["env"])
    except ConfigError as error:
        scenario_state["error"] = error


@then(parsers.parse('the body says exactly "{detail}"'))
def body_says_exactly(scenario_state, detail):
    """El cuerpo del rechazo es exactamente el de la especificación."""
    assert _last_response(scenario_state).json() == {"detail": detail}


@then(parsers.parse("the first {count:d} questions were answered"))
def first_questions_answered(scenario_state, count):
    """Las preguntas dentro del límite responden 200."""
    statuses = [response.status_code for response in scenario_state["responses"]]
    assert statuses[:count] == [200] * count


@then("the response has a positive Retry-After header")
def retry_after_is_positive(scenario_state):
    """``Retry-After`` dice en cuántos segundos se puede volver a preguntar."""
    assert int(_last_response(scenario_state).headers["Retry-After"]) > 0


@then(
    parsers.parse('the request, agent run and audit events name the client "{name}"')
)
def events_name_the_client(log_events, name):
    """``request``, ``agent_run`` y cada ``audit`` llevan el nombre del cliente."""
    for event_name in ("request", "agent_run", "audit"):
        events = _events_named(log_events, event_name)
        assert events, f"no {event_name} event"
        assert all(event.get("client") == name for event in events)


@then(parsers.parse('the log never contains the key of client "{name}"'))
def log_has_no_key(log_events, name):
    """La clave no aparece en ninguna línea del log."""
    log_text = json.dumps(log_events(), ensure_ascii=False)
    assert CLIENT_KEYS[name] not in log_text


@then("the page, the health check and the docs answer 200")
def open_paths_answer_200(scenario_state):
    """``/``, ``/health`` y ``/docs`` no piden clave."""
    opened = scenario_state["opened"]
    assert {path: opened[path] for path in OPEN_PATHS} == dict.fromkeys(
        OPEN_PATHS, 200
    )


@then("the metrics answer 401")
def metrics_answer_401(scenario_state):
    """``/metrics`` sí pide clave."""
    assert scenario_state["opened"][METRICS_PATH] == 401


@then(parsers.parse('it refuses to start naming "{variable}" but never the key'))
def refuses_to_start(scenario_state, variable):
    """El error nombra la regla incumplida y no muestra ninguna clave."""
    error = scenario_state.get("error")
    assert error is not None, "the assistant started in production"
    message = str(error)
    assert variable in message
    assert all(key not in message for key in CLIENT_KEYS.values())
