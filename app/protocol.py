"""Piezas del protocolo que comparten el agente y todos los modelos.

Viven aparte para que ``llm.py`` (que arma los modelos) y ``gateway.py`` (el
modelo real) las usen sin importarse entre sí. ``app.llm`` las vuelve a
exponer, así que el resto del código las sigue importando desde ahí.
"""

from dataclasses import dataclass

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "


@dataclass(frozen=True)
class Completion:
    """Respuesta de una llamada al modelo.

    :param text: Texto del modelo (un objeto JSON)
    :type text: str
    :param input_tokens: Tokens de entrada contados
    :type input_tokens: int
    :param output_tokens: Tokens de salida contados
    :type output_tokens: int
    :param cached: ``True`` si la respuesta salió de la caché del gateway (no
        cuesta, pero sus tokens se siguen contando)
    :type cached: bool
    """

    text: str
    input_tokens: int
    output_tokens: int
    cached: bool = False
