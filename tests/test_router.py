"""Pruebas del enrutador: una regla en código elige el modelo por pregunta."""

from app.config import RoutingSettings
from app.router import Route, choose_route

SMALL = "small-model"
LARGE = "large-model"
LIMIT = 30


def routing(enabled=True):
    """Configuración de enrutamiento con nombres cortos y un límite de 30."""
    return RoutingSettings(
        model_small=SMALL, model_large=LARGE, enabled=enabled, max_chars=LIMIT
    )


def test_question_at_the_limit_goes_small_and_one_more_character_goes_large():
    at_limit = "x" * LIMIT
    over_limit = "x" * (LIMIT + 1)

    assert choose_route(at_limit, routing()) == Route(SMALL, "simple")
    assert choose_route(over_limit, routing()) == Route(LARGE, "long_question")


def test_routing_keyword_counts_even_in_uppercase():
    route = choose_route("¿POR QUÉ salió EMP-0004?", routing())

    assert route == Route(LARGE, "keyword:por qué")


def test_disabled_routing_wins_over_every_other_reason():
    long_question_with_keyword = "Resume " + "x" * LIMIT

    route = choose_route(long_question_with_keyword, routing(enabled=False))

    assert route == Route(LARGE, "routing_disabled")
