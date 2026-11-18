"""Palanca 1: una regla en código elige el modelo de cada pregunta (ADR 0007).

No se usa otro modelo para decidir: la regla es pura, rápida y gratis. Una
pregunta va al modelo capaz si el enrutamiento está apagado, si es larga o si
pide comparar, resumir, explicar o analizar; si no, va al modelo barato.
"""

import unicodedata
from dataclasses import dataclass

ROUTING_KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")
REASON_DISABLED = "routing_disabled"
REASON_LONG_QUESTION = "long_question"
REASON_KEYWORD_PREFIX = "keyword:"
REASON_SIMPLE = "simple"


@dataclass(frozen=True)
class Route:
    """Modelo elegido para una pregunta y el motivo.

    :param model: Nombre del modelo que atiende la pregunta
    :type model: str
    :param reason: Motivo: ``routing_disabled``, ``long_question``,
        ``keyword:<palabra>`` o ``simple``
    :type reason: str
    """

    model: str
    reason: str


def choose_route(question, routing):
    """Elige el modelo de una pregunta; la primera regla que aplica decide.

    Las palabras clave se buscan sin distinguir mayúsculas ni la forma Unicode
    de los acentos (``POR QUÉ`` cuenta como ``por qué``).

    :param question: Pregunta de la persona
    :type question: str
    :param routing: Configuración de enrutamiento
    :type routing: app.config.RoutingSettings
    :return: Modelo elegido y motivo
    :rtype: Route
    """
    if not routing.enabled:
        return Route(routing.model_large, REASON_DISABLED)
    if len(question) > routing.max_chars:
        return Route(routing.model_large, REASON_LONG_QUESTION)
    folded = unicodedata.normalize("NFC", question).casefold()
    for keyword in ROUTING_KEYWORDS:
        if keyword in folded:
            return Route(routing.model_large, REASON_KEYWORD_PREFIX + keyword)
    return Route(routing.model_small, REASON_SIMPLE)
