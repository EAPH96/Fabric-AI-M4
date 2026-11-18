"""Fixtures compartidas: la aplicación se arma con dependencias inyectadas.

Las pruebas nunca leen ``os.environ``: pasan su propio entorno a ``load_settings``
y construyen el directorio, el modelo y la observabilidad antes de llamar a
``create_app``. La hora sale de un ``FakeClock`` y el log se escribe en memoria,
así que cada prueba es determinista y no ensucia la salida estándar.

Desde la sesión 4, ``/ask`` y ``/metrics`` piden ``X-API-Key``: ``make_client``
configura por omisión un cliente ``tests`` con una clave de prueba y manda esa
clave en cada petición, para que las pruebas de las sesiones 1 a 3 sigan igual.
"""

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest_bdd import parsers, then

from app.config import load_settings
from app.directory import EmployeeDirectory
from app.llm import build_models
from app.logs import JsonLogger
from app.main import create_app
from app.metrics import Metrics
from app.observability import Observability
from app.tracing import NullTracer

PRODUCT_DIR = Path(__file__).resolve().parents[1]
EMPLOYEES_FILE = PRODUCT_DIR / "data" / "employees.json"
FIXED_NOW = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)
TICK_SECONDS = 0.01
FAKE_CF_TOKEN = "cf-token-for-tests-not-real"
TEST_CLIENT = "tests"
TEST_API_KEY = "tests-key-not-real-0001"
API_KEY_HEADER = "X-API-Key"


class FakeClock:
    """Reloj de prueba: hora fija en UTC y ``monotonic`` que avanza 10 ms por llamada.

    :param now: Hora que devuelve siempre ``now()``
    :type now: datetime.datetime
    """

    def __init__(self, now=FIXED_NOW):
        self._now = now
        self._seconds = 0.0

    def now(self):
        """Devuelve la hora fija, con zona UTC.

        :return: Hora fija
        :rtype: datetime.datetime
        """
        return self._now

    def monotonic(self):
        """Avanza el contador 10 ms y lo devuelve.

        :return: Segundos transcurridos desde que se creó el reloj
        :rtype: float
        """
        self._seconds += TICK_SECONDS
        return self._seconds

    def advance(self, seconds):
        """Mueve el contador ``monotonic`` hacia adelante, como si pasara el tiempo.

        :param seconds: Segundos que se adelanta el reloj
        :type seconds: float
        """
        self._seconds += seconds


class FakeGateway:
    """AI Gateway simulado con ``httpx.MockTransport``: nunca usa la red.

    Guarda cada petición recibida y responde como Workers AI. Cada prueba
    cambia ``status``, ``content``, ``headers``, ``payload`` o ``times_out`` para
    simular una respuesta distinta.
    """

    PROMPT_TOKENS = 120
    COMPLETION_TOKENS = 15

    def __init__(self):
        self.requests = []
        self.status = 200
        self.content = json.dumps({"answer": "Hola desde el gateway"})
        self.headers = {}
        self.payload = None
        self.times_out = False

    def client(self):
        """Cliente HTTP cuyo transporte es este gateway simulado.

        :return: Cliente para inyectar en ``build_models``
        :rtype: httpx.Client
        """
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def last_body(self):
        """Cuerpo JSON de la última petición recibida.

        :return: Cuerpo decodificado
        :rtype: dict
        """
        return json.loads(self.requests[-1].content)

    def _handle(self, request):
        """Responde una petición como lo haría el gateway.

        :param request: Petición que manda ``GatewayModel``
        :type request: httpx.Request
        :return: Respuesta simulada
        :rtype: httpx.Response
        :raises httpx.ReadTimeout: Si la prueba pidió ``times_out``
        """
        self.requests.append(request)
        if self.times_out:
            raise httpx.ReadTimeout("simulated gateway timeout", request=request)
        payload = self.payload
        if payload is None:
            payload = {
                "choices": [
                    {"message": {"role": "assistant", "content": self.content}}
                ],
                "usage": {
                    "prompt_tokens": self.PROMPT_TOKENS,
                    "completion_tokens": self.COMPLETION_TOKENS,
                },
            }
        return httpx.Response(self.status, json=payload, headers=self.headers)


@pytest.fixture
def fake_gateway():
    """Gateway simulado que responde una respuesta final válida.

    :return: Gateway simulado sin peticiones
    :rtype: FakeGateway
    """
    return FakeGateway()


@pytest.fixture
def gateway_env():
    """Variables de entorno para ``MODEL_PROVIDER=gateway`` con valores de prueba.

    :return: Variables con las tres ``CF_*`` y un token que no es real
    :rtype: dict
    """
    return {
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "acct-123",
        "CF_GATEWAY_ID": "hr-gateway",
        "CF_API_TOKEN": FAKE_CF_TOKEN,
    }


@pytest.fixture
def clock():
    """Reloj de prueba compartido por la aplicación y la prueba.

    :return: Reloj con hora fija
    :rtype: FakeClock
    """
    return FakeClock()


@pytest.fixture
def log_stream():
    """Destino del log en memoria, en lugar de la salida estándar.

    :return: Flujo de texto vacío
    :rtype: io.StringIO
    """
    return io.StringIO()


@pytest.fixture
def log_events(log_stream):
    """Lector del log: convierte cada línea escrita en un diccionario.

    :param log_stream: Flujo donde escribe la aplicación
    :type log_stream: io.StringIO
    :return: Función sin argumentos que devuelve los eventos escritos hasta ahora
    :rtype: collections.abc.Callable
    """

    def _read():
        lines = log_stream.getvalue().splitlines()
        return [json.loads(line) for line in lines]

    return _read


@pytest.fixture
def directory():
    """Directorio de empleados cargado desde ``data/employees.json``.

    :return: Directorio de solo lectura con los cinco empleados de ejemplo
    :rtype: EmployeeDirectory
    """
    return EmployeeDirectory(EMPLOYEES_FILE)


@pytest.fixture
def make_client(clock, log_stream):
    """Fábrica de clientes HTTP con la configuración que pida cada prueba.

    La observabilidad usa el ``FakeClock`` y el log en memoria de la prueba,
    métricas nuevas y un tracer que no hace nada. Si la prueba pasa un
    ``model``, ese modelo atiende las dos rutas (pequeño y grande); si no, se
    construyen con ``build_models``, que con ``MODEL_PROVIDER=gateway`` usa el
    ``http_client`` de la prueba (un ``httpx.MockTransport``, nunca la red).

    Si la prueba no pasa ``API_KEYS``, se configura el cliente ``tests`` con
    ``TEST_API_KEY``. El ``TestClient`` manda ``api_key`` en ``X-API-Key`` en
    cada petición; con ``api_key=None`` no manda ningún encabezado de clave.

    :param clock: Reloj de prueba
    :type clock: FakeClock
    :param log_stream: Destino del log
    :type log_stream: io.StringIO
    :return: Función que recibe un modelo opcional, un cliente HTTP opcional,
        la clave que se manda y variables de entorno, y devuelve un ``TestClient``
    :rtype: collections.abc.Callable
    """

    def _make(model=None, http_client=None, api_key=TEST_API_KEY, **env):
        env.setdefault("API_KEYS", f"{TEST_CLIENT}:{TEST_API_KEY}")
        settings = load_settings(env)
        employees = EmployeeDirectory(settings.employees_path)
        models = None
        if model is None:
            models = build_models(settings, employees, http_client=http_client)
        logger = JsonLogger(
            stream=log_stream,
            clock=clock,
            service=settings.observability.service_name,
        )
        observability = Observability(
            clock=clock, logger=logger, metrics=Metrics(), tracer=NullTracer()
        )
        app = create_app(
            settings=settings,
            model=model,
            directory=employees,
            observability=observability,
            models=models,
        )
        headers = {API_KEY_HEADER: api_key} if api_key else {}
        return TestClient(app, headers=headers)

    return _make


@pytest.fixture
def client(make_client):
    """Cliente HTTP con la configuración por omisión.

    :param make_client: Fábrica de clientes
    :type make_client: collections.abc.Callable
    :return: Cliente de prueba de la aplicación
    :rtype: TestClient
    """
    return make_client()


# Pasos compartidos por los escenarios que guardan sus respuestas en la fixture
# ``scenario_state`` de su módulo (observabilidad y costos). Un módulo que
# defina el mismo paso usa el suyo.


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(scenario_state, status):
    """Revisa el código HTTP de la última respuesta."""
    assert scenario_state["responses"][-1].status_code == status


@then(parsers.parse('the body says "{detail}" with the request id of the response'))
def body_has_detail_and_request_id(scenario_state, detail):
    """El error no explica la falla, pero da el id para soporte."""
    response = scenario_state["responses"][-1]
    expected = {"detail": detail, "request_id": response.headers["X-Request-ID"]}
    assert response.json() == expected


@then(parsers.parse('the log has one error event of type "{error_type}"'))
def log_has_error_event(scenario_state, log_events, error_type):
    """``error`` nombra el tipo y la línea ``request`` registra el mismo código."""
    events = log_events()
    (error,) = [event for event in events if event["event"] == "error"]
    (request,) = [event for event in events if event["event"] == "request"]
    response = scenario_state["responses"][-1]
    assert error["error_type"] == error_type
    assert request["status"] == response.status_code
    request_id = response.headers["X-Request-ID"]
    assert error["request_id"] == request["request_id"] == request_id
