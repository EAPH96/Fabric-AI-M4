"""Pruebas de las reglas de compliance que se revisan al arrancar.

Con ``ENVIRONMENT=production`` cada regla incumplida es una violación; en
``development`` no se aplica ninguna. La regla del modelo simulado se prueba
de punta a punta en ``features/security.feature``.
"""

import pytest

from app.compliance import compliance_violations
from app.config import load_settings

PRODUCTION_KEY = "hr-production-key-0001"
SHORT_KEY = "k" * 15


@pytest.fixture
def production_env(gateway_env):
    """Entorno de producción que cumple todas las reglas.

    :param gateway_env: Variables del gateway con valores de prueba
    :type gateway_env: dict
    :return: Variables de entorno de producción
    :rtype: dict
    """
    return {
        **gateway_env,
        "ENVIRONMENT": "production",
        "API_KEYS": f"hr:{PRODUCTION_KEY}",
    }


@pytest.mark.parametrize(
    ("change", "variable"),
    [
        ({"API_KEYS": ""}, "API_KEYS"),
        ({"API_KEYS": f"hr:{SHORT_KEY}"}, "API_KEYS"),
        ({"LANGSMITH_TRACING": "true", "HIDE_INPUTS": "false"}, "HIDE_INPUTS"),
    ],
    ids=["no_api_keys", "key_shorter_than_16", "traces_show_inputs"],
)
def test_each_broken_production_rule_is_one_violation(
    production_env, change, variable
):
    settings = load_settings({**production_env, **change})

    violations = compliance_violations(settings)

    assert len(violations) == 1
    assert variable in violations[0]
    assert SHORT_KEY not in violations[0]


def test_development_and_a_correct_production_have_no_violations(production_env):
    assert compliance_violations(load_settings({})) == []
    assert compliance_violations(load_settings(production_env)) == []
