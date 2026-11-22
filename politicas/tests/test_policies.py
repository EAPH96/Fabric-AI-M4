"""Pruebas del catálogo de políticas de solo lectura (``app/policies.py``).

Usan el ``data/policies.json`` real: diez políticas de ``POL-001`` a ``POL-010``.
Un id desconocido se prueba a través del agente (``test_agent.py``) y del
escenario de ``POL-999``.
"""

import json

import pytest

from app.policies import PolicyCatalog, normalize

AGUINALDO_TEXT = (
    "El aguinaldo equivale a 15 días de salario y se paga antes del 20 de "
    "diciembre. Quien no completó el año recibe la parte proporcional al tiempo "
    "trabajado."
)


def test_a_file_that_is_not_a_list_raises_value_error(tmp_path):
    path = tmp_path / "policies.json"
    path.write_text(json.dumps({"id": "POL-001"}), encoding="utf-8")

    with pytest.raises(ValueError):
        PolicyCatalog(path)


def test_get_policy_returns_only_id_title_and_text_as_a_copy(catalog):
    policy = catalog.get_policy("POL-003")
    policy["title"] = "Cambiado por la prueba"

    assert catalog.get_policy("POL-003") == {
        "id": "POL-003",
        "title": "Aguinaldo",
        "text": AGUINALDO_TEXT,
    }


def test_search_ignores_case_and_accents(catalog):
    assert normalize("  Viáticos ") == "viaticos"
    assert catalog.search("VIATICOS") == [{"id": "POL-010", "title": "Viáticos"}]


def test_search_by_keyword_returns_only_id_and_title_and_unknown_topic_is_empty(
    catalog,
):
    assert catalog.search("papá") == [
        {"id": "POL-006", "title": "Permiso de paternidad"}
    ]
    assert catalog.search("astronautas") == []


def test_terms_follow_the_order_of_the_file(catalog):
    terms = list(dict.fromkeys(catalog.terms()))

    assert terms[:5] == [
        "vacaciones",
        "días de descanso pagados",
        "prima vacacional",
        "prima",
        "aguinaldo",
    ]
    assert terms[-1] == "comprobación"
