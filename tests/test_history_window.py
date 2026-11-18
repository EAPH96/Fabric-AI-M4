"""Pruebas de la ventana de historial: al modelo solo llegan los últimos mensajes."""

import pytest

from app.agent import recent_history

HISTORY = [
    {"role": "user", "content": "uno"},
    {"role": "assistant", "content": "dos"},
    {"role": "user", "content": "tres"},
    {"role": "assistant", "content": "cuatro"},
]


@pytest.mark.parametrize(
    ("window", "expected"),
    [(0, []), (2, HISTORY[2:]), (10, HISTORY)],
    ids=["zero_window_sends_nothing", "smaller_window", "window_larger_than_history"],
)
def test_recent_history_keeps_only_the_last_messages(window, expected):
    original = [dict(message) for message in HISTORY]

    assert recent_history(HISTORY, window) == expected
    assert HISTORY == original
