"""Pruebas de la configuración nueva de la sesión 3: modelos, palancas y gateway.

La configuración de costos vive en ``settings.costs``, con tres grupos:
``routing``, ``call`` y ``gateway``, más ``prices_path``.
"""

from pathlib import Path

import pytest

from app.config import ConfigError, load_settings

PRODUCT_DIR = Path(__file__).resolve().parents[1]


def test_cost_defaults_match_the_specification():
    costs = load_settings({}).costs

    assert costs.routing.model_small == "@cf/meta/llama-3.1-8b-instruct-fast"
    assert costs.routing.model_large == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert costs.routing.enabled is True
    assert costs.routing.max_chars == 80
    assert costs.call.history_window == 6
    assert costs.call.max_tokens == 300
    assert costs.call.temperature == 0
    assert costs.call.cache_ttl_seconds == 0
    assert costs.gateway.gateway_id == "default"
    assert not costs.gateway.account_id
    assert not costs.gateway.api_token
    expected_prices = (PRODUCT_DIR / "data" / "model_prices.json").resolve()
    assert Path(costs.prices_path).resolve() == expected_prices


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CF_ACCOUNT_ID", ""),
        ("CF_API_TOKEN", ""),
        ("CF_ACCOUNT_ID", "acct/../admin"),
        ("CF_GATEWAY_ID", "gw?x=1"),
    ],
    ids=[
        "missing_account",
        "missing_token",
        "account_with_a_path",
        "gateway_id_with_a_query",
    ],
)
def test_gateway_with_a_missing_or_unsafe_cloudflare_variable_prevents_start(
    variable, value, gateway_env
):
    gateway_env[variable] = value

    with pytest.raises(ConfigError, match=variable):
        load_settings(gateway_env)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("HISTORY_WINDOW", "-1"),
        ("MODEL_TEMPERATURE", "abc"),
        ("MODEL_MAX_TOKENS", "0"),
        ("ROUTER_MAX_CHARS", "0"),
        ("ROUTING", "maybe"),
        ("CACHE_TTL_SECONDS", "-5"),
    ],
    ids=[
        "negative_history_window",
        "temperature_that_is_not_a_number",
        "zero_output_cap",
        "zero_routing_limit",
        "routing_flag_that_is_not_a_boolean",
        "negative_cache_ttl",
    ],
)
def test_invalid_cost_setting_prevents_start_with_a_clear_message(variable, value):
    with pytest.raises(ConfigError, match=variable):
        load_settings({variable: value})


def test_zero_history_window_is_accepted():
    settings = load_settings({"HISTORY_WINDOW": "0"})

    assert settings.costs.call.history_window == 0


def test_cloudflare_token_is_read_but_never_shown_in_the_settings(gateway_env):
    settings = load_settings(gateway_env)

    assert settings.model_provider == "gateway"
    assert settings.costs.gateway.api_token == gateway_env["CF_API_TOKEN"]
    assert gateway_env["CF_API_TOKEN"] not in repr(settings)
    assert gateway_env["CF_API_TOKEN"] not in str(settings)
