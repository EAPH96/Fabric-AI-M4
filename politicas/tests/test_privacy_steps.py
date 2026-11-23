"""Pasos de los escenarios de ``features/privacy.feature`` (spec 09).

Un modelo espía guarda cada conversación que recibe y responde un texto fijo;
un tracer espía guarda lo que entra y sale de cada traza. El log se lee del
``StringIO`` de ``conftest.py``. Los datos personales son ficticios: la CURP
genérica ``XEXX010101HDFXXX04`` y el dominio ``ejemplo.com``.
"""

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.llm import Completion

scenarios("features/privacy.feature")

SPY_ANSWER = "Respuesta del modelo espía"
DEFAULT_QUESTION = "¿Cuántos días de vacaciones me tocan?"
API_KEY_HEADER = "X-API-Key"
REQUEST_ID_HEADER = "X-Request-ID"
BASE_FIELDS = {"ts", "service", "event", "request_id"}


class SpyModel:  # pylint: disable=too-few-public-methods
    """Modelo espía: guarda cada conversación y responde siempre el mismo texto.

    :param answer: Respuesta final que devuelve en cada llamada
    :type answer: str
    """

    def __init__(self, answer=SPY_ANSWER):
        self.answer = answer
        self.calls = []

    def complete(self, messages):
        """Guarda una copia de la conversación y responde la respuesta fija.

        :param messages: Conversación que manda el agente
        :type messages: list[dict]
        :return: Respuesta final con tokens fijos
        :rtype: Completion
        """
        self.calls.append([dict(message) for message in messages])
        text = json.dumps({"answer": self.answer}, ensure_ascii=False)
        return Completion(text=text, input_tokens=10, output_tokens=5)


class SpyTracer:  # pylint: disable=too-few-public-methods
    """Tracer espía: guarda el tipo, las entradas y la salida de cada traza."""

    def __init__(self):
        self.runs = []

    # pylint: disable-next=unused-argument
    def wrap(self, function, run_type, request_id, client=None):
        """Envuelve la función para anotar lo que recibe y lo que devuelve.

        :param function: Función a envolver
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza (``chain``, ``llm`` o ``tool``)
        :type run_type: str
        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente, o ``None``
        :type client: str or None
        :return: Función con la misma firma que anota cada llamada
        :rtype: collections.abc.Callable
        """

        def traced(*args, **kwargs):
            output = function(*args, **kwargs)
            self.runs.append(
                {
                    "run_type": run_type,
                    "inputs": repr((args, kwargs)),
                    "output": repr(output),
                }
            )
            return output

        return traced


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente, modelo, tracer y respuestas.

    :return: Diccionario con la lista ``responses``
    :rtype: dict
    """
    return {"responses": []}


def _last_response(scenario_state):
    """Devuelve la última respuesta HTTP del escenario."""
    return scenario_state["responses"][-1]


def _last_body(scenario_state):
    """Devuelve el cuerpo JSON de la última respuesta."""
    return _last_response(scenario_state).json()


def _events_named(log_events, name):
    """Devuelve los eventos del log con el nombre indicado."""
    return [event for event in log_events() if event["event"] == name]


def _post(scenario_state, body, headers=None):
    """Envía ``POST /ask`` y guarda la respuesta."""
    response = scenario_state["client"].post("/ask", json=body, headers=headers)
    scenario_state["responses"].append(response)


def _chain_run(scenario_state):
    """Devuelve la única traza ``chain`` de la petición."""
    runs = scenario_state["tracer"].runs
    (chain,) = [run for run in runs if run["run_type"] == "chain"]
    return chain


@given("the assistant is running with the default settings")
def assistant_with_default_settings(scenario_state, make_client):
    """Modelos simulados con la configuración por omisión."""
    scenario_state["client"] = make_client()


@given("the assistant is running with a spy model")
def assistant_with_spy_model(scenario_state, make_client):
    """Un modelo espía atiende las dos rutas del enrutador."""
    scenario_state["model"] = SpyModel()
    scenario_state["client"] = make_client(model=scenario_state["model"])


@given(
    parsers.parse('the assistant is running with a model that answers "{answer}"')
)
def assistant_with_answering_model(scenario_state, make_client, answer):
    """Un modelo espía responde el texto del escenario."""
    scenario_state["model"] = SpyModel(answer)
    scenario_state["client"] = make_client(model=scenario_state["model"])


@given(
    parsers.parse(
        "the assistant is running with a spy tracer"
        ' and a model that answers "{answer}"'
    )
)
def assistant_with_spy_tracer(scenario_state, make_client, answer):
    """Un tracer espía guarda cada traza y el modelo responde el texto dado."""
    scenario_state["model"] = SpyModel(answer)
    scenario_state["tracer"] = SpyTracer()
    scenario_state["client"] = make_client(
        model=scenario_state["model"], tracer=scenario_state["tracer"]
    )


@given("the assistant is running without a key in the client")
def assistant_without_key(scenario_state, make_client):
    """El ``TestClient`` no manda clave: cada paso decide qué encabezado va."""
    scenario_state["client"] = make_client(api_key=None)


@given(parsers.parse("the assistant allows {limit:d} question per minute"))
def assistant_with_rate_limit(scenario_state, make_client, limit):
    """Límite pequeño por minuto para el cliente ``tests``."""
    scenario_state["client"] = make_client(RATE_LIMIT_PER_MINUTE=str(limit))


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask_question(scenario_state, question):
    """Pregunta sin historial."""
    _post(scenario_state, {"question": question})


@when(parsers.re(r'I ask "(?P<question>[^"]+)" after saying "(?P<earlier>[^"]+)"'))
def ask_after_saying(scenario_state, question, earlier):
    """Pregunta con un mensaje previo de la persona en el historial."""
    history = [{"role": "user", "content": earlier}]
    _post(scenario_state, {"question": question, "history": history})


@when("I ask without a key")
def ask_without_key(scenario_state):
    """Pregunta sin encabezado ``X-API-Key``."""
    _post(scenario_state, {"question": DEFAULT_QUESTION})


@when(parsers.re(r'I ask with the key "(?P<key>[^"]*)"'))
def ask_with_key(scenario_state, key):
    """Pregunta con la clave indicada."""
    _post(scenario_state, {"question": DEFAULT_QUESTION}, {API_KEY_HEADER: key})


@when(parsers.parse("I ask {count:d} questions in a row"))
def ask_in_a_row(scenario_state, count):
    """Hace varias preguntas seguidas con la clave de prueba."""
    for _ in range(count):
        _post(scenario_state, {"question": DEFAULT_QUESTION})


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(scenario_state, status):
    """Revisa el código HTTP de la última respuesta."""
    assert _last_response(scenario_state).status_code == status


@then(parsers.parse('the masked types are "{types}"'))
def masked_types_are(scenario_state, types):
    """``pii_masked`` lista los tipos ordenados y sin repetir."""
    assert _last_body(scenario_state)["pii_masked"] == types.split(", ")


@then("no personal data was masked")
def no_personal_data_masked(scenario_state, log_events):
    """Sin PII, ``pii_masked`` es una lista vacía y no hay ``pii_detected``."""
    assert _last_body(scenario_state)["pii_masked"] == []
    assert not _events_named(log_events, "pii_detected")


@then(parsers.parse('the answer is "{text}"'))
def answer_is(scenario_state, text):
    """La respuesta es exactamente el texto."""
    assert _last_body(scenario_state)["answer"] == text


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(scenario_state, text):
    """La respuesta contiene el texto."""
    assert text in _last_body(scenario_state)["answer"]


@then(parsers.parse('the tools used are "{names}"'))
def tools_used_are(scenario_state, names):
    """Las herramientas usadas, en orden."""
    assert _last_body(scenario_state)["tools_used"] == names.split(", ")


@then("no tools were used")
def no_tools_were_used(scenario_state):
    """No se usó ninguna herramienta."""
    assert _last_body(scenario_state)["tools_used"] == []


@then(parsers.parse('the model received "{text}"'))
def model_received(scenario_state, text):
    """El texto aparece en alguna conversación que recibió el modelo."""
    received = json.dumps(scenario_state["model"].calls, ensure_ascii=False)
    assert text in received


@then(parsers.parse('the model never received "{text}"'))
def model_never_received(scenario_state, text):
    """El texto no aparece en ninguna conversación que recibió el modelo."""
    received = json.dumps(scenario_state["model"].calls, ensure_ascii=False)
    assert text not in received


@then(
    parsers.parse(
        'the log has a pii detected event in the "{where}" with the types "{types}"'
    )
)
def log_has_pii_event(scenario_state, log_events, where, types):
    """Un ``pii_detected`` por lugar, con sus tipos y el id de la petición."""
    events = [
        event
        for event in _events_named(log_events, "pii_detected")
        if event["where"] == where
    ]
    (event,) = events
    assert event["types"] == types.split(", ")
    request_id = _last_response(scenario_state).headers[REQUEST_ID_HEADER]
    assert event["request_id"] == request_id


@then(parsers.parse('the log never contains "{text}"'))
def log_never_contains(log_stream, text):
    """El texto no aparece en ninguna línea del log."""
    assert text not in log_stream.getvalue()


@then(
    parsers.parse(
        'the chain trace received "{question_mark}" and returned "{answer_mark}"'
    )
)
def chain_trace_is_masked(scenario_state, question_mark, answer_mark):
    """La traza ``chain`` recibe la pregunta y devuelve la respuesta enmascaradas."""
    chain = _chain_run(scenario_state)
    assert question_mark in chain["inputs"]
    assert answer_mark in chain["output"]


@then(parsers.parse('the chain trace never contains "{text}"'))
def chain_trace_never_contains(scenario_state, text):
    """El valor no está ni en la entrada ni en la salida de la traza ``chain``."""
    chain = _chain_run(scenario_state)
    assert text not in chain["inputs"]
    assert text not in chain["output"]


@then(
    parsers.parse('the log has one auth failed event with only the reason "{reason}"')
)
def log_has_auth_failed(scenario_state, log_events, reason):
    """``auth_failed`` lleva solo ``reason``: ningún campo puede traer la clave."""
    (event,) = _events_named(log_events, "auth_failed")
    assert event["reason"] == reason
    assert set(event) == BASE_FIELDS | {"reason"}
    request_id = _last_response(scenario_state).headers[REQUEST_ID_HEADER]
    assert event["request_id"] == request_id


@then(
    parsers.parse(
        'the log has one rate limited event for the client "{client}"'
        " with the Retry-After seconds"
    )
)
def log_has_rate_limited(scenario_state, log_events, client):
    """``rate_limited`` nombra al cliente y los mismos segundos de ``Retry-After``."""
    response = _last_response(scenario_state)
    (event,) = _events_named(log_events, "rate_limited")
    assert event["client"] == client
    assert isinstance(event["retry_after"], int)
    assert event["retry_after"] == int(response.headers["Retry-After"])
    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
