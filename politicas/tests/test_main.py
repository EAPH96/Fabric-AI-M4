"""Pruebas de la API web de Políticas armada con ``create_app()``.

Recorren el middleware, la clave, el límite, el enrutador, el costo y el log,
que son los módulos copiados del HR.
"""

import os

VACATIONS = "¿Cuántos días de vacaciones me tocan?"


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
