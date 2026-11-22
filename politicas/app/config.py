"""Configuración del Asistente de políticas de RH leída de variables de entorno.

Todas las variables tienen valores por omisión, salvo los secretos
(``LANGSMITH_API_KEY``, ``CF_API_TOKEN`` y ``API_KEYS``) y la cuenta de
Cloudflare. Un valor inválido lanza ``ConfigError`` con un mensaje que nombra la
variable, para que el proceso no arranque con una configuración rota. Los
secretos nunca aparecen en ``repr`` ni en los mensajes de error.

Cambia respecto al HR: ``POLICIES_PATH`` en lugar de ``EMPLOYEES_PATH`` y los
valores por omisión de ``SERVICE_NAME``, ``COMPANION_NAME`` y
``LANGSMITH_PROJECT``.
"""

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from app.errors import ConfigError
from app.security import parse_api_keys

PRODUCT_DIR = Path(__file__).resolve().parents[1]
FAKE_PROVIDER = "fake"
GATEWAY_PROVIDER = "gateway"
SUPPORTED_PROVIDERS = (FAKE_PROVIDER, GATEWAY_PROVIDER)

DEFAULT_MODEL_PROVIDER = FAKE_PROVIDER
DEFAULT_AGENT_MAX_STEPS = 3
DEFAULT_MAX_QUESTION_CHARS = 2000
DEFAULT_POLICIES_PATH = "data/policies.json"

DEFAULT_SERVICE_NAME = "politicas-rh"
DEFAULT_SLO_P95_MS = 2000
DEFAULT_LANGSMITH_TRACING = False
DEFAULT_HIDE_CONTENT = True
DEFAULT_LANGSMITH_PROJECT = "politicas-rh"
BOOLEAN_VALUES = {"true": True, "false": False}

DEFAULT_MODEL_SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
DEFAULT_MODEL_LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
DEFAULT_ROUTING = True
DEFAULT_ROUTER_MAX_CHARS = 80
DEFAULT_HISTORY_WINDOW = 6
DEFAULT_MODEL_MAX_TOKENS = 300
DEFAULT_MODEL_TEMPERATURE = 0.0
DEFAULT_CACHE_TTL_SECONDS = 0
DEFAULT_PRICES_PATH = "data/model_prices.json"
DEFAULT_CF_GATEWAY_ID = "default"
# Solo letras, dígitos, guion y guion bajo: los ids van dentro de la URL y no
# deben poder agregar segmentos de ruta ni parámetros.
CLOUDFLARE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

DEVELOPMENT = "development"
PRODUCTION = "production"
SUPPORTED_ENVIRONMENTS = (DEVELOPMENT, PRODUCTION)
DEFAULT_ENVIRONMENT = DEVELOPMENT
DEFAULT_RATE_LIMIT_PER_MINUTE = 30

DEFAULT_COMPANION_URL = ""
DEFAULT_COMPANION_NAME = "HR Assistant"


@dataclass(frozen=True)
class PageSettings:
    """Configuración de la página web y de lo que acepta su formulario.

    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :param companion_url: URL del otro producto; vacía, la página no lo enlaza
    :type companion_url: str
    :param companion_name: Texto del enlace al otro producto
    :type companion_name: str
    """

    max_question_chars: int = DEFAULT_MAX_QUESTION_CHARS
    companion_url: str = DEFAULT_COMPANION_URL
    companion_name: str = DEFAULT_COMPANION_NAME


@dataclass(frozen=True)
class RoutingSettings:
    """Palanca de enrutamiento: qué modelo atiende cada pregunta.

    :param model_small: Nombre del modelo barato
    :type model_small: str
    :param model_large: Nombre del modelo capaz
    :type model_large: str
    :param enabled: Si se enruta por pregunta; si no, todo va al modelo capaz
    :type enabled: bool
    :param max_chars: Preguntas más largas que esto van al modelo capaz
    :type max_chars: int
    """

    model_small: str = DEFAULT_MODEL_SMALL
    model_large: str = DEFAULT_MODEL_LARGE
    enabled: bool = DEFAULT_ROUTING
    max_chars: int = DEFAULT_ROUTER_MAX_CHARS


@dataclass(frozen=True)
class CallSettings:
    """Palancas que se aplican a cada llamada al modelo.

    :param history_window: Mensajes del historial del cliente que se mandan
    :type history_window: int
    :param max_tokens: Tope de tokens de salida por llamada
    :type max_tokens: int
    :param temperature: Temperatura del modelo (0 hace repetibles las pruebas)
    :type temperature: float
    :param cache_ttl_seconds: Vida de la caché del gateway; 0 la apaga
    :type cache_ttl_seconds: int
    """

    history_window: int = DEFAULT_HISTORY_WINDOW
    max_tokens: int = DEFAULT_MODEL_MAX_TOKENS
    temperature: float = DEFAULT_MODEL_TEMPERATURE
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS


@dataclass(frozen=True)
class GatewaySettings:
    """Datos de Cloudflare AI Gateway.

    :param account_id: Id de la cuenta de Cloudflare
    :type account_id: str
    :param gateway_id: Id del gateway
    :type gateway_id: str
    :param api_token: Token de la API; nunca se muestra en ``repr``
    :type api_token: str
    """

    account_id: str = ""
    gateway_id: str = DEFAULT_CF_GATEWAY_ID
    api_token: str = field(default="", repr=False)


@dataclass(frozen=True)
class CostSettings:
    """Configuración de costos: modelos, palancas, gateway y precios.

    :param routing: Enrutamiento por pregunta
    :type routing: RoutingSettings
    :param call: Palancas de cada llamada
    :type call: CallSettings
    :param gateway: Datos de Cloudflare AI Gateway
    :type gateway: GatewaySettings
    :param prices_path: Ruta absoluta al archivo de precios por modelo
    :type prices_path: pathlib.Path
    """

    routing: RoutingSettings = field(default_factory=RoutingSettings)
    call: CallSettings = field(default_factory=CallSettings)
    gateway: GatewaySettings = field(default_factory=GatewaySettings)
    prices_path: Path = PRODUCT_DIR / DEFAULT_PRICES_PATH


@dataclass(frozen=True)
class ObservabilitySettings:
    """Configuración inmutable de log, métricas y trazas.

    :param service_name: Valor del campo ``service`` del log
    :type service_name: str
    :param slo_p95_ms: Meta de latencia p95 en milisegundos
    :type slo_p95_ms: int
    :param langsmith_tracing: Si se encienden las trazas en LangSmith
    :type langsmith_tracing: bool
    :param hide_inputs: Si se ocultan las entradas en las trazas
    :type hide_inputs: bool
    :param hide_outputs: Si se ocultan las salidas en las trazas
    :type hide_outputs: bool
    :param langsmith_api_key: Clave de LangSmith; nunca se muestra en ``repr``
    :type langsmith_api_key: str
    :param langsmith_project: Proyecto de LangSmith donde quedan las trazas
    :type langsmith_project: str
    """

    service_name: str = DEFAULT_SERVICE_NAME
    slo_p95_ms: int = DEFAULT_SLO_P95_MS
    langsmith_tracing: bool = DEFAULT_LANGSMITH_TRACING
    hide_inputs: bool = DEFAULT_HIDE_CONTENT
    hide_outputs: bool = DEFAULT_HIDE_CONTENT
    langsmith_api_key: str = field(default="", repr=False)
    langsmith_project: str = DEFAULT_LANGSMITH_PROJECT


@dataclass(frozen=True)
class SecuritySettings:
    """Configuración de acceso: entorno, claves por cliente y límite.

    :param environment: ``development`` o ``production`` (aplica compliance)
    :type environment: str
    :param api_keys: Claves por nombre de cliente (secreto); nunca se muestran
        en ``repr``
    :type api_keys: collections.abc.Mapping[str, str]
    :param rate_limit_per_minute: Peticiones por cliente por minuto
    :type rate_limit_per_minute: int
    """

    environment: str = DEFAULT_ENVIRONMENT
    api_keys: Mapping = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación.

    :param model_provider: Proveedor del modelo: ``fake`` o ``gateway``
    :type model_provider: str
    :param agent_max_steps: Tope de vueltas del bucle del agente
    :type agent_max_steps: int
    :param page: Largo máximo de la pregunta y enlace al otro producto
    :type page: PageSettings
    :param policies_path: Ruta absoluta al archivo de políticas
    :type policies_path: pathlib.Path
    :param observability: Configuración de log, métricas y trazas
    :type observability: ObservabilitySettings
    :param costs: Configuración de modelos, palancas de costo y gateway
    :type costs: CostSettings
    :param security: Entorno, claves por cliente y límite de peticiones
    :type security: SecuritySettings
    """

    model_provider: str = DEFAULT_MODEL_PROVIDER
    agent_max_steps: int = DEFAULT_AGENT_MAX_STEPS
    page: PageSettings = field(default_factory=PageSettings)
    policies_path: Path = PRODUCT_DIR / DEFAULT_POLICIES_PATH
    observability: ObservabilitySettings = field(
        default_factory=ObservabilitySettings
    )
    costs: CostSettings = field(default_factory=CostSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)


def _read(env, name, default):
    """Lee una variable sin espacios; si falta o está vacía usa el valor por omisión.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión
    :type default: str
    :return: Valor leído
    :rtype: str
    """
    value = str(env.get(name, "")).strip()
    return value or default


def _integer(env, name, default, minimum):
    """Lee una variable que debe ser un entero mayor o igual que ``minimum``.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión
    :type default: int
    :param minimum: Menor valor aceptado
    :type minimum: int
    :return: Entero validado
    :rtype: int
    :raises ConfigError: Si el valor no es un entero o es menor que ``minimum``
    """
    raw = _read(env, name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(
            f"{name} must be an integer (>= {minimum}), got {raw!r}"
        ) from error
    if value < minimum:
        raise ConfigError(f"{name} must be an integer (>= {minimum}), got {value}")
    return value


def _positive_int(env, name, default):
    """Lee una variable que debe ser un entero mayor que cero.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión
    :type default: int
    :return: Entero validado
    :rtype: int
    :raises ConfigError: Si el valor no es un entero o es menor que 1
    """
    return _integer(env, name, default, minimum=1)


def _non_negative_number(env, name, default):
    """Lee una variable que debe ser un número finito mayor o igual que cero.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión
    :type default: float
    :return: Número validado
    :rtype: float
    :raises ConfigError: Si el valor no es un número, no es finito o es negativo
    """
    raw = _read(env, name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be a number (>= 0), got {raw!r}") from error
    if not math.isfinite(value) or value < 0:
        raise ConfigError(f"{name} must be a finite number (>= 0), got {raw!r}")
    return value


def _provider(env):
    """Lee y valida ``MODEL_PROVIDER``.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Proveedor soportado
    :rtype: str
    :raises ConfigError: Si el proveedor no está soportado
    """
    provider = _read(env, "MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER).casefold()
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ConfigError(
            f"MODEL_PROVIDER must be one of: {supported}, got {provider!r}"
        )
    return provider


def _existing_file(env, name, default):
    """Lee una ruta de archivo y la resuelve contra la carpeta del producto.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Ruta por omisión, relativa a la carpeta del producto
    :type default: str
    :return: Ruta absoluta a un archivo existente
    :rtype: pathlib.Path
    :raises ConfigError: Si el archivo no existe
    """
    path = Path(_read(env, name, default))
    if not path.is_absolute():
        path = PRODUCT_DIR / path
    path = path.resolve()
    if not path.is_file():
        raise ConfigError(f"{name} must point to an existing file: {path}")
    return path


def _boolean(env, name, default):
    """Lee una variable que solo puede valer ``true`` o ``false``.

    No distingue mayúsculas de minúsculas.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión
    :type default: bool
    :return: Valor leído
    :rtype: bool
    :raises ConfigError: Si el valor no es ``true`` ni ``false``
    """
    raw = _read(env, name, str(default)).casefold()
    if raw not in BOOLEAN_VALUES:
        raise ConfigError(f"{name} must be 'true' or 'false', got {raw!r}")
    return BOOLEAN_VALUES[raw]


def _observability(env):
    """Lee las variables de log, métricas y trazas.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de observabilidad validada
    :rtype: ObservabilitySettings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    return ObservabilitySettings(
        service_name=_read(env, "SERVICE_NAME", DEFAULT_SERVICE_NAME),
        slo_p95_ms=_positive_int(env, "SLO_P95_MS", DEFAULT_SLO_P95_MS),
        langsmith_tracing=_boolean(
            env, "LANGSMITH_TRACING", DEFAULT_LANGSMITH_TRACING
        ),
        hide_inputs=_boolean(env, "HIDE_INPUTS", DEFAULT_HIDE_CONTENT),
        hide_outputs=_boolean(env, "HIDE_OUTPUTS", DEFAULT_HIDE_CONTENT),
        langsmith_api_key=_read(env, "LANGSMITH_API_KEY", ""),
        langsmith_project=_read(
            env, "LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT
        ),
    )


def _routing(env):
    """Lee los modelos y la palanca de enrutamiento.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de enrutamiento validada
    :rtype: RoutingSettings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    return RoutingSettings(
        model_small=_read(env, "MODEL_SMALL", DEFAULT_MODEL_SMALL),
        model_large=_read(env, "MODEL_LARGE", DEFAULT_MODEL_LARGE),
        enabled=_boolean(env, "ROUTING", DEFAULT_ROUTING),
        max_chars=_positive_int(env, "ROUTER_MAX_CHARS", DEFAULT_ROUTER_MAX_CHARS),
    )


def _call(env):
    """Lee las palancas de cada llamada: historial, tope, temperatura y caché.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de llamada validada
    :rtype: CallSettings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    return CallSettings(
        history_window=_integer(
            env, "HISTORY_WINDOW", DEFAULT_HISTORY_WINDOW, minimum=0
        ),
        max_tokens=_positive_int(env, "MODEL_MAX_TOKENS", DEFAULT_MODEL_MAX_TOKENS),
        temperature=_non_negative_number(
            env, "MODEL_TEMPERATURE", DEFAULT_MODEL_TEMPERATURE
        ),
        cache_ttl_seconds=_integer(
            env, "CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS, minimum=0
        ),
    )


def _gateway(env, provider):
    """Lee los datos de Cloudflare; con ``gateway`` los tres son obligatorios.

    Los mensajes de error nunca incluyen el valor recibido: puede ser secreto.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param provider: Proveedor ya validado
    :type provider: str
    :return: Datos del gateway
    :rtype: GatewaySettings
    :raises ConfigError: Si el proveedor es ``gateway`` y falta una variable o
        un id tiene caracteres no permitidos
    """
    gateway = GatewaySettings(
        account_id=_read(env, "CF_ACCOUNT_ID", ""),
        gateway_id=_read(env, "CF_GATEWAY_ID", DEFAULT_CF_GATEWAY_ID),
        api_token=_read(env, "CF_API_TOKEN", ""),
    )
    if provider != GATEWAY_PROVIDER:
        return gateway
    ids = (
        ("CF_ACCOUNT_ID", gateway.account_id),
        ("CF_GATEWAY_ID", gateway.gateway_id),
    )
    for name, value in ids:
        if not CLOUDFLARE_ID_PATTERN.fullmatch(value):
            raise ConfigError(
                f"{name} is required with MODEL_PROVIDER=gateway and may only "
                "contain letters, digits, '_' and '-' (1 to 64 characters)"
            )
    if not gateway.api_token:
        raise ConfigError("CF_API_TOKEN is required with MODEL_PROVIDER=gateway")
    return gateway


def _costs(env, provider):
    """Lee toda la configuración de costos.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param provider: Proveedor ya validado
    :type provider: str
    :return: Configuración de costos validada
    :rtype: CostSettings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    return CostSettings(
        routing=_routing(env),
        call=_call(env),
        gateway=_gateway(env, provider),
        prices_path=_existing_file(env, "PRICES_PATH", DEFAULT_PRICES_PATH),
    )


def _environment(env):
    """Lee y valida ``ENVIRONMENT``.

    Solo se aceptan ``development`` y ``production``: un error de dedo (por
    ejemplo ``prod``) no debe saltarse las reglas de compliance.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Entorno soportado
    :rtype: str
    :raises ConfigError: Si el entorno no está soportado
    """
    environment = _read(env, "ENVIRONMENT", DEFAULT_ENVIRONMENT).casefold()
    if environment not in SUPPORTED_ENVIRONMENTS:
        supported = ", ".join(SUPPORTED_ENVIRONMENTS)
        raise ConfigError(
            f"ENVIRONMENT must be one of: {supported}, got {environment!r}"
        )
    return environment


def _security(env):
    """Lee el entorno, las claves por cliente y el límite de peticiones.

    Los errores de ``API_KEYS`` nombran la entrada y su largo, nunca su valor.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de seguridad validada
    :rtype: SecuritySettings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    return SecuritySettings(
        environment=_environment(env),
        api_keys=parse_api_keys(str(env.get("API_KEYS", ""))),
        rate_limit_per_minute=_positive_int(
            env, "RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE
        ),
    )


def _page(env):
    """Lee el largo máximo de la pregunta y el enlace al otro producto.

    Una ``COMPANION_URL`` vacía o de solo espacios deja la página sin enlace;
    un ``COMPANION_NAME`` vacío usa el nombre por omisión.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de la página validada
    :rtype: PageSettings
    :raises ConfigError: Si ``MAX_QUESTION_CHARS`` no es un entero positivo
    """
    return PageSettings(
        max_question_chars=_positive_int(
            env, "MAX_QUESTION_CHARS", DEFAULT_MAX_QUESTION_CHARS
        ),
        companion_url=_read(env, "COMPANION_URL", DEFAULT_COMPANION_URL),
        companion_name=_read(env, "COMPANION_NAME", DEFAULT_COMPANION_NAME),
    )


def load_settings(env: Mapping | None = None) -> Settings:
    """Construye la configuración a partir de variables de entorno.

    :param env: Variables de entorno; si es ``None`` se usa ``os.environ``
    :type env: collections.abc.Mapping or None
    :return: Configuración validada
    :rtype: Settings
    :raises ConfigError: Si alguna variable tiene un valor inválido
    """
    source = os.environ if env is None else env
    provider = _provider(source)
    return Settings(
        model_provider=provider,
        agent_max_steps=_positive_int(
            source, "AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS
        ),
        page=_page(source),
        policies_path=_existing_file(
            source, "POLICIES_PATH", DEFAULT_POLICIES_PATH
        ),
        observability=_observability(source),
        costs=_costs(source, provider),
        security=_security(source),
    )
