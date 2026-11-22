"""Id por petición, middleware de registro y observador del agente.

El middleware resuelve el ``request_id``, mide la latencia, registra cada
petición en el log y en las métricas, y convierte cualquier excepción en un
``500`` que no explica el error pero da el id para soporte (ADR 0004 del HR).
"""

import re
import sys
import uuid
from dataclasses import dataclass

from fastapi.responses import JSONResponse

from app.clock import SystemClock
from app.logs import JsonLogger
from app.metrics import Metrics
from app.tracing import build_tracer

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")
INTERNAL_ERROR_STATUS = 500
INTERNAL_ERROR_DETAIL = "internal error"
MILLISECONDS = 1000
LATENCY_DECIMALS = 2


@dataclass(frozen=True)
class Observability:
    """Dependencias de observabilidad compartidas por toda la aplicación.

    :param clock: Reloj para la hora del log y la latencia
    :type clock: app.clock.Clock
    :param logger: Log JSON de eventos
    :type logger: app.logs.JsonLogger
    :param metrics: Métricas en memoria del proceso
    :type metrics: app.metrics.Metrics
    :param tracer: Tracer de LangSmith o uno que no hace nada
    :type tracer: app.tracing.NullTracer or app.tracing.LangSmithTracer
    """

    clock: object
    logger: JsonLogger
    metrics: Metrics
    tracer: object


def build_observability(settings, stream=None):
    """Construye la observabilidad real: reloj del sistema y log en ``stdout``.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param stream: Destino del log; si es ``None`` se usa ``sys.stdout``
    :type stream: typing.TextIO or None
    :return: Observabilidad lista para ``create_app``
    :rtype: Observability
    """
    clock = SystemClock()
    logger = JsonLogger(
        stream=sys.stdout if stream is None else stream,
        clock=clock,
        service=settings.observability.service_name,
    )
    return Observability(
        clock=clock, logger=logger, metrics=Metrics(), tracer=build_tracer(settings)
    )


def resolve_request_id(header):
    """Usa el id que manda el cliente si es válido; si no, genera un UUID.

    Un id válido tiene de 1 a 128 caracteres de ``[A-Za-z0-9._:-]``.

    :param header: Valor del encabezado ``X-Request-ID`` o ``None``
    :type header: str or None
    :return: Id de la petición
    :rtype: str
    """
    if header and REQUEST_ID_PATTERN.fullmatch(header):
        return header
    return str(uuid.uuid4())


def client_fields(client):
    """Campo ``client`` para un evento del log, solo si se conoce el cliente.

    :param client: Nombre del cliente (nunca su clave), o ``None``
    :type client: str or None
    :return: ``{"client": client}`` o un diccionario vacío
    :rtype: dict
    """
    return {} if client is None else {"client": client}


class RequestObserver:
    """Observador del agente para una sola petición.

    Envuelve funciones con el tracer y escribe un evento ``audit`` por cada
    herramienta ejecutada. Si se conoce el cliente, su nombre va en cada
    evento y en los metadatos de la traza.

    :param observability: Dependencias de observabilidad
    :type observability: Observability
    :param request_id: Id de la petición
    :type request_id: str
    :param client: Nombre del cliente que pregunta (nunca su clave), o ``None``
    :type client: str or None
    """

    def __init__(self, observability, request_id, client=None):
        self._observability = observability
        self._request_id = request_id
        self._client = client

    def wrap(self, function, run_type):
        """Envuelve una función como traza de esta petición.

        :param function: Función a envolver
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza (``chain``, ``llm`` o ``tool``)
        :type run_type: str
        :return: Función trazada (o la misma si el tracer está apagado)
        :rtype: collections.abc.Callable
        """
        return self._observability.tracer.wrap(
            function,
            run_type=run_type,
            request_id=self._request_id,
            client=self._client,
        )

    def log_event(self, name, **fields):
        """Escribe un evento de esta petición con su ``request_id`` y cliente.

        :param name: Nombre del evento (``agent_run``, ``audit``...)
        :type name: str
        :param fields: Campos propios del evento
        :type fields: dict
        """
        self._observability.logger.event(
            name, self._request_id, **client_fields(self._client), **fields
        )

    def tool_called(self, name, args):
        """Escribe el evento ``audit`` de una herramienta ejecutada.

        :param name: Nombre de la herramienta
        :type name: str
        :param args: Argumentos con los que se ejecutó
        :type args: dict
        """
        self.log_event("audit", action="tool_call", tool=name, args=args)


def _error_response(request_id):
    """Crea la respuesta ``500`` que no explica el error.

    :param request_id: Id de la petición
    :type request_id: str
    :return: Respuesta JSON con ``detail`` y ``request_id``
    :rtype: fastapi.responses.JSONResponse
    """
    return JSONResponse(
        {"detail": INTERNAL_ERROR_DETAIL, "request_id": request_id},
        status_code=INTERNAL_ERROR_STATUS,
    )


def install_middleware(api, observability):
    """Instala el middleware que da id, mide y registra cada petición.

    :param api: Aplicación donde se instala
    :type api: fastapi.FastAPI
    :param observability: Dependencias de observabilidad
    :type observability: Observability
    """

    @api.middleware("http")
    async def observe_request(request, call_next):
        """Atiende la petición, la registra y agrega ``X-Request-ID``."""
        start = observability.clock.monotonic()
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Solo el tipo: el mensaje puede traer datos personales o secretos.
            observability.logger.event(
                "error", request_id, error_type=type(error).__name__
            )
            response = _error_response(request_id)
        elapsed = observability.clock.monotonic() - start
        latency_ms = round(elapsed * MILLISECONDS, LATENCY_DECIMALS)
        observability.metrics.record_request(response.status_code, latency_ms)
        # La dependencia de clave guarda el cliente en el mismo ``scope``.
        client = getattr(request.state, "client", None)
        observability.logger.event(
            "request",
            request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
            **client_fields(client),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
