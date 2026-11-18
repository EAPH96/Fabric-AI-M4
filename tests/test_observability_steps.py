"""Pasos de los escenarios de ``features/observability.feature``.

Cada escenario arma su aplicación con el reloj falso y el log en memoria de
``conftest.py``; los pasos ``Then`` leen las respuestas guardadas en
``scenario_state`` y los eventos del log.
"""

import json
import uuid

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/observability.feature")

SECRET_MESSAGE = "db password is hunter2"


class FailingModel:
    """Modelo que siempre truena con un mensaje que no debe llegar al log."""

    def complete(self, messages):
        """Lanza un error inesperado sin importar la conversación.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :raises RuntimeError: Siempre, con un mensaje secreto
        """
        raise RuntimeError(f"{SECRET_MESSAGE} ({len(messages)} messages)")


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente, preguntas, respuestas y métricas.

    :return: Diccionario con las listas ``questions`` y ``responses``
    :rtype: dict
    """
    return {"questions": [], "responses": []}


def _last_response(scenario_state):
    """Devuelve la última respuesta HTTP del escenario."""
    return scenario_state["responses"][-1]


def _events_named(log_events, name):
    """Devuelve los eventos del log con el nombre indicado."""
    return [event for event in log_events() if event["event"] == name]


def _post_question(scenario_state, question, headers=None):
    """Envía ``POST /ask`` y guarda la pregunta y la respuesta."""
    response = scenario_state["client"].post(
        "/ask", json={"question": question}, headers=headers or {}
    )
    scenario_state["questions"].append(question)
    scenario_state["responses"].append(response)


@given("the assistant is running with observability")
def assistant_with_observability(scenario_state, make_client):
    """Aplicación por omisión con log en memoria y reloj falso."""
    scenario_state["client"] = make_client()


@given("the assistant is running with a model that fails with a secret message")
def assistant_with_failing_model(scenario_state, make_client):
    """Aplicación cuyo modelo lanza ``RuntimeError`` en cada llamada."""
    scenario_state["client"] = make_client(model=FailingModel())


@when("I check the health endpoint")
def check_health(scenario_state):
    """Pide ``GET /health`` sin encabezado ``X-Request-ID``."""
    scenario_state["responses"].append(scenario_state["client"].get("/health"))


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask_question(scenario_state, question):
    """Pregunta sin historial y sin id del cliente."""
    _post_question(scenario_state, question)


@when(
    parsers.re(
        r'the client sends the request id "(?P<request_id>[^"]+)"'
        r' with the question "(?P<question>[^"]+)"'
    )
)
def ask_with_request_id(scenario_state, request_id, question):
    """Pregunta mandando su propio ``X-Request-ID``."""
    _post_question(scenario_state, question, headers={"X-Request-ID": request_id})


@when("I read the metrics")
def read_metrics(scenario_state):
    """Pide ``GET /metrics`` y guarda el cuerpo."""
    scenario_state["metrics"] = scenario_state["client"].get("/metrics").json()


@when("I open the home page")
def open_home_page(scenario_state):
    """Pide la página web."""
    scenario_state["responses"].append(scenario_state["client"].get("/"))


@then("the response carries a generated UUID as its request id")
def response_has_generated_uuid(scenario_state):
    """El id generado es un UUID válido."""
    request_id = _last_response(scenario_state).headers["X-Request-ID"]
    assert str(uuid.UUID(request_id)) == request_id


@then(parsers.parse('the response header X-Request-ID is "{request_id}"'))
def header_request_id_is(scenario_state, request_id):
    """El encabezado devuelve el id del cliente."""
    assert _last_response(scenario_state).headers["X-Request-ID"] == request_id


@then(parsers.parse('the answer body has the request id "{request_id}"'))
def body_request_id_is(scenario_state, request_id):
    """El cuerpo de ``POST /ask`` también trae el id."""
    response = _last_response(scenario_state)
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id


@then(parsers.parse('the log has exactly one "{name}" event'))
def log_has_one_event(log_events, name):
    """Hay una sola línea del evento indicado."""
    assert len(_events_named(log_events, name)) == 1


@then(
    parsers.parse(
        'the request event has method "{method}", path "{path}" and status {status:d}'
    )
)
def request_event_has(log_events, method, path, status):
    """La línea ``request`` describe la petición atendida."""
    (event,) = _events_named(log_events, "request")
    assert (event["method"], event["path"], event["status"]) == (method, path, status)


@then("the request event has a positive latency and the request id of the response")
def request_event_matches_response(scenario_state, log_events):
    """La línea ``request`` mide la latencia y comparte el id de la respuesta."""
    (event,) = _events_named(log_events, "request")
    response = _last_response(scenario_state)
    assert event["latency_ms"] > 0
    assert event["request_id"] == response.headers["X-Request-ID"]


@then("the agent run event has the counts of the answer and was not stopped")
def agent_run_has_counts(scenario_state, log_events):
    """``agent_run`` lleva solo conteos que coinciden con la respuesta."""
    (event,) = _events_named(log_events, "agent_run")
    body = _last_response(scenario_state).json()
    assert event["request_id"] == body["request_id"]
    assert event["question_chars"] == len(scenario_state["questions"][-1])
    assert event["history_messages"] == 0
    assert event["steps"] == body["steps"] == 2
    assert event["tools"] == body["tools_used"]
    assert event["input_tokens"] == body["input_tokens"]
    assert event["output_tokens"] == body["output_tokens"]
    assert event["stopped"] is False


@then(parsers.parse('the log has one audit of "{tool}" for employee "{employee_id}"'))
def log_has_audit(log_events, tool, employee_id):
    """Hay un ``audit`` por la herramienta ejecutada, con sus argumentos."""
    (event,) = _events_named(log_events, "audit")
    assert event["action"] == "tool_call"
    assert event["tool"] == tool
    assert event["args"] == {"employee_id": employee_id}


@then("the log never contains the question or the answer")
def log_has_no_conversation(scenario_state, log_events):
    """Ni la pregunta ni la respuesta aparecen en ninguna línea."""
    log_text = json.dumps(log_events(), ensure_ascii=False)
    assert scenario_state["questions"][-1] not in log_text
    assert _last_response(scenario_state).json()["answer"] not in log_text
    assert "Jorge" not in log_text


@then("the log never contains the secret message")
def log_has_no_secret(log_events):
    """El mensaje de la excepción nunca llega al log."""
    assert SECRET_MESSAGE not in json.dumps(log_events(), ensure_ascii=False)


@then(
    parsers.parse(
        "the metrics count {requests:d} requests with an error rate of {rate:f}"
    )
)
def metrics_count_requests(scenario_state, requests, rate):
    """``/metrics`` cuenta las peticiones atendidas antes de leerlas."""
    metrics = scenario_state["metrics"]
    assert metrics["requests"] == requests
    assert metrics["error_rate"] == rate


@then("the metrics add up the tokens of both answers")
def metrics_add_up_tokens(scenario_state):
    """Los tokens de ``/metrics`` son la suma de los de cada respuesta."""
    bodies = [response.json() for response in scenario_state["responses"]]
    expected = {
        "input": sum(body["input_tokens"] for body in bodies),
        "output": sum(body["output_tokens"] for body in bodies),
    }
    assert expected["input"] > 0
    assert scenario_state["metrics"]["tokens"] == expected


@then(parsers.parse("the latency objective is {target:d} ms and it is met"))
def latency_objective_is_met(scenario_state, target):
    """La meta por omisión se cumple con latencias de milisegundos."""
    assert scenario_state["metrics"]["slo"] == {"p95_ms_target": target, "met": True}


@then("the page has a place to show the request id")
def page_shows_request_id(scenario_state):
    """La página lee ``request_id`` y lo pinta en su propio elemento."""
    page = _last_response(scenario_state).text
    assert 'data-testid="request-id"' in page
    assert "request_id" in page
