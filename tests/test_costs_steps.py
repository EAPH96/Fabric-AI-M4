"""Pasos de los escenarios de ``features/costs.feature``.

Los escenarios con el modelo simulado no usan red. Los del gateway usan el
``FakeGateway`` de ``conftest.py``, inyectado como cliente HTTP.
"""

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.llm import Completion

scenarios("features/costs.feature")

SPY_ANSWER = json.dumps({"answer": "Respuesta del modelo espía"})


class SpyModel:
    """Modelo espía: guarda los mensajes de cada llamada y responde de inmediato."""

    def __init__(self):
        self.calls = []

    def complete(self, messages):
        """Guarda una copia de la conversación y responde una respuesta final.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :return: Respuesta final con tokens fijos
        :rtype: Completion
        """
        self.calls.append([dict(message) for message in messages])
        return Completion(text=SPY_ANSWER, input_tokens=10, output_tokens=5)


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente, preguntas, historial y respuestas.

    :return: Diccionario con las listas ``questions`` y ``responses``
    :rtype: dict
    """
    return {"questions": [], "responses": [], "history": []}


def _last_response(scenario_state):
    """Devuelve la última respuesta HTTP del escenario."""
    return scenario_state["responses"][-1]


def _events_named(log_events, name):
    """Devuelve los eventos del log con el nombre indicado."""
    return [event for event in log_events() if event["event"] == name]


@given("the assistant is running with the default settings")
def assistant_with_default_settings(scenario_state, make_client):
    """Modelos simulados con la configuración por omisión."""
    scenario_state["client"] = make_client()


@given(
    parsers.parse(
        "the assistant is running with a routing limit of {limit:d} characters"
    )
)
def assistant_with_routing_limit(scenario_state, make_client, limit):
    """Modelos simulados con ``ROUTER_MAX_CHARS`` fijado por el escenario."""
    scenario_state["client"] = make_client(ROUTER_MAX_CHARS=str(limit))


@given("the assistant is running with routing disabled")
def assistant_with_routing_disabled(scenario_state, make_client):
    """Modelos simulados con ``ROUTING=false``."""
    scenario_state["client"] = make_client(ROUTING="false")


@given(
    parsers.parse(
        "the assistant is running with a history window of {window:d} and a spy model"
    )
)
def assistant_with_history_window(scenario_state, make_client, window):
    """Un modelo espía atiende las dos rutas con ``HISTORY_WINDOW`` fijado."""
    scenario_state["spy"] = SpyModel()
    scenario_state["client"] = make_client(
        model=scenario_state["spy"], HISTORY_WINDOW=str(window)
    )


@given(
    "the assistant is running on the gateway and the gateway answers from its cache"
)
def assistant_with_cached_gateway(
    scenario_state, make_client, fake_gateway, gateway_env
):
    """El gateway simulado responde con ``cf-aig-cache-status: HIT``."""
    fake_gateway.headers = {"cf-aig-cache-status": "HIT"}
    scenario_state["client"] = make_client(
        http_client=fake_gateway.client(), CACHE_TTL_SECONDS="60", **gateway_env
    )


@given(
    parsers.parse(
        "the assistant is running on the gateway and the gateway fails"
        " with status {status:d}"
    )
)
def assistant_with_failing_gateway(
    scenario_state, make_client, fake_gateway, gateway_env, status
):
    """El gateway simulado responde un error HTTP."""
    fake_gateway.status = status
    fake_gateway.payload = {"errors": [{"message": "upstream exploded"}]}
    scenario_state["client"] = make_client(
        http_client=fake_gateway.client(), **gateway_env
    )


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask_question(scenario_state, question):
    """Pregunta sin historial."""
    response = scenario_state["client"].post("/ask", json={"question": question})
    scenario_state["questions"].append(question)
    scenario_state["responses"].append(response)


@when(
    parsers.re(
        r'I ask "(?P<question>[^"]+)" after a conversation of (?P<size>\d+) messages'
    )
)
def ask_question_with_history(scenario_state, question, size):
    """Pregunta con un historial de mensajes numerados, alternando roles."""
    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}"}
        for index in range(int(size))
    ]
    body = {"question": question, "history": history}
    response = scenario_state["client"].post("/ask", json=body)
    scenario_state["history"] = history
    scenario_state["questions"].append(question)
    scenario_state["responses"].append(response)


@when("I read the metrics")
def read_metrics(scenario_state):
    """Pide ``GET /metrics`` y guarda el cuerpo."""
    scenario_state["metrics"] = scenario_state["client"].get("/metrics").json()


@then(
    parsers.parse('the answer used the model "{model}" for the reason "{reason}"')
)
def answer_used_model(scenario_state, model, reason):
    """La respuesta dice qué modelo eligió el enrutador y por qué."""
    response = _last_response(scenario_state)
    assert response.status_code == 200
    body = response.json()
    assert (body["model"], body["route"]) == (model, reason)


@then(parsers.parse("the answer reports a positive cost and {cached:d} cached calls"))
def answer_reports_positive_cost(scenario_state, cached):
    """El costo del modelo simulado es positivo aunque la pregunta sea corta."""
    body = _last_response(scenario_state).json()
    assert body["cost_usd"] > 0
    assert body["cached_calls"] == cached


@then(parsers.parse("the answer reports a cost of 0 and {cached:d} cached calls"))
def answer_reports_zero_cost(scenario_state, cached):
    """Una llamada servida por la caché no cuesta, pero sí cuenta sus tokens."""
    body = _last_response(scenario_state).json()
    assert body["cost_usd"] == 0
    assert body["cached_calls"] == cached
    assert body["input_tokens"] > 0


@then("the agent run event has the model, the route and the cost of the answer")
def agent_run_has_cost(scenario_state, log_events):
    """``agent_run`` registra lo mismo que la respuesta, sin texto."""
    (event,) = _events_named(log_events, "agent_run")
    body = _last_response(scenario_state).json()
    for key in ("model", "route", "cached_calls", "cost_usd"):
        assert event[key] == body[key]


@then(
    parsers.parse(
        "the model received only the last {window:d} history messages and the question"
    )
)
def model_received_recent_history(scenario_state, window):
    """La primera llamada al modelo lleva solo el final del historial."""
    first_call = scenario_state["spy"].calls[0]
    expected = scenario_state["history"][-window:] + [
        {"role": "user", "content": scenario_state["questions"][-1]}
    ]
    assert first_call == expected


@then("the log never contains the Cloudflare token")
def log_has_no_token(log_events, gateway_env):
    """El token de Cloudflare nunca llega al log."""
    log_text = json.dumps(log_events(), ensure_ascii=False)
    assert gateway_env["CF_API_TOKEN"] not in log_text


@then("the metrics cost is the sum of the cost of both answers")
def metrics_add_up_cost(scenario_state):
    """``/metrics`` acumula el costo de cada respuesta del proceso."""
    costs = [response.json()["cost_usd"] for response in scenario_state["responses"]]
    assert all(cost > 0 for cost in costs)
    assert scenario_state["metrics"]["cost_usd"] == pytest.approx(sum(costs))
