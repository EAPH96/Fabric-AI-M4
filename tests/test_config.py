"""Pruebas de la configuración leída de variables de entorno."""

from pathlib import Path

import pytest

from app.config import ConfigError, load_settings

PRODUCT_DIR = Path(__file__).resolve().parents[1]


def test_default_settings_match_the_specification():
    settings = load_settings({})

    assert settings.model_provider == "fake"
    assert settings.agent_max_steps == 3
    assert settings.max_question_chars == 2000
    expected_path = (PRODUCT_DIR / "data" / "employees.json").resolve()
    assert Path(settings.employees_path).resolve() == expected_path


def test_observability_defaults_match_the_specification():
    observability = load_settings({}).observability

    assert observability.service_name == "hr-assistant"
    assert observability.slo_p95_ms == 2000
    assert observability.langsmith_tracing is False
    assert observability.hide_inputs is True
    assert observability.hide_outputs is True
    assert not observability.langsmith_api_key


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("AGENT_MAX_STEPS", "0"),
        ("AGENT_MAX_STEPS", "many"),
        ("MODEL_PROVIDER", "openai"),
        ("SLO_P95_MS", "0"),
        ("LANGSMITH_TRACING", "maybe"),
    ],
    ids=[
        "zero_steps",
        "non_numeric_steps",
        "unknown_provider",
        "zero_latency_objective",
        "tracing_flag_that_is_not_a_boolean",
    ],
)
def test_invalid_setting_prevents_start_with_a_clear_message(variable, value):
    with pytest.raises(ConfigError, match=variable):
        load_settings({variable: value})


def test_langsmith_key_is_read_but_never_shown_in_the_settings():
    secret_key = "lsv2-example-key-not-real"

    settings = load_settings({"LANGSMITH_API_KEY": secret_key})

    assert settings.observability.langsmith_api_key == secret_key
    assert secret_key not in repr(settings)
    assert secret_key not in str(settings)
