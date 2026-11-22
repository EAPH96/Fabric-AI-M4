"""API web sin estado del HR Assistant.

``create_app()`` recibe sus dependencias para que las pruebas inyecten las
suyas; ``app`` es la instancia que arranca ``uvicorn app.main:app`` con la
configuración del entorno. Cada petición lleva un ``request_id``, deja una
línea JSON en el log y alimenta las métricas de ``GET /metrics``.

En cada ``POST /ask`` el enrutador elige el modelo, se recorta el historial y
un ``CostMeter`` suma el costo de la respuesta (ADR 0007 y 0009).

``POST /ask`` y ``GET /metrics`` piden ``X-API-Key`` y respetan el límite de
peticiones por cliente; ``/``, ``/health`` y ``/docs`` siguen abiertos (ADR 0010
y 0011). Con ``ENVIRONMENT=production`` la aplicación no se arma si incumple
una regla de compliance (ADR 0012).

La página de ``GET /`` se arma una sola vez al arrancar, con el enlace al otro
producto si ``COMPANION_URL`` tiene valor (ADR 0014).
"""

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

from app.agent import Agent, recent_history
from app.compliance import enforce_compliance
from app.config import load_settings
from app.directory import EmployeeDirectory
from app.gateway import ModelUnavailableError
from app.llm import build_models
from app.observability import (
    RequestObserver,
    build_observability,
    install_middleware,
)
from app.page import render_index
from app.pricing import CostMeter, PriceTable
from app.ratelimit import RateLimiter
from app.router import choose_route
from app.security import ApiKeyAuth

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"
MODEL_UNAVAILABLE_STATUS = 502
MODEL_UNAVAILABLE_DETAIL = "model unavailable"
API_KEY_HEADER = "X-API-Key"
INVALID_KEY_STATUS = 401
INVALID_KEY_DETAIL = "invalid or missing API key"
RATE_LIMITED_STATUS = 429
RATE_LIMITED_DETAIL = "rate limit exceeded"
RETRY_AFTER_HEADER = "Retry-After"


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversación que guarda el cliente.

    :param role: Quién lo dijo: ``user`` o ``assistant``
    :type role: str
    :param content: Texto del mensaje
    :type content: str
    """

    role: Literal["user", "assistant"]
    content: str


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``.

    :param answer: Respuesta del agente
    :type answer: str
    :param steps: Número de llamadas al modelo
    :type steps: int
    :param tools_used: Herramientas ejecutadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada sumados
    :type input_tokens: int
    :param output_tokens: Tokens de salida sumados
    :type output_tokens: int
    :param request_id: Id de la petición, para pasarlo a soporte
    :type request_id: str
    :param model: Modelo que eligió el enrutador
    :type model: str
    :param route: Motivo del enrutador
    :type route: str
    :param cached_calls: Llamadas servidas por la caché del gateway
    :type cached_calls: int
    :param cost_usd: Costo de la respuesta en USD, sin redondear
    :type cost_usd: float
    """

    answer: str
    steps: int
    tools_used: list[str]
    input_tokens: int
    output_tokens: int
    request_id: str
    model: str
    route: str
    cached_calls: int
    cost_usd: float


class HealthResponse(BaseModel):
    """Respuesta de ``GET /health``.

    :param status: Siempre ``ok`` si el proceso responde
    :type status: str
    :param pid: Id del proceso que atendió la petición
    :type pid: int
    """

    status: str
    pid: int


def build_ask_request(max_question_chars):
    """Crea el modelo del cuerpo de ``POST /ask`` con el largo máximo configurado.

    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :return: Clase Pydantic que valida el cuerpo
    :rtype: type[pydantic.BaseModel]
    """

    class AskRequest(BaseModel):
        """Cuerpo de ``POST /ask``: pregunta e historial opcional del cliente."""

        question: str = Field(min_length=1, max_length=max_question_chars)
        history: list[HistoryMessage] = Field(default_factory=list)

        @field_validator("question")
        @classmethod
        def question_is_not_blank(cls, value):
            """Rechaza preguntas que solo tienen espacios.

            :param value: Pregunta recibida
            :type value: str
            :return: La misma pregunta
            :rtype: str
            :raises ValueError: Si la pregunta está en blanco
            """
            if not value.strip():
                raise ValueError("question must not be blank")
            return value

    return AskRequest


def cost_fields(route, meter):
    """Reúne lo que la respuesta y el log dicen del modelo y del costo.

    :param route: Modelo y motivo del enrutador
    :type route: app.router.Route
    :param meter: Medidor de costo de la petición
    :type meter: app.pricing.CostMeter
    :return: ``model``, ``route``, ``cached_calls`` y ``cost_usd``
    :rtype: dict
    """
    return {
        "model": route.model,
        "route": route.reason,
        "cached_calls": meter.cached_calls,
        "cost_usd": meter.cost_usd,
    }


def log_agent_run(observability, observer, payload, result, cost):
    """Escribe el evento ``agent_run`` y suma tokens y costo a las métricas.

    Solo registra conteos y el nombre del cliente: nunca el texto de la
    pregunta ni de la respuesta, ni la clave.

    :param observability: Dependencias de observabilidad
    :type observability: app.observability.Observability
    :param observer: Observador de la petición, con su ``request_id`` y cliente
    :type observer: app.observability.RequestObserver
    :param payload: Cuerpo validado de ``POST /ask``
    :type payload: pydantic.BaseModel
    :param result: Resultado del agente
    :type result: app.agent.AgentResult
    :param cost: Modelo, motivo y costo, de ``cost_fields``
    :type cost: dict
    """
    observer.log_event(
        "agent_run",
        question_chars=len(payload.question),
        history_messages=len(payload.history),
        steps=result.steps,
        tools=list(result.tools_used),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        stopped=result.stopped,
        **cost,
    )
    observability.metrics.add_tokens(result.input_tokens, result.output_tokens)
    observability.metrics.add_cost(cost["cost_usd"])


def model_unavailable(observability, request_id, error):
    """Registra la falla del modelo y crea la respuesta ``502``.

    El evento ``error`` lleva solo el tipo: el mensaje podría traer datos de
    la cuenta.

    :param observability: Dependencias de observabilidad
    :type observability: app.observability.Observability
    :param request_id: Id de la petición
    :type request_id: str
    :param error: Falla del modelo
    :type error: app.gateway.ModelUnavailableError
    :return: Respuesta JSON con ``detail`` y ``request_id``
    :rtype: fastapi.responses.JSONResponse
    """
    observability.logger.event(
        "error", request_id, error_type=type(error).__name__
    )
    return JSONResponse(
        {"detail": MODEL_UNAVAILABLE_DETAIL, "request_id": request_id},
        status_code=MODEL_UNAVAILABLE_STATUS,
    )


def resolve_models(settings, directory, model, models):
    """Decide qué modelo atiende cada nombre del enrutador.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param directory: Directorio de empleados
    :type directory: app.directory.EmployeeDirectory
    :param model: Modelo único que atiende las dos rutas, o ``None``
    :type model: app.llm.ChatModel or None
    :param models: Modelos por nombre, o ``None``
    :type models: dict[str, app.llm.ChatModel] or None
    :return: Modelos por nombre de ``MODEL_SMALL`` y ``MODEL_LARGE``
    :rtype: dict[str, app.llm.ChatModel]
    """
    if models is not None:
        return models
    if model is not None:
        routing = settings.costs.routing
        return {routing.model_small: model, routing.model_large: model}
    return build_models(settings, directory)


def build_client_guard(settings, observability):
    """Arma la dependencia que identifica al cliente y aplica su límite.

    Primero la clave: sin ella o con una inválida, ``401``. Después el límite:
    si el cliente ya usó sus peticiones del minuto, ``429`` con
    ``Retry-After``. Un ``401`` no cuenta en el límite. La clave nunca se
    guarda ni se registra; solo el nombre del cliente, en
    ``request.state.client``, para el log del middleware.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param observability: Dependencias de observabilidad; su reloj mueve la
        ventana del límite
    :type observability: app.observability.Observability
    :return: Dependencia de FastAPI que devuelve el nombre del cliente
    :rtype: collections.abc.Callable
    """
    auth = ApiKeyAuth(settings.security.api_keys)
    limiter = RateLimiter(
        settings.security.rate_limit_per_minute, observability.clock
    )
    api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)

    def require_client(
        request: Request,
        api_key: Annotated[str | None, Security(api_key_header)] = None,
    ):
        """Devuelve el cliente dueño de la clave o rechaza la petición.

        :raises fastapi.HTTPException: ``401`` si falta la clave o no es
            válida; ``429`` si el cliente pasó su límite por minuto
        """
        client = auth.identify(api_key)
        if client is None:
            raise HTTPException(INVALID_KEY_STATUS, detail=INVALID_KEY_DETAIL)
        request.state.client = client
        retry_after = limiter.check(client)
        if retry_after is not None:
            raise HTTPException(
                RATE_LIMITED_STATUS,
                detail=RATE_LIMITED_DETAIL,
                headers={RETRY_AFTER_HEADER: str(retry_after)},
            )
        return client

    return require_client


def create_app(
    settings=None, model=None, directory=None, observability=None, models=None
):
    """Arma la aplicación FastAPI con sus dependencias.

    Lo único compartido entre peticiones es de solo lectura, salvo el log y
    las métricas del proceso; se crea un ``Agent`` nuevo en cada ``POST /ask``.

    :param settings: Configuración; si es ``None`` se lee del entorno
    :type settings: app.config.Settings or None
    :param model: Modelo único para las dos rutas del enrutador (útil en
        pruebas); se ignora si se pasa ``models``
    :type model: app.llm.ChatModel or None
    :param directory: Directorio; si es ``None`` se carga de ``employees_path``
    :type directory: app.directory.EmployeeDirectory or None
    :param observability: Reloj, log, métricas y tracer; si es ``None`` se
        construyen con ``build_observability``
    :type observability: app.observability.Observability or None
    :param models: Modelos por nombre; si ni este ni ``model`` se pasan, se
        construyen con ``build_models``
    :type models: dict[str, app.llm.ChatModel] or None
    :return: Aplicación lista para servir
    :rtype: fastapi.FastAPI
    :raises app.config.ConfigError: Si la configuración del entorno es inválida,
        falta el precio de un modelo o, en producción, se incumple una regla de
        compliance
    """
    if settings is None:
        settings = load_settings()
    enforce_compliance(settings)
    if directory is None:
        directory = EmployeeDirectory(settings.employees_path)
    models = resolve_models(settings, directory, model, models)
    prices = PriceTable.from_file(
        settings.costs.prices_path,
        [settings.costs.routing.model_small, settings.costs.routing.model_large],
    )
    if observability is None:
        observability = build_observability(settings)
    index_page = render_index(INDEX_FILE.read_text(encoding="utf-8"), settings.page)
    ask_request = build_ask_request(settings.page.max_question_chars)
    require_client = build_client_guard(settings, observability)

    api = FastAPI(title="HR Assistant")
    install_middleware(api, observability)

    @api.get("/", response_class=HTMLResponse)
    def home():
        """Sirve la página web del personal de RH."""
        return HTMLResponse(index_page)

    @api.get("/health", response_model=HealthResponse)
    def health():
        """Indica que el proceso responde y cuál es su ``pid``."""
        return HealthResponse(status="ok", pid=os.getpid())

    @api.get("/metrics", dependencies=[Depends(require_client)])
    def read_metrics():
        """Devuelve las métricas de este proceso y si se cumple la meta p95."""
        return observability.metrics.snapshot(settings.observability.slo_p95_ms)

    @api.post("/ask", response_model=AskResponse)
    def ask(
        payload: ask_request,
        request: Request,
        client: Annotated[str, Depends(require_client)],
    ):
        """Responde una pregunta con el modelo que elige el enrutador.

        Se crea un agente nuevo con un medidor de costo y solo los últimos
        mensajes del historial del cliente.
        """
        request_id = request.state.request_id
        route = choose_route(payload.question, settings.costs.routing)
        meter = CostMeter(models[route.model], prices, route.model)
        observer = RequestObserver(observability, request_id, client)
        agent = Agent(
            model=meter,
            directory=directory,
            max_steps=settings.agent_max_steps,
            observer=observer,
        )
        history = recent_history(
            [message.model_dump() for message in payload.history],
            settings.costs.call.history_window,
        )
        run_agent = observer.wrap(agent.run, run_type="chain")
        try:
            result = run_agent(payload.question, history)
        except ModelUnavailableError as error:
            return model_unavailable(observability, request_id, error)
        cost = cost_fields(route, meter)
        log_agent_run(observability, observer, payload, result, cost)
        return AskResponse(
            answer=result.answer,
            steps=result.steps,
            tools_used=result.tools_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            request_id=request_id,
            **cost,
        )

    return api


app = create_app()
