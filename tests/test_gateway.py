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
GATEWAY_URL = (
    "https://gateway.ai.cloudflare.com/v1/acct-123/hr-gateway"
    "/workers-ai/v1/chat/completions"
)
QUESTION = [{"role": "user", "content": "¿Quién es EMP-0004?"}]


def small_model(env, directory, fake_gateway):
    """Modelo pequeño del gateway, conectado al gateway simulado."""
    settings = load_settings(env)
    models = build_models(settings, directory, http_client=fake_gateway.client())
    return models[SMALL]


def test_gateway_call_sends_the_token_and_exactly_four_body_fields(
    gateway_env, directory, fake_gateway
):
    model = small_model(
        {**gateway_env, "MODEL_MAX_TOKENS": "120"}, directory, fake_gateway
    )

    completion = model.complete(QUESTION)

    (request,) = fake_gateway.requests
    assert str(request.url) == GATEWAY_URL
    assert request.headers["Authorization"] == f"Bearer {gateway_env['CF_API_TOKEN']}"
    assert "cf-aig-cache-ttl" not in request.headers
    body = fake_gateway.last_body()
    assert set(body) == {"model", "messages", "max_tokens", "temperature"}
    assert (body["model"], body["max_tokens"], body["temperature"]) == (SMALL, 120, 0)
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][-1] == QUESTION[-1]
    assert completion.text == fake_gateway.content
    assert completion.input_tokens == fake_gateway.PROMPT_TOKENS
    assert completion.output_tokens == fake_gateway.COMPLETION_TOKENS
    assert completion.cached is False


def test_cache_ttl_is_sent_and_a_cache_hit_marks_the_call_as_cached(
    gateway_env, directory, fake_gateway
):
    fake_gateway.headers = {"cf-aig-cache-status": "HIT"}
    env = {**gateway_env, "CACHE_TTL_SECONDS": "300"}

    completion = small_model(env, directory, fake_gateway).complete(QUESTION)

    assert fake_gateway.requests[0].headers["cf-aig-cache-ttl"] == "300"
    assert completion.cached is True


def fail_with_status_500(gateway):
    """El gateway responde un error del servidor."""
    gateway.status = 500


def fail_with_timeout(gateway):
    """La llamada al gateway agota su tiempo."""
    gateway.times_out = True


def fail_without_choices(gateway):
    """El gateway responde 200 pero sin ``choices``."""
    gateway.payload = {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}


@pytest.mark.parametrize(
    "make_it_fail",
    [fail_with_status_500, fail_with_timeout, fail_without_choices],
    ids=["status_500", "timeout", "json_without_choices"],
)
def test_gateway_failure_raises_model_unavailable_without_the_token(
    make_it_fail, gateway_env, directory, fake_gateway
):
    make_it_fail(fake_gateway)
    model = small_model(gateway_env, directory, fake_gateway)

    with pytest.raises(ModelUnavailableError) as raised:
        model.complete(QUESTION)

    assert gateway_env["CF_API_TOKEN"] not in str(raised.value)
    assert len(fake_gateway.requests) == 1


def test_code_fences_are_removed_from_the_model_text(
    gateway_env, directory, fake_gateway
):
    fake_gateway.content = '```json\n{"answer": "Jorge Díaz"}\n```'

    completion = small_model(gateway_env, directory, fake_gateway).complete(QUESTION)

    assert json.loads(completion.text) == {"answer": "Jorge Díaz"}
