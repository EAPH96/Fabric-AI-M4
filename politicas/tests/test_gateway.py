"""Pruebas del modelo real a través de AI Gateway, sin red.

El gateway es el ``FakeGateway`` de ``conftest.py`` (``httpx.MockTransport``);
los modelos se construyen con ``build_models`` igual que en producción.
"""

import json

import pytest

from app.config import load_settings
from app.gateway import ModelUnavailableError
from app.llm import build_models

SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
QUESTION = [{"role": "user", "content": "¿Cuántos días de vacaciones me tocan?"}]


def small_model(gateway_env, catalog, fake_gateway):
    """Modelo pequeño del gateway, conectado al gateway simulado."""
    settings = load_settings(gateway_env)
    models = build_models(settings, catalog, http_client=fake_gateway.client())
    return models[SMALL]


def test_gateway_body_carries_the_system_prompt_with_both_tools(
    gateway_env, catalog, fake_gateway
):
    small_model(gateway_env, catalog, fake_gateway).complete(QUESTION)

    system, *rest = fake_gateway.last_body()["messages"]
    assert system["role"] == "system"
    assert "search_policies" in system["content"]
    assert "get_policy" in system["content"]
    assert rest == QUESTION


def test_gateway_error_raises_model_unavailable_without_the_url(
    gateway_env, catalog, fake_gateway
):
    fake_gateway.status = 500
    model = small_model(gateway_env, catalog, fake_gateway)

    with pytest.raises(ModelUnavailableError) as raised:
        model.complete(QUESTION)

    message = str(raised.value)
    assert "gateway.ai.cloudflare.com" not in message
    assert gateway_env["CF_API_TOKEN"] not in message


def test_code_fences_are_removed_from_the_model_text(
    gateway_env, catalog, fake_gateway
):
    fake_gateway.content = '```json\n{"answer": "Según POL-001"}\n```'

    completion = small_model(gateway_env, catalog, fake_gateway).complete(QUESTION)

    assert json.loads(completion.text) == {"answer": "Según POL-001"}
