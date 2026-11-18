"""Pruebas de las trazas opcionales en LangSmith, sin red y sin la librería real.

``build_tracer`` recibe un ``importer``: aquí se inyecta uno que devuelve un
módulo ``langsmith`` falso y anota qué se importó.
"""

import types

from app.config import load_settings
from app.observability import Observability, RequestObserver
from app.tracing import LangSmithTracer, NullTracer, build_tracer

EXAMPLE_KEY = "lsv2-example-key-not-real"


def fake_langsmith():
    """Crea un módulo ``langsmith`` falso que anota cómo se usa.

    :return: Módulo con ``Client``, ``traceable`` y el registro ``calls``
    :rtype: types.SimpleNamespace
    """
    calls = {"client": None, "traceable": []}
    client = object()

    def make_client(**options):
        calls["client"] = options
        return client

    def traceable(function=None, **options):
        calls["traceable"].append(options)
        if function is not None:
            return function

        def decorator(wrapped):
            return wrapped

        return decorator

    return types.SimpleNamespace(
        Client=make_client, traceable=traceable, calls=calls, client=client
    )


def recording_importer(module, imported):
    """Crea un importador que devuelve ``module`` y anota cada nombre pedido."""

    def _import(name):
        imported.append(name)
        return module

    return _import


def lookup(employee_id):
    """Herramienta de ejemplo para envolver."""
    return f"found {employee_id}"


def test_tracing_without_a_key_never_imports_langsmith():
    imported = []
    settings = load_settings({"LANGSMITH_TRACING": "true"})

    tracer = build_tracer(settings, importer=recording_importer(None, imported))
    traced = tracer.wrap(lookup, run_type="tool", request_id="req-7")

    assert isinstance(tracer, NullTracer)
    assert not imported
    assert traced("EMP-0004") == "found EMP-0004"


def test_tracing_with_a_key_hides_content_and_tags_the_request_id():
    imported = []
    langsmith = fake_langsmith()
    settings = load_settings(
        {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": EXAMPLE_KEY}
    )

    tracer = build_tracer(settings, importer=recording_importer(langsmith, imported))
    traced = tracer.wrap(lookup, run_type="tool", request_id="req-7")

    assert imported == ["langsmith"]
    client_options = langsmith.calls["client"]
    assert client_options["api_key"] == EXAMPLE_KEY
    assert client_options["hide_inputs"] is True
    assert client_options["hide_outputs"] is True
    (trace_options,) = langsmith.calls["traceable"]
    assert trace_options["run_type"] == "tool"
    assert trace_options["metadata"]["request_id"] == "req-7"
    assert trace_options["client"] is langsmith.client
    assert traced("EMP-0004") == "found EMP-0004"


def test_trace_metadata_names_the_request_id_and_the_client():
    langsmith = fake_langsmith()
    tracer = LangSmithTracer(langsmith.traceable, langsmith.client)
    observability = Observability(
        clock=None, logger=None, metrics=None, tracer=tracer
    )
    observer = RequestObserver(observability, "req-7", client="hr")

    traced = observer.wrap(lookup, run_type="tool")

    (trace_options,) = langsmith.calls["traceable"]
    assert trace_options["metadata"] == {"request_id": "req-7", "client": "hr"}
    assert traced("EMP-0004") == "found EMP-0004"
