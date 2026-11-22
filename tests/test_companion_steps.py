"""Pasos de los escenarios de ``features/companion.feature``.

Cada escenario arma la aplicación sin clave en el ``TestClient`` y pasa
``COMPANION_URL`` y ``COMPANION_NAME`` como variables de entorno. Los enlaces se
leen con la fixture ``companion_links`` de ``conftest.py``, que devuelve los
atributos ya sin escapar, como los vería el navegador.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/companion.feature")

QUESTION = "¿Quién es EMP-0004?"


@pytest.fixture
def scenario_state():
    """Estado de un escenario: cliente HTTP y respuestas por ruta.

    :return: Diccionario vacío que llenan los pasos
    :rtype: dict
    """
    return {}


def _only_link(scenario_state, companion_links):
    """Devuelve el único enlace al otro producto de la página abierta."""
    links = companion_links(scenario_state["home"].text)
    assert len(links) == 1, f"expected one companion link, found {len(links)}"
    return links[0]


@given("the assistant is running without a companion URL")
def assistant_without_companion(scenario_state, make_client):
    """Aplicación con la configuración por omisión: sin enlace."""
    scenario_state["client"] = make_client(api_key=None)


@given(
    parsers.re(r'the assistant is running with the companion URL "(?P<url>[^"]+)"$')
)
def assistant_with_companion(scenario_state, make_client, url):
    """Aplicación con ``COMPANION_URL`` y el nombre por omisión."""
    scenario_state["client"] = make_client(api_key=None, COMPANION_URL=url)


@given(
    parsers.re(
        r'the assistant is running with the companion URL "(?P<url>[^"]+)"'
        r' named "(?P<name>[^"]+)"$'
    )
)
def assistant_with_named_companion(scenario_state, make_client, url, name):
    """Aplicación con ``COMPANION_URL`` y ``COMPANION_NAME``."""
    scenario_state["client"] = make_client(
        api_key=None, COMPANION_URL=url, COMPANION_NAME=name
    )


@when("I open the home page")
def open_home_page(scenario_state):
    """Pide ``GET /`` sin clave."""
    scenario_state["home"] = scenario_state["client"].get("/")


@when("I open the home page and ask without a key")
def open_home_and_ask(scenario_state):
    """Pide la página y hace una pregunta, las dos sin clave."""
    client = scenario_state["client"]
    scenario_state["home"] = client.get("/")
    scenario_state["ask"] = client.post("/ask", json={"question": QUESTION})


@then("the page has no companion link")
def page_has_no_link(scenario_state, companion_links):
    """Ni el enlace ni su ``data-testid`` aparecen en el HTML."""
    page = scenario_state["home"].text
    assert companion_links(page) == []
    assert 'data-testid="companion-link"' not in page


@then(parsers.parse('the page header has a companion link named "{name}"'))
def header_has_named_link(scenario_state, companion_links, name):
    """El enlace está dentro del ``<header>`` y muestra el nombre configurado."""
    link = _only_link(scenario_state, companion_links)
    assert link["in_header"]
    assert link["text"] == name


@then(parsers.parse('the companion link opens "{url}"'))
def link_opens_url(scenario_state, companion_links, url):
    """El ``href`` del enlace es la URL configurada."""
    assert _only_link(scenario_state, companion_links)["attrs"]["href"] == url


@then("the companion link opens in a new tab")
def link_opens_new_tab(scenario_state, companion_links):
    """Se abre en otra pestaña: la conversación vive solo en esta."""
    assert _only_link(scenario_state, companion_links)["attrs"]["target"] == "_blank"


@then("the companion link gives the other product no access to this page")
def link_has_no_opener(scenario_state, companion_links):
    """``rel`` lleva ``noopener`` y ``noreferrer``."""
    rel = _only_link(scenario_state, companion_links)["attrs"].get("rel") or ""
    assert {"noopener", "noreferrer"} <= set(rel.split())


@then("the home page answers 200")
def home_answers_200(scenario_state):
    """La página sigue abierta sin clave."""
    assert scenario_state["home"].status_code == 200


@then("the question answers 401")
def question_answers_401(scenario_state):
    """``POST /ask`` sigue pidiendo clave."""
    assert scenario_state["ask"].status_code == 401
