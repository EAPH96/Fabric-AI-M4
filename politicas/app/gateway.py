"""Modelo real: Workers AI a través de Cloudflare AI Gateway (ADR 0008 del HR).

``GatewayModel`` cumple ``complete(messages)`` igual que el simulado. Recibe el
cliente HTTP ya creado, así las pruebas inyectan un ``httpx.MockTransport`` y
nunca usan la red. Cualquier falla lanza ``ModelUnavailableError``, sin
reintentos y sin URL ni token en el mensaje.
"""

import re

import httpx

from app.protocol import TOOL_RESULT_PREFIX, Completion

GATEWAY_URL_TEMPLATE = (
    "https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}"
    "/workers-ai/v1/chat/completions"
)
GATEWAY_TIMEOUT_SECONDS = 30.0
CACHE_TTL_HEADER = "cf-aig-cache-ttl"
CACHE_STATUS_HEADER = "cf-aig-cache-status"
CACHE_HIT = "HIT"
CODE_FENCE_PATTERN = re.compile(r"\A```[A-Za-z0-9_-]*\s*(.*?)\s*```\Z", re.DOTALL)
SYSTEM_PROMPT = (
    "You are the HR policies assistant of a company. You answer questions "
    "about the company policies (vacations, bonuses, working hours, leaves "
    "and others) using only the policy catalog. Reply with exactly one JSON "
    "object and nothing else: no code fences, no extra text.\n"
    'To use a tool reply {"tool": "<name>", "args": {...}}. Tools:\n'
    "- search_policies: the id and title of the policies about a topic, args "
    '{"topic": "vacaciones"}. Write topics in Spanish.\n'
    '- get_policy: one policy by id, args {"policy_id": "POL-001"}.\n'
    f"Tool results arrive as user messages that start with {TOOL_RESULT_PREFIX!r}."
    "\n"
    'To answer the person reply {"answer": "<text in Spanish>"}. Cite the id '
    "of every policy you used (for example POL-001). Never invent data that "
    "is not in a tool result."
)


class ModelUnavailableError(RuntimeError):
    """El gateway no respondió o respondió algo que no se puede usar."""


def strip_code_fences(text):
    """Quita los cercos de código que a veces agrega el modelo.

    :param text: Texto del modelo
    :type text: str
    :return: Texto sin cercos ni espacios en los extremos
    :rtype: str
    """
    stripped = text.strip()
    match = CODE_FENCE_PATTERN.match(stripped)
    return match.group(1) if match else stripped


def _parse_response(response):
    """Saca el texto, los tokens y si salió de la caché de una respuesta.

    :param response: Respuesta HTTP del gateway
    :type response: httpx.Response
    :return: Respuesta del modelo
    :rtype: app.protocol.Completion
    :raises httpx.HTTPStatusError: Si el estado no es 2xx
    :raises ValueError: Si el cuerpo no es JSON o el texto no es una cadena
    :raises KeyError: Si faltan ``choices`` o ``usage``
    :raises IndexError: Si ``choices`` está vacío
    :raises TypeError: Si el cuerpo no tiene la forma esperada
    """
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    if not isinstance(text, str):
        raise ValueError("model content is not text")
    usage = data["usage"]
    cache_status = response.headers.get(CACHE_STATUS_HEADER, "")
    return Completion(
        text=strip_code_fences(text),
        input_tokens=int(usage["prompt_tokens"]),
        output_tokens=int(usage["completion_tokens"]),
        cached=cache_status.strip().upper() == CACHE_HIT,
    )


class GatewayModel:
    """Modelo de Workers AI que se llama a través de AI Gateway.

    :param name: Nombre del modelo en Workers AI (también su precio)
    :type name: str
    :param settings: Configuración de costos (gateway y palancas de llamada)
    :type settings: app.config.CostSettings
    :param http_client: Cliente HTTP; en pruebas usa ``httpx.MockTransport``
    :type http_client: httpx.Client
    """

    def __init__(self, name, settings, http_client):
        self.name = name
        self._call = settings.call
        self._http_client = http_client
        self._url = GATEWAY_URL_TEMPLATE.format(
            account_id=settings.gateway.account_id,
            gateway_id=settings.gateway.gateway_id,
        )
        self._headers = {"Authorization": f"Bearer {settings.gateway.api_token}"}
        if settings.call.cache_ttl_seconds > 0:
            self._headers[CACHE_TTL_HEADER] = str(settings.call.cache_ttl_seconds)

    def complete(self, messages):
        """Pide al modelo el siguiente paso de la conversación.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Texto del modelo, tokens de ``usage`` y si salió de la caché
        :rtype: app.protocol.Completion
        :raises ModelUnavailableError: Si hay error de red, tiempo agotado,
            estado no 2xx o una respuesta sin los campos esperados
        """
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        conversation.extend(
            {"role": message["role"], "content": message["content"]}
            for message in messages
        )
        body = {
            "model": self.name,
            "messages": conversation,
            "max_tokens": self._call.max_tokens,
            "temperature": self._call.temperature,
        }
        try:
            response = self._http_client.post(
                self._url,
                json=body,
                headers=self._headers,
                timeout=GATEWAY_TIMEOUT_SECONDS,
            )
            return _parse_response(response)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            # Solo el tipo: el mensaje original puede traer la URL de la cuenta.
            raise ModelUnavailableError(
                f"model gateway call failed ({type(error).__name__})"
            ) from error


def build_http_client():
    """Crea el cliente HTTP de producción para el gateway.

    :return: Cliente con el tiempo máximo de espera del gateway
    :rtype: httpx.Client
    """
    return httpx.Client(timeout=GATEWAY_TIMEOUT_SECONDS)
