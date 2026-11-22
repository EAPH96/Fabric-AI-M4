"""Pruebas de las trazas opcionales en LangSmith, sin red y sin la librería real.

``build_tracer`` recibe un ``importer``: aquí se inyecta uno que devuelve un
módulo ``langsmith`` falso y anota qué se importó.
"""

import types

from app.config import load_settings
from app.tracing import NullTracer, build_tracer

EXAMPLE_KEY = "lsv2-example-key-not-real"


def fake_langsmith():
    """Crea un módulo ``langsmith`` falso que anota las opciones de ``traceable``.

    :return: Módulo con ``Client``, ``traceable`` y la lista ``traced``
    :rtype: types.SimpleNamespace
    """
    traced = []

    def traceable(**options):
        traced.append(options)
        return lambda function: function

    return types.SimpleNamespace(
        Client=lambda **options: object(), traceable=traceable, traced=traced
    )


def recording_importer(module, imported):
    """Crea un importador que devuelve ``module`` y anota cada nombre pedido."""

    def _import(name):
        imported.append(name)
        return module

    return _import


def lookup(policy_id):
    """Herramienta de ejemplo para envolver."""
    return f"found {policy_id}"


def test_tracing_is_off_by_default_and_never_imports_langsmith():
    imported = []
    importer = recording_importer(None, imported)

    tracer = build_tracer(load_settings({}), importer=importer)

    assert isinstance(tracer, NullTracer)
    assert not imported


def test_traces_go_to_the_project_named_by_langsmith_project():
    langsmith = fake_langsmith()
    settings = load_settings(
        {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": EXAMPLE_KEY,
            "LANGSMITH_PROJECT": "politicas-demo",
        }
    )

    tracer = build_tracer(settings, importer=recording_importer(langsmith, []))
    traced = tracer.wrap(lookup, run_type="tool", request_id="req-7")

    (options,) = langsmith.traced
    assert options["project_name"] == "politicas-demo"
    assert traced("POL-001") == "found POL-001"
