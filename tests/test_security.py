"""Pruebas de las claves por cliente: lectura de ``API_KEYS`` e identificación.

Un error de ``API_KEYS`` nombra la entrada y su largo, nunca su valor: el
mensaje termina en la salida de arranque, que cualquiera puede leer.
"""

import pytest

from app.config import ConfigError
from app.security import ApiKeyAuth, parse_api_keys

HR_KEY = "hr-key-for-tests-0001"
PAYROLL_KEY = "payroll:key-with-colon-0002"


def test_api_keys_with_two_clients_are_parsed():
    keys = parse_api_keys(f"hr:{HR_KEY} , payroll:{PAYROLL_KEY}")

    assert keys == {"hr": HR_KEY, "payroll": PAYROLL_KEY}


@pytest.mark.parametrize(
    ("entry", "secret"),
    [
        ("secretvaluewithoutclient", "secretvaluewithoutclient"),
        (":secret-value-for-anyone", "secret-value-for-anyone"),
        ("payroll:", "payroll:"),
        ("hr:another-secret-value", "another-secret-value"),
    ],
    ids=["entry_without_colon", "empty_client", "empty_key", "repeated_client"],
)
def test_malformed_api_keys_entry_is_reported_without_its_value(entry, secret):
    with pytest.raises(ConfigError) as raised:
        parse_api_keys(f"hr:{HR_KEY},{entry}")

    message = str(raised.value)
    assert "entry 2" in message
    assert f"length {len(entry)}" in message
    assert secret not in message
    assert HR_KEY not in message


def test_identify_accepts_only_the_key_of_a_known_client():
    auth = ApiKeyAuth({"hr": HR_KEY, "payroll": PAYROLL_KEY})

    assert auth.identify(PAYROLL_KEY) == "payroll"
    assert auth.identify("not-the-right-key-0000") is None
    assert auth.identify(None) is None
    assert auth.identify("") is None
    assert auth.identify("clave-ñandú-no-ascii") is None
