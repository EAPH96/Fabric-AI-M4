"""Pruebas de las métricas en memoria del proceso.

Desde la especificación 07 también cubren las métricas de negocio:
``by_model``, ``cached_calls``, ``stopped``, ``tools`` y ``status``.
"""

import threading

from app import metrics as metrics_module
from app.metrics import Metrics

SLO_P95_MS = 2000
SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
THREADS = 20
CALLS_PER_THREAD = 50


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


def test_business_metrics_start_empty_with_every_status_class_at_zero():
    snapshot = Metrics().snapshot(SLO_P95_MS)

    assert snapshot["by_model"] == {}
    assert snapshot["tools"] == {}
    assert snapshot["cached_calls"] == 0
    assert snapshot["stopped"] == 0
    assert snapshot["status"] == {"2xx": 0, "4xx": 0, "5xx": 0}


def test_answers_add_requests_and_unrounded_cost_per_model():
    metrics = Metrics()
    metrics.record_answer(SMALL, 1e-7, 0, [], False)
    metrics.record_answer(SMALL, 2e-7, 0, [], False)
    metrics.record_answer(LARGE, 3e-5, 0, [], False)

    by_model = metrics.snapshot(SLO_P95_MS)["by_model"]

    assert by_model == {
        SMALL: {"requests": 2, "cost_usd": 1e-7 + 2e-7},
        LARGE: {"requests": 1, "cost_usd": 3e-5},
    }


def test_answers_add_their_cost_to_the_total_cost():
    metrics = Metrics()
    metrics.record_answer(SMALL, 1e-7, 0, [], False)
    metrics.record_answer(LARGE, 2e-7, 0, [], False)

    assert metrics.snapshot(SLO_P95_MS)["cost_usd"] == 1e-7 + 2e-7


def test_a_repeated_tool_counts_twice_and_no_tools_add_no_keys():
    metrics = Metrics()
    metrics.record_answer(SMALL, 0.0, 0, ["get_employee", "get_employee"], False)
    metrics.record_answer(SMALL, 0.0, 0, [], False)
    metrics.record_answer(LARGE, 0.0, 0, ["search_by_department"], False)

    tools = metrics.snapshot(SLO_P95_MS)["tools"]

    assert tools == {"get_employee": 2, "search_by_department": 1}


def test_only_cut_answers_are_stopped_and_cached_calls_accumulate():
    metrics = Metrics()
    metrics.record_answer(SMALL, 0.0, 2, ["get_employee"], True)
    metrics.record_answer(SMALL, 0.0, 1, [], False)

    snapshot = metrics.snapshot(SLO_P95_MS)

    assert snapshot["stopped"] == 1
    assert snapshot["cached_calls"] == 3


def test_status_class_groups_codes_and_sends_redirects_to_2xx():
    expected = {
        200: "2xx",
        307: "2xx",
        401: "4xx",
        422: "4xx",
        429: "4xx",
        500: "5xx",
        502: "5xx",
    }

    classes = {status: metrics_module.status_class(status) for status in expected}
    assert classes == expected


def test_status_classes_add_up_to_the_requests_with_mixed_codes():
    metrics = Metrics()
    for status in (200, 200, 307, 401, 422, 429, 500, 502):
        metrics.record_request(status, 5.0)

    snapshot = metrics.snapshot(SLO_P95_MS)

    assert snapshot["status"] == {"2xx": 3, "4xx": 3, "5xx": 2}
    assert sum(snapshot["status"].values()) == snapshot["requests"]


def test_snapshot_returns_copies_of_the_business_metrics():
    metrics = Metrics()
    metrics.record_request(200, 5.0)
    metrics.record_answer(SMALL, 1e-6, 0, ["get_employee"], False)
    first = metrics.snapshot(SLO_P95_MS)

    first["by_model"][SMALL]["requests"] = 99
    first["by_model"]["invented"] = {"requests": 1, "cost_usd": 1.0}
    first["tools"]["get_employee"] = 99
    first["status"]["2xx"] = 99

    second = metrics.snapshot(SLO_P95_MS)
    assert second["by_model"] == {SMALL: {"requests": 1, "cost_usd": 1e-6}}
    assert second["tools"] == {"get_employee": 1}
    assert second["status"] == {"2xx": 1, "4xx": 0, "5xx": 0}


def test_concurrent_records_keep_exact_totals():
    metrics = Metrics()

    def work():
        for _ in range(CALLS_PER_THREAD):
            metrics.record_request(200, 1.0)
            metrics.record_answer(SMALL, 0.5, 1, ["get_employee"], True)

    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    total = THREADS * CALLS_PER_THREAD
    snapshot = metrics.snapshot(SLO_P95_MS)
    assert snapshot["requests"] == total
    assert snapshot["status"] == {"2xx": total, "4xx": 0, "5xx": 0}
    expected_cost = total * 0.5
    assert snapshot["by_model"] == {
        SMALL: {"requests": total, "cost_usd": expected_cost}
    }
    assert snapshot["cost_usd"] == expected_cost
    assert snapshot["cached_calls"] == total
    assert snapshot["stopped"] == total
    assert snapshot["tools"] == {"get_employee": total}
