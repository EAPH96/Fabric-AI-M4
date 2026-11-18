"""Pruebas del log JSON: una línea por evento con los campos comunes."""

import io
import json
from datetime import datetime, timedelta

from app.logs import JsonLogger


def test_each_event_is_one_json_line_with_utc_time_and_service(clock):
    stream = io.StringIO()
    logger = JsonLogger(stream=stream, clock=clock, service="people-desk")

    logger.event("audit", "req-1", action="tool_call", tool="get_employee")
    logger.event("request", "req-2", status=200)

    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["event"] == "audit"
    assert first["request_id"] == "req-1"
    assert (first["action"], first["tool"]) == ("tool_call", "get_employee")
    assert (second["event"], second["status"]) == ("request", 200)
    for line in (first, second):
        assert line["service"] == "people-desk"
        timestamp = datetime.fromisoformat(line["ts"])
        assert timestamp == clock.now()
        assert timestamp.utcoffset() == timedelta(0)
