"""Pruebas de las métricas en memoria del proceso."""

from app.metrics import Metrics

SLO_P95_MS = 2000


def test_percentiles_use_the_nearest_rank():
    metrics = Metrics()
    for latency in range(1, 101):
        metrics.record_request(200, float(latency))

    snapshot = metrics.snapshot(SLO_P95_MS)

    assert snapshot["requests"] == 100
    assert snapshot["latency_ms"] == {"p50": 50, "p95": 95}


def test_metrics_without_requests_report_zeros_and_meet_the_objective():
    snapshot = Metrics().snapshot(SLO_P95_MS)

    assert snapshot["requests"] == 0
    assert snapshot["error_rate"] == 0.0
    assert snapshot["latency_ms"] == {"p50": 0, "p95": 0}
    assert snapshot["tokens"] == {"input": 0, "output": 0}
    assert snapshot["slo"] == {"p95_ms_target": SLO_P95_MS, "met": True}


def test_error_rate_counts_only_server_errors():
    metrics = Metrics()
    for status in (200, 404, 422, 500):
        metrics.record_request(status, 5.0)
    metrics.add_tokens(30, 12)

    snapshot = metrics.snapshot(SLO_P95_MS)

    assert snapshot["error_rate"] == 0.25
    assert snapshot["tokens"] == {"input": 30, "output": 12}


def test_objective_is_missed_when_p95_reaches_the_target():
    metrics = Metrics()
    metrics.record_request(200, float(SLO_P95_MS))

    assert metrics.snapshot(SLO_P95_MS)["slo"]["met"] is False
    assert metrics.snapshot(SLO_P95_MS + 1)["slo"]["met"] is True
