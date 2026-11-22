"""Pruebas de la página de Políticas: plantilla real y enlace al HR escapado."""

from pathlib import Path

PRODUCT_DIR = Path(__file__).resolve().parents[1]
INDEX_FILE = PRODUCT_DIR / "app" / "static" / "index.html"
MARKER = "<!-- COMPANION_LINK -->"
LEGAL_NOTICE = "Políticas ficticias de ejemplo; no son asesoría legal"


def test_real_index_page_has_the_marker_the_notice_and_the_test_ids():
    page = INDEX_FILE.read_text(encoding="utf-8")

    assert page.count(MARKER) == 1
    assert "Asistente de políticas de RH" in page
    assert LEGAL_NOTICE in page
    for test_id in ("question", "send", "answer", "api-key"):
        assert f'data-testid="{test_id}"' in page
    assert "politicas-rh-api-key" in page
    assert "sessionStorage" in page
    assert "localStorage" not in page


def test_script_in_the_companion_name_is_shown_as_text(make_client, companion_links):
    hostile_name = "<script>alert(1)</script>"
    client = make_client(
        api_key=None,
        COMPANION_URL="https://hr.example.com/",
        COMPANION_NAME=hostile_name,
    )

    page = client.get("/").text

    assert hostile_name not in page
    (link,) = companion_links(page)
    assert link["text"] == hostile_name
