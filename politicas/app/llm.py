"""Interfaz del modelo de lenguaje, modelo simulado y fábrica de modelos.

El agente solo conoce ``ChatModel.complete(messages)``. El modelo responde
siempre un único objeto JSON: ``{"tool": ..., "args": {...}}`` para pedir una
herramienta o ``{"answer": ...}`` para responder.

``build_models`` crea un modelo por nombre (``MODEL_SMALL`` y ``MODEL_LARGE``),
simulado o real, para que el enrutador elija por nombre en los dos casos.
"""

import json
import re
from typing import Protocol

from app.config import FAKE_PROVIDER, GATEWAY_PROVIDER, ConfigError
from app.gateway import GatewayModel, build_http_client
from app.policies import normalize
from app.protocol import TOOL_RESULT_PREFIX, Completion

__all__ = [
    "ChatModel",
    "Completion",
    "FakeModel",
    "TOOL_RESULT_PREFIX",
    "build_models",
    "count_words",
]

POLICIES_ANSWER_PREFIX = "Según las políticas: "
HELP_ANSWER = "Pregúntame por una política (POL-001) o un tema, como vacaciones."
POLICY_ID_PATTERN = re.compile(r"POL-[0-9]{3}")
FAKE_MODEL_NAME = "fake"


class ChatModel(Protocol):  # pylint: disable=too-few-public-methods
    """Interfaz que debe cumplir cualquier modelo que use el agente."""

    def complete(self, messages: list[dict]) -> Completion:
        """Pide al modelo el siguiente paso de la conversación.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Texto del modelo y tokens usados
        :rtype: Completion
        """


def count_words(text):
    """Cuenta palabras separadas por espacios, como aproximación de tokens.

    :param text: Texto a contar
    :type text: str
    :return: Número de palabras
    :rtype: int
    """
    return len(str(text).split())


class FakeModel:  # pylint: disable=too-few-public-methods
    """Modelo simulado: decide con reglas fijas sobre el último mensaje.

    Las reglas se evalúan en orden estricto: resultado de herramienta, id de
    política, tema conocido y, si nada aplica, la ayuda. El nombre no cambia
    las respuestas: solo sirve para buscar su precio.

    :param terms: Topics y keywords de las políticas, en el orden del archivo
    :type terms: list[str]
    :param name: Nombre del modelo simulado
    :type name: str
    """

    def __init__(self, terms, name=FAKE_MODEL_NAME):
        self._terms = tuple((term, normalize(term)) for term in terms)
        self.name = name

    def complete(self, messages):
        """Responde según las reglas de la especificación.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Objeto JSON con ``tool`` o ``answer`` y el conteo de tokens
        :rtype: Completion
        """
        last = str(messages[-1]["content"]) if messages else ""
        text = json.dumps(self._decide(last), ensure_ascii=False)
        input_tokens = sum(count_words(message["content"]) for message in messages)
        return Completion(
            text=text, input_tokens=input_tokens, output_tokens=count_words(text)
        )

    def _decide(self, last):
        """Aplica las cuatro reglas al último mensaje.

        :param last: Contenido del último mensaje
        :type last: str
        :return: Petición de herramienta o respuesta
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            result = last[len(TOOL_RESULT_PREFIX):]
            return {"answer": POLICIES_ANSWER_PREFIX + result}
        match = POLICY_ID_PATTERN.search(last)
        if match:
            return {"tool": "get_policy", "args": {"policy_id": match.group()}}
        topic = self._find_topic(last)
        if topic:
            return {"tool": "search_policies", "args": {"topic": topic}}
        return {"answer": HELP_ANSWER}

    def _find_topic(self, text):
        """Busca el primer término mencionado en el texto, sin acentos ni mayúsculas.

        :param text: Texto donde buscar
        :type text: str
        :return: Término tal como está escrito en el archivo, o ``None``
        :rtype: str or None
        """
        folded = normalize(text)
        for term, normalized in self._terms:
            if normalized and normalized in folded:
                return term
        return None


def build_models(settings, catalog, http_client=None):
    """Construye un modelo por cada nombre de ``MODEL_SMALL`` y ``MODEL_LARGE``.

    Con ``fake`` son dos modelos simulados que responden igual; con
    ``gateway`` son dos ``GatewayModel`` que comparten el cliente HTTP.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param catalog: Catálogo de políticas (da los topics y keywords)
    :type catalog: app.policies.PolicyCatalog
    :param http_client: Cliente HTTP para el gateway; si es ``None`` se crea
        uno con ``build_http_client``. El modelo simulado no lo usa.
    :type http_client: httpx.Client or None
    :return: Modelos por nombre
    :rtype: dict[str, ChatModel]
    :raises ConfigError: Si el proveedor no está soportado
    """
    routing = settings.costs.routing
    names = (routing.model_small, routing.model_large)
    if settings.model_provider == FAKE_PROVIDER:
        terms = catalog.terms()
        return {name: FakeModel(terms, name) for name in names}
    if settings.model_provider == GATEWAY_PROVIDER:
        client = build_http_client() if http_client is None else http_client
        return {name: GatewayModel(name, settings.costs, client) for name in names}
    raise ConfigError(
        f"MODEL_PROVIDER {settings.model_provider!r} is not supported"
    )
