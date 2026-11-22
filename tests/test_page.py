"""Pruebas del armado de la página con el enlace al otro producto.

``render_index`` recibe la plantilla y ``PageSettings`` y pone el enlace en
lugar del marcador ``<!-- COMPANION_LINK -->``; sin URL, el marcador se borra.
"""

from pathlib import Path

from app.config import PageSettings
from app.page import companion_link_html, render_index

PRODUCT_DIR = Path(__file__).resolve().parents[1]
INDEX_FILE = PRODUCT_DIR / "app" / "static" / "index.html"
MARKER = "<!-- COMPANION_LINK -->"
TEMPLATE = f"<header><h1>HR Assistant</h1>{MARKER}</header><main></main>"
DEFAULT_NAME = "Asistente de políticas de RH"
POLICIES_URL = "https://politicas.example.com/"


def _page(url="", name=DEFAULT_NAME):
    """Configuración de la página con la URL y el nombre dados."""
    return PageSettings(
        max_question_chars=2000, companion_url=url, companion_name=name
    )


def test_without_url_the_page_keeps_neither_the_link_nor_the_marker():
    rendered = render_index(TEMPLATE, _page())

    assert "COMPANION_LINK" not in rendered
    assert "companion-link" not in rendered
    assert rendered == "<header><h1>HR Assistant</h1></header><main></main>"


def test_link_html_is_empty_without_url():
    assert companion_link_html("", DEFAULT_NAME) == ""


def test_url_with_quotes_and_angle_brackets_stays_inside_the_href(companion_links):
    hostile_url = 'https://evil.example.com/"><script>alert(1)</script>'

    rendered = render_index(TEMPLATE, _page(url=hostile_url))

    assert "<script>" not in rendered
    (link,) = companion_links(rendered)
    assert link["attrs"]["href"] == hostile_url


def test_script_in_the_name_is_shown_as_text(companion_links):
    hostile_name = "<script>alert(1)</script>"

    rendered = render_index(TEMPLATE, _page(url=POLICIES_URL, name=hostile_name))

    assert "<script>" not in rendered
    (link,) = companion_links(rendered)
    assert link["text"] == hostile_name


def test_with_url_the_link_is_inside_the_header_of_the_real_page(companion_links):
    template = INDEX_FILE.read_text(encoding="utf-8")

    rendered = render_index(template, _page(url=POLICIES_URL))

    (link,) = companion_links(rendered)
    assert link["in_header"]
    assert link["attrs"]["href"] == POLICIES_URL
    assert link["text"] == DEFAULT_NAME
    assert MARKER not in rendered


def test_real_index_page_has_the_marker_exactly_once():
    page = INDEX_FILE.read_text(encoding="utf-8")

    assert page.count(MARKER) == 1
