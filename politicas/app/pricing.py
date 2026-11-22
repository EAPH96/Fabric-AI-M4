"""Precios por modelo y medidor del costo de cada respuesta (ADR 0009 del HR).

Los precios viven en ``PRICES_PATH`` (USD por millón de tokens), no en el
código. ``CostMeter`` envuelve el modelo elegido para una petición: el agente no
sabe de precios, igual que no sabe de trazas.
"""

import json
from pathlib import Path

from app.config import ConfigError

TOKENS_PER_PRICE_UNIT = 1_000_000
PRICE_FIELDS = ("input", "output")


def _price(model, entry):
    """Valida el precio de un modelo del archivo.

    :param model: Nombre del modelo
    :type model: str
    :param entry: Entrada del archivo con ``input`` y ``output``
    :type entry: object
    :return: Precio de entrada y de salida por millón de tokens
    :rtype: tuple[float, float]
    :raises ConfigError: Si falta un precio o no es un número mayor o igual que 0
    """
    if not isinstance(entry, dict):
        raise ConfigError(f"PRICES_PATH: price of {model!r} must be an object")
    prices = []
    for name in PRICE_FIELDS:
        value = entry.get(name)
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_number or value < 0:
            raise ConfigError(
                f"PRICES_PATH: {name} price of {model!r} must be a number >= 0"
            )
        prices.append(float(value))
    return prices[0], prices[1]


class PriceTable:
    """Tabla de precios por modelo, en USD por millón de tokens.

    :param prices: Precio de entrada y de salida de cada modelo
    :type prices: dict[str, tuple[float, float]]
    """

    def __init__(self, prices):
        self._prices = dict(prices)

    @classmethod
    def from_file(cls, path, required_models):
        """Carga la tabla y exige precio para cada modelo que se va a usar.

        Así un modelo sin precio impide arrancar, en lugar de costar 0 en
        silencio.

        :param path: Archivo con el formato de ``spec/model_prices.json``
        :type path: str or pathlib.Path
        :param required_models: Modelos que deben tener precio
        :type required_models: collections.abc.Iterable[str]
        :return: Tabla de precios validada
        :rtype: PriceTable
        :raises ConfigError: Si el archivo no se puede leer, no tiene el formato
            esperado o le falta el precio de un modelo requerido
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigError(f"PRICES_PATH could not be read: {path}") from error
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            raise ConfigError("PRICES_PATH must have a 'models' object")
        prices = {model: _price(model, entry) for model, entry in models.items()}
        missing = [model for model in required_models if model not in prices]
        if missing:
            raise ConfigError(
                f"PRICES_PATH has no price for model(s): {', '.join(missing)}"
            )
        return cls(prices)

    def cost_usd(self, model, input_tokens, output_tokens):
        """Calcula el costo de una llamada, sin redondear.

        Una pregunta corta cuesta del orden de 1e-7 USD: redondear la dejaría
        en 0.

        :param model: Nombre del modelo
        :type model: str
        :param input_tokens: Tokens de entrada
        :type input_tokens: int
        :param output_tokens: Tokens de salida
        :type output_tokens: int
        :return: Costo en USD
        :rtype: float
        :raises KeyError: Si el modelo no está en la tabla
        """
        input_price, output_price = self._prices[model]
        total = input_tokens * input_price + output_tokens * output_price
        return total / TOKENS_PER_PRICE_UNIT


class CostMeter:
    """Envuelve un modelo y suma el costo de las llamadas de una petición.

    Las llamadas servidas por la caché del gateway se cuentan en
    ``cached_calls`` y no cuestan.

    :param model: Modelo que atiende la petición
    :type model: app.llm.ChatModel
    :param prices: Tabla de precios
    :type prices: PriceTable
    :param model_name: Nombre con el que se busca el precio
    :type model_name: str
    """

    def __init__(self, model, prices, model_name):
        self._model = model
        self._prices = prices
        self._model_name = model_name
        self.cached_calls = 0
        self.cost_usd = 0.0

    def complete(self, messages):
        """Delega la llamada en el modelo y anota su costo.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: La misma respuesta del modelo
        :rtype: app.llm.Completion
        """
        completion = self._model.complete(messages)
        if completion.cached:
            self.cached_calls += 1
        else:
            self.cost_usd += self._prices.cost_usd(
                self._model_name, completion.input_tokens, completion.output_tokens
            )
        return completion
