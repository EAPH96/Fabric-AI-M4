"""Pruebas de la configuración de seguridad: entorno, claves y límite."""

import pytest

from app.config import ConfigError, load_settings

HR_KEY = "hr-key-for-tests-0001"


def test_security_defaults_match_the_specification():
    security = load_settings({}).security

    assert security.environment == "development"
    assert not security.api_keys
    assert security.rate_limit_per_minute == 30


def test_unknown_environment_or_zero_rate_limit_prevents_start():
    with pytest.raises(ConfigError, match="ENVIRONMENT"):
        load_settings({"ENVIRONMENT": "staging"})
    with pytest.raises(ConfigError, match="RATE_LIMIT_PER_MINUTE"):
        load_settings({"RATE_LIMIT_PER_MINUTE": "0"})


def test_api_keys_are_loaded_but_never_shown_in_the_settings():
    settings = load_settings({"API_KEYS": f"hr:{HR_KEY}"})

    assert settings.security.api_keys == {"hr": HR_KEY}
    assert HR_KEY not in repr(settings)
    assert HR_KEY not in str(settings)
