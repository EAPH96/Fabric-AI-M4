"""Pasos de los escenarios de ``features/business_metrics.feature``.

Cada escenario arma su aplicación sin clave por omisión y manda la clave del
cliente ``staff`` en cada pregunta, para poder hacer también una petición sin
clave. Los escenarios del gateway usan el ``FakeGateway`` de ``conftest.py``.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/business_metrics.feature")

API_KEY_HEADER = "X-API-Key"
STAFF_KEY = "staff-key-for-tests-0001"
API_KEYS = f"staff:{STAFF_KEY}"
STAFF_HEADERS = {API_KEY_HEADER: STAFF_KEY}
CAP_MESSAGE_START = "No pude completar"


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente, respuestas y métricas leídas.

    :return: Diccionario con la lista ``responses``
    :rtype: dict
    """
    return {"responses": []}


def _answers(scenario_state):
    """Cuerpos de las respuestas ``200`` del escenario."""
    return [
        response.json()
        for response in scenario_state["responses"]
        if response.status_code == 200
    ]


def _post(scenario_state, question, headers):
    """Envía ``POST /ask`` con los encabezados dados y guarda la respuesta."""
    response = scenario_state["client"].post(
        "/ask", json={"question": question}, headers=headers
    )
    scenario_state["responses"].append(response)


@given("the assistant is running with the default settings")
def assistant_with_default_settings(scenario_state, make_client):
    """Modelos simulados con la configuración por omisión."""
    scenario_state["client"] = make_client(api_key=None, API_KEYS=API_KEYS)


@given(parsers.parse("the assistant is running with a cap of {steps:d} step"))
def assistant_with_step_cap(scenario_state, make_client, steps):
    """Modelos simulados con ``AGENT_MAX_STEPS`` fijado por el escenario."""
    scenario_state["client"] = make_client(
        api_key=None, API_KEYS=API_KEYS, AGENT_MAX_STEPS=str(steps)
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
        http_client=fake_gateway.client(),
        api_key=None,
        API_KEYS=API_KEYS,
        CACHE_TTL_SECONDS="60",
        **gateway_env,
    )


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask_question(scenario_state, question):
    """Pregunta con la clave del cliente ``staff``."""
    _post(scenario_state, question, STAFF_HEADERS)


@when(parsers.re(r'I ask "(?P<question>[^"]+)" without a key'))
def ask_question_without_key(scenario_state, question):
    """Pregunta sin encabezado ``X-API-Key``."""
    _post(scenario_state, question, {})


@when("I read the metrics")
def read_metrics(scenario_state):
    """Pide ``GET /metrics`` con la clave y guarda el cuerpo."""
    response = scenario_state["client"].get("/metrics", headers=STAFF_HEADERS)
    assert response.status_code == 200
    scenario_state["metrics"] = response.json()


@then(parsers.parse("the answers came from {count:d} different models"))
def answers_came_from_models(scenario_state, count):
    """Una pregunta fue al modelo pequeño y otra al grande."""
    models = {body["model"] for body in _answers(scenario_state)}
    assert len(models) == count


@then("each model counts its answers with the cost of those answers")
def each_model_counts_its_answers(scenario_state):
    """``by_model`` tiene una entrada por modelo con sus respuestas y su costo."""
    answers = _answers(scenario_state)
    by_model = scenario_state["metrics"]["by_model"]
    assert set(by_model) == {body["model"] for body in answers}
    for model, counted in by_model.items():
        own = [body for body in answers if body["model"] == model]
        assert counted["requests"] == len(own)
        assert counted["cost_usd"] > 0
        assert counted["cost_usd"] == pytest.approx(
            sum(body["cost_usd"] for body in own), abs=1e-12
        )


@then(
    parsers.parse(
        'the metrics count {first:d} runs of "{first_tool}"'
        ' and {second:d} run of "{second_tool}"'
    )
)
def metrics_count_tool_runs(scenario_state, first, first_tool, second, second_tool):
    """``tools`` cuenta cada ejecución de cada herramienta."""
    assert scenario_state["metrics"]["tools"] == {
        first_tool: first,
        second_tool: second,
    }


@then("the tools in the metrics add up to the tools used by the answers")
def tools_add_up_to_tools_used(scenario_state):
    """La suma de ``tools`` es igual al total de ``tools_used`` de las respuestas."""
    used = [tool for body in _answers(scenario_state) for tool in body["tools_used"]]
    assert sum(scenario_state["metrics"]["tools"].values()) == len(used)


@then(
    parsers.parse(
        'the status classes are {ok:d} "2xx", {client_error:d} "4xx"'
        ' and {server_error:d} "5xx"'
    )
)
def status_classes_are(scenario_state, ok, client_error, server_error):
    """``status`` cuenta cada petición en su clase."""
    expected = {"2xx": ok, "4xx": client_error, "5xx": server_error}
    assert scenario_state["metrics"]["status"] == expected


@then("the status classes add up to the requests")
def status_classes_add_up(scenario_state):
    """La suma de las tres clases es igual a ``requests``."""
    metrics = scenario_state["metrics"]
    assert sum(metrics["status"].values()) == metrics["requests"]


@then(parsers.parse("the metrics count {count:d} answer in total by model"))
def metrics_count_answers_by_model(scenario_state, count):
    """Una petición rechazada no suma a ningún modelo."""
    by_model = scenario_state["metrics"]["by_model"]
    assert sum(entry["requests"] for entry in by_model.values()) == count


@then("the answer was cut by the step cap")
def answer_was_cut(scenario_state):
    """La respuesta es el mensaje del tope tras una sola llamada al modelo."""
    (body,) = _answers(scenario_state)
    assert body["steps"] == 1
    assert body["answer"].startswith(CAP_MESSAGE_START)


@then(parsers.parse("the metrics count {count:d} stopped answer"))
def metrics_count_stopped(scenario_state, count):
    """``stopped`` cuenta las respuestas cortadas por el tope."""
    assert scenario_state["metrics"]["stopped"] == count


@then(parsers.parse("the metrics count {count:d} cached call"))
def metrics_count_cached_calls(scenario_state, count):
    """``cached_calls`` suma lo que dicen las respuestas."""
    (body,) = _answers(scenario_state)
    assert body["cached_calls"] == count
    assert scenario_state["metrics"]["cached_calls"] == count


@then(
    parsers.parse(
        "the model of the answer counts {count:d} answer with a cost of 0"
    )
)
def model_counts_free_answer(scenario_state, count):
    """Una respuesta de la caché cuenta en su modelo, pero no cuesta."""
    (body,) = _answers(scenario_state)
    assert scenario_state["metrics"]["by_model"] == {
        body["model"]: {"requests": count, "cost_usd": 0}
    }
