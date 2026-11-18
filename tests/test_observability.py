"""Pruebas del id por petición y del middleware que registra cada respuesta."""

import uuid

import pytest

from app.observability import resolve_request_id


@pytest.mark.parametrize(
    "header",
    ["x" * 129, "id with spaces"],
    ids=["longer_than_128_characters", "with_spaces"],
)
def test_malformed_client_request_id_is_replaced_by_a_uuid(header):
    request_id = resolve_request_id(header)

    assert request_id != header
    assert str(uuid.UUID(request_id)) == request_id


def test_rejected_question_still_gets_a_request_id_and_a_request_line(
    client, log_events
):
    response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422
    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(request_id)
    request_lines = [
        (event["status"], event["request_id"])
        for event in log_events()
        if event["event"] == "request"
    ]
    assert request_lines == [(422, request_id)]
