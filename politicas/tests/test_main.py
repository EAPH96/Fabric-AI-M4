"""Pruebas de la API web de Políticas armada con ``create_app()``.

Recorren el middleware, la clave, el límite, el enrutador, el costo y el log,
que son los módulos copiados del HR.
"""

import json
import os

VACATIONS = "¿Cuántos días de vacaciones me tocan?"
POLICY_QUESTION = "¿Qué dice la política POL-003?"
STAFF_KEY = "staff-key-for-tests-0001"
READER_KEY = "reader-key-for-tests-0001"
API_KEY_HEADER = "X-API-Key"


def test_health_reports_ok_and_the_process_id(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pid": os.getpid()}


def test_swagger_is_titled_as_the_policies_assistant(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "Asistente de políticas de RH"


def test_metrics_add_up_the_cost_of_a_question(client):
    answer = client.post("/ask", json={"question": VACATIONS}).json()

    metrics = client.get("/metrics").json()

    assert answer["cost_usd"] > 0
    assert metrics["cost_usd"] == answer["cost_usd"]
    assert metrics["tokens"]["input"] == answer["input_tokens"]


def test_client_request_id_is_kept_and_the_log_names_the_service(client, log_events):
    response = client.post(
        "/ask", json={"question": VACATIONS}, headers={"X-Request-ID": "demo-pol"}
    )

    assert response.json()["request_id"] == "demo-pol"
    assert response.headers["X-Request-ID"] == "demo-pol"
    events = [e for e in log_events() if e["request_id"] == "demo-pol"]
    assert {event["event"] for event in events} >= {"request", "agent_run", "audit"}
    assert {event["service"] for event in events} == {"politicas-rh"}


def test_blank_question_is_rejected(client):
    response = client.post("/ask", json={"question": "   "})

    assert response.status_code == 422


def test_gateway_failure_returns_502_with_the_request_id(
    make_client, gateway_env, fake_gateway
):
    fake_gateway.status = 500
    client = make_client(http_client=fake_gateway.client(), **gateway_env)

    response = client.post("/ask", json={"question": VACATIONS})

    assert response.status_code == 502
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {"detail": "model unavailable", "request_id": request_id}


def test_gateway_failure_counts_as_5xx_and_leaves_business_metrics_untouched(
    make_client, gateway_env, fake_gateway
):
    fake_gateway.status = 500
    client = make_client(http_client=fake_gateway.client(), **gateway_env)

    assert client.post("/ask", json={"question": VACATIONS}).status_code == 502
    metrics = client.get("/metrics").json()

    assert metrics["status"] == {"2xx": 0, "4xx": 0, "5xx": 1}
    assert metrics["by_model"] == {}
    assert metrics["tools"] == {}
    assert metrics["cached_calls"] == 0
    assert metrics["stopped"] == 0


def test_blank_question_counts_as_4xx_and_not_by_model(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    metrics = client.get("/metrics").json()

    assert metrics["status"] == {"2xx": 0, "4xx": 1, "5xx": 0}
    assert metrics["by_model"] == {}


def test_rate_limited_question_counts_as_4xx(make_client):
    client = make_client(
        api_key=None,
        API_KEYS=f"staff:{STAFF_KEY},reader:{READER_KEY}",
        RATE_LIMIT_PER_MINUTE="2",
    )
    staff = {API_KEY_HEADER: STAFF_KEY}

    statuses = [
        client.post("/ask", json={"question": VACATIONS}, headers=staff).status_code
        for _ in range(3)
    ]
    metrics = client.get("/metrics", headers={API_KEY_HEADER: READER_KEY}).json()

    assert statuses == [200, 200, 429]
    assert metrics["status"] == {"2xx": 2, "4xx": 1, "5xx": 0}
    assert sum(entry["requests"] for entry in metrics["by_model"].values()) == 2


def test_metrics_never_contain_the_question_the_answer_the_key_or_tool_arguments(
    make_client,
):
    client = make_client(api_key=STAFF_KEY, API_KEYS=f"staff:{STAFF_KEY}")
    answer = client.post("/ask", json={"question": POLICY_QUESTION}).json()

    metrics = client.get("/metrics").json()

    assert metrics["tools"] == {"get_policy": 1}
    metrics_text = json.dumps(metrics, ensure_ascii=False)
    private = (POLICY_QUESTION, answer["answer"], STAFF_KEY, "POL-003", "Aguinaldo")
    for text in private:
        assert text not in metrics_text
