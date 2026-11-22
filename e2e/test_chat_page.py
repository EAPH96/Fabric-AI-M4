"""Pruebas de punta a punta de la página del HR Assistant.

Usan la página como una persona: escriben la clave, escriben en la caja de
pregunta, pulsan Enviar y revisan lo que queda en pantalla. El producto corre
con el modelo simulado; la URL base y la clave (``E2E_API_KEY``) las pone la
verificación. La clave nunca se escribe en este archivo. El producto arranca
sin ``COMPANION_URL``, así que la página no debe mostrar el enlace a Políticas.
"""

import os
import re

from playwright.sync_api import Page, expect

FIRST_QUESTION = "¿Quién es EMP-0004?"
SECOND_QUESTION = "¿Quién es EMP-0001?"
SPANISH_QUESTION_ERROR = re.compile(r"pregunta|vac[ií]a", re.IGNORECASE)
INVALID_KEY_MESSAGE = re.compile(r"Clave inv[aá]lida", re.IGNORECASE)
# Valor que no es una clave del producto: sirve para provocar el 401.
WRONG_API_KEY = "this-is-not-a-valid-client-key"


def _enter_api_key(page: Page, api_key: str | None = None) -> None:
    """Escribe la clave del cliente en su campo de la página.

    :param page: Página de Playwright ya abierta en el producto
    :type page: Page
    :param api_key: Clave que se escribe; por omisión, la de ``E2E_API_KEY``
    :type api_key: str | None
    """
    key = api_key if api_key is not None else os.environ["E2E_API_KEY"]
    page.get_by_test_id("api-key").fill(key)


def _ask(page: Page, question: str) -> dict:
    """Escribe una pregunta, la envía y devuelve el cuerpo de la respuesta.

    :param page: Página de Playwright ya abierta en el producto
    :type page: Page
    :param question: Texto de la pregunta
    :type question: str
    :return: Cuerpo JSON de la respuesta de ``POST /ask``
    :rtype: dict
    """
    page.get_by_test_id("question").fill(question)
    with page.expect_response(re.compile(r"/ask$")) as response_info:
        page.get_by_test_id("send").click()
    response = response_info.value
    assert response.ok, f"/ask respondió {response.status}"
    return response.json()


def test_asking_a_question_shows_the_answer_and_its_request_id(page: Page):
    """La respuesta y su ``request_id`` aparecen en pantalla."""
    page.goto("/")
    _enter_api_key(page)

    body = _ask(page, FIRST_QUESTION)

    conversation = page.get_by_test_id("answer")
    expect(conversation).to_contain_text(FIRST_QUESTION)
    expect(conversation).to_contain_text(body["answer"])
    request_id = page.get_by_test_id("request-id")
    expect(request_id).to_have_count(1)
    expect(request_id).to_be_visible()
    expect(request_id).to_contain_text(body["request_id"])


def test_an_empty_or_blank_question_shows_an_error_message_in_spanish(page: Page):
    """Enviar sin texto o con solo espacios muestra un error en español.

    Cada intento deja su propio mensaje de error y ninguno llega a la API, así
    que no aparece ningún ``request_id``.
    """
    page.goto("/")
    _enter_api_key(page)
    errors = page.get_by_test_id("answer").get_by_text(SPANISH_QUESTION_ERROR)

    page.get_by_test_id("send").click()
    expect(errors).to_have_count(1)

    page.get_by_test_id("question").fill("   ")
    page.get_by_test_id("send").click()
    expect(errors).to_have_count(2)

    expect(page.get_by_test_id("request-id")).to_have_count(0)


def test_a_second_question_keeps_the_previous_conversation_on_screen(page: Page):
    """Tras la segunda pregunta, la primera y su respuesta siguen visibles."""
    page.goto("/")
    _enter_api_key(page)

    first = _ask(page, FIRST_QUESTION)
    request_ids = page.get_by_test_id("request-id")
    expect(request_ids).to_have_count(1)
    second = _ask(page, SECOND_QUESTION)

    conversation = page.get_by_test_id("answer")
    expect(request_ids).to_have_count(2)
    expect(conversation).to_contain_text(FIRST_QUESTION)
    expect(conversation).to_contain_text(first["answer"])
    expect(conversation).to_contain_text(SECOND_QUESTION)
    expect(conversation).to_contain_text(second["answer"])
    expect(request_ids.nth(0)).to_contain_text(first["request_id"])
    expect(request_ids.nth(1)).to_contain_text(second["request_id"])


def test_a_wrong_api_key_shows_an_invalid_key_message(page: Page):
    """Con una clave equivocada, la página muestra «Clave inválida»."""
    page.goto("/")
    _enter_api_key(page, WRONG_API_KEY)

    page.get_by_test_id("question").fill(FIRST_QUESTION)
    with page.expect_response(re.compile(r"/ask$")) as response_info:
        page.get_by_test_id("send").click()

    assert response_info.value.status == 401
    expect(page.get_by_test_id("answer")).to_contain_text(INVALID_KEY_MESSAGE)


def test_without_a_companion_url_the_header_shows_no_companion_link(page: Page):
    """Sin ``COMPANION_URL`` la página carga y no muestra el enlace al otro producto.

    La verificación arranca el producto sin ``COMPANION_URL``. La caja de
    pregunta visible confirma que la página ya cargó antes de buscar el enlace.
    """
    page.goto("/")

    expect(page.get_by_test_id("question")).to_be_visible()
    expect(page.get_by_test_id("companion-link")).to_have_count(0)


def test_the_api_key_field_hides_the_key_and_keeps_it_only_in_session_storage(
    page: Page,
):
    """El campo de clave es de contraseña y la clave vive en ``sessionStorage``."""
    page.goto("/")
    api_key_field = page.get_by_test_id("api-key")
    expect(api_key_field).to_have_attribute("type", "password")
    _enter_api_key(page)

    _ask(page, FIRST_QUESTION)

    api_key = os.environ["E2E_API_KEY"]
    page.wait_for_function(
        "key => Object.values(window.sessionStorage).includes(key)", arg=api_key
    )
    in_local_storage = page.evaluate(
        "key => Object.values(window.localStorage).includes(key)", api_key
    )
    assert not in_local_storage, "la clave no debe guardarse en localStorage"
