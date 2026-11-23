"""Fixtures compartidas del Asistente de políticas de RH.

La aplicación se arma con ``create_app()`` y dependencias inyectadas: las
pruebas nunca leen ``os.environ`` ni usan la red. La hora sale de un
``FakeClock``, el log se escribe en memoria y el gateway es un
``httpx.MockTransport``.

``make_client`` configura por omisión un cliente ``tests`` con una clave de
prueba y la manda en cada petición; con ``api_key=None`` no manda ninguna.
"""

import io
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.llm import build_models
from app.logs import JsonLogger
from app.main import create_app
from app.metrics import Metrics
from app.observability import Observability
from app.policies import PolicyCatalog
from app.tracing import NullTracer

PRODUCT_DIR = Path(__file__).resolve().parents[1]
POLICIES_FILE = PRODUCT_DIR / "data" / "policies.json"
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


class FakeGateway:
    """AI Gateway simulado con ``httpx.MockTransport``: nunca usa la red.

    Guarda cada petición y responde como Workers AI. Cada prueba cambia
    ``status``, ``content`` o ``headers`` para simular otra respuesta; con
    ``cf-aig-cache-status: HIT`` en ``headers`` responde como la caché.
    """

    PROMPT_TOKENS = 120
    COMPLETION_TOKENS = 15

    def __init__(self):
        self.requests = []
        self.status = 200
        self.content = json.dumps({"answer": "Hola desde el gateway"})
        self.headers = {}

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
        """
        self.requests.append(request)
        payload = {
            "choices": [{"message": {"role": "assistant", "content": self.content}}],
            "usage": {
                "prompt_tokens": self.PROMPT_TOKENS,
                "completion_tokens": self.COMPLETION_TOKENS,
            },
        }
        return httpx.Response(self.status, json=payload, headers=self.headers)


class CompanionLinkParser(HTMLParser):
    """Junta los enlaces ``data-testid="companion-link"`` de una página.

    De cada enlace guarda sus atributos ya sin escapar, su texto visible y si
    está dentro de un ``<header>``, como lo vería el navegador.
    """

    def __init__(self):
        super().__init__()
        self.links = []
        self._header_depth = 0
        self._current = None

    def handle_starttag(self, tag, attrs):
        """Abre un ``<header>`` o empieza un enlace al otro producto."""
        if tag == "header":
            self._header_depth += 1
        attributes = dict(attrs)
        if tag == "a" and attributes.get("data-testid") == "companion-link":
            self._current = {
                "attrs": attributes,
                "text": "",
                "in_header": self._header_depth > 0,
            }

    def handle_endtag(self, tag):
        """Cierra el ``<header>`` o termina el enlace en curso."""
        if tag == "header" and self._header_depth:
            self._header_depth -= 1
        if tag == "a" and self._current is not None:
            self._current["text"] = self._current["text"].strip()
            self.links.append(self._current)
            self._current = None

    def handle_data(self, data):
        """Suma el texto visible del enlace en curso."""
        if self._current is not None:
            self._current["text"] += data


@pytest.fixture
def companion_links():
    """Lector de los enlaces al otro producto que trae una página.

    :return: Función que recibe el HTML y devuelve una lista de diccionarios
        con ``attrs``, ``text`` e ``in_header``
    :rtype: collections.abc.Callable
    """

    def _find(page):
        parser = CompanionLinkParser()
        parser.feed(page)
        parser.close()
        return parser.links

    return _find


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
        "CF_GATEWAY_ID": "politicas-gateway",
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
        return [json.loads(line) for line in log_stream.getvalue().splitlines()]

    return _read


@pytest.fixture
def catalog():
    """Catálogo de políticas cargado desde ``data/policies.json``.

    :return: Catálogo de solo lectura con las diez políticas de ejemplo
    :rtype: PolicyCatalog
    """
    return PolicyCatalog(POLICIES_FILE)


@pytest.fixture
def make_client(clock, log_stream):
    """Fábrica de clientes HTTP con la configuración que pida cada prueba.

    Los modelos se construyen con ``build_models``: con ``MODEL_PROVIDER=fake``
    son los simulados y con ``gateway`` usan el ``http_client`` de la prueba
    (un ``httpx.MockTransport``, nunca la red). Si la prueba pasa un
    ``model``, ese modelo atiende las dos rutas; si pasa un ``tracer`` (por
    ejemplo un espía), se usa en lugar del ``NullTracer``. Si la prueba no
    pasa ``API_KEYS``, se configura el cliente ``tests`` con ``TEST_API_KEY``.

    :param clock: Reloj de prueba
    :type clock: FakeClock
    :param log_stream: Destino del log
    :type log_stream: io.StringIO
    :return: Función que recibe un cliente HTTP opcional, la clave que se
        manda, un modelo y un tracer opcionales y variables de entorno, y
        devuelve un ``TestClient``
    :rtype: collections.abc.Callable
    """

    def _make(
        http_client=None, api_key=TEST_API_KEY, model=None, tracer=None, **env
    ):
        env.setdefault("API_KEYS", f"{TEST_CLIENT}:{TEST_API_KEY}")
        settings = load_settings(env)
        policies = PolicyCatalog(settings.policies_path)
        models = None
        if model is None:
            models = build_models(settings, policies, http_client=http_client)
        logger = JsonLogger(
            stream=log_stream,
            clock=clock,
            service=settings.observability.service_name,
        )
        observability = Observability(
            clock=clock,
            logger=logger,
            metrics=Metrics(),
            tracer=NullTracer() if tracer is None else tracer,
        )
        app = create_app(
            settings=settings,
            model=model,
            catalog=policies,
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
