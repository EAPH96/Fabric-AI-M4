"""Pruebas de las reglas de compliance de producción, copiadas del HR.

Cada caso parte de un entorno de producción correcto y rompe una regla; las
violaciones nombran la variable y nunca la clave.
"""

import pytest

from app.compliance import compliance_violations
from app.config import load_settings

PRODUCTION_KEY = "politicas-production-key-0001"
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
        "API_KEYS": f"staff:{PRODUCTION_KEY}",
    }


@pytest.mark.parametrize(
    ("change", "variables"),
    [
        ({"MODEL_PROVIDER": "fake"}, ["MODEL_PROVIDER"]),
        ({"API_KEYS": f"staff:{SHORT_KEY}"}, ["API_KEYS"]),
        (
            {
                "LANGSMITH_TRACING": "true",
                "HIDE_INPUTS": "false",
                "HIDE_OUTPUTS": "false",
            },
            ["HIDE_INPUTS", "HIDE_OUTPUTS"],
        ),
    ],
    ids=["fake_model", "key_shorter_than_16", "traces_show_inputs_and_outputs"],
)
def test_production_rejects_each_broken_rule_without_showing_the_key(
    production_env, change, variables
):
    assert compliance_violations(load_settings(production_env)) == []

    violations = compliance_violations(load_settings({**production_env, **change}))

    assert len(violations) == len(variables)
    for variable, violation in zip(variables, violations):
        assert variable in violation
        assert SHORT_KEY not in violation
