"""Pruebas de la tabla de precios y del medidor de costo por respuesta."""

import json

import pytest

from app.config import ConfigError
from app.llm import Completion
from app.pricing import CostMeter, PriceTable

SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
PRICES = {
    "currency": "USD",
    "unit": "per million tokens",
    "models": {
        SMALL: {"input": 0.045, "output": 0.384},
        LARGE: {"input": 0.293, "output": 2.253},
    },
}


@pytest.fixture
def prices_file(tmp_path):
    """Archivo de precios con el mismo formato que ``spec/model_prices.json``."""
    path = tmp_path / "model_prices.json"
    path.write_text(json.dumps(PRICES), encoding="utf-8")
    return path


class ScriptedModel:
    """Modelo de prueba que devuelve las respuestas indicadas, en orden."""

    def __init__(self, completions):
        self._completions = list(completions)

    def complete(self, messages):  # pylint: disable=unused-argument
        """Devuelve la siguiente respuesta del guion."""
        return self._completions.pop(0)


def test_cost_is_charged_per_million_tokens_without_rounding(prices_file):
    table = PriceTable.from_file(prices_file, [SMALL, LARGE])

    assert table.cost_usd(SMALL, 1_000_000, 0) == pytest.approx(0.045)
    assert table.cost_usd(LARGE, 0, 1_000_000) == pytest.approx(2.253)
    # 10 * 0.045 + 5 * 0.384 = 2.37 millonésimas: redondear a 6 decimales daría 2e-6.
    assert table.cost_usd(SMALL, 10, 5) == pytest.approx(2.37e-6)


def test_model_without_a_price_prevents_start(prices_file):
    with pytest.raises(ConfigError, match="unknown-model"):
        PriceTable.from_file(prices_file, [SMALL, "unknown-model"])


def test_cost_meter_charges_only_the_calls_that_were_not_cached(prices_file):
    table = PriceTable.from_file(prices_file, [SMALL, LARGE])
    cached = Completion(text="{}", input_tokens=1000, output_tokens=100, cached=True)
    paid = Completion(text="{}", input_tokens=1000, output_tokens=100)
    meter = CostMeter(ScriptedModel([cached, paid]), table, SMALL)
    messages = [{"role": "user", "content": "Hola"}]

    replies = [meter.complete(messages), meter.complete(messages)]

    assert replies == [cached, paid]
    assert meter.cached_calls == 1
    assert meter.cost_usd == pytest.approx(table.cost_usd(SMALL, 1000, 100))
