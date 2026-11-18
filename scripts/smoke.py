"""Prueba de humo contra el HR Assistant publicado.

Uso: ``SMOKE_API_KEY=<clave> python scripts/smoke.py https://<servicio>.onrender.com``

La clave se lee solo de la variable ``SMOKE_API_KEY``, nunca de un argumento,
para que no quede en el historial de la terminal. Comprueba tres cosas e imprime
``[OK]`` o ``[FAIL]`` en cada una:

- ``GET /health`` responde 200.
- ``POST /ask`` sin clave responde 401.
- ``POST /ask`` con clave responde 200.
"""

import os
import sys
from collections.abc import Callable

import httpx

QUESTION = {"question": "¿Quién es EMP-0004?"}
# Render despierta un servicio gratuito dormido en hasta un minuto.
TIMEOUT_SECONDS = 90
USAGE = "Uso: SMOKE_API_KEY=<clave> python scripts/smoke.py <url>"


def check(name: str, expected: int, send: Callable[[], httpx.Response]) -> bool:
    """Hace una petición, imprime ``[OK]`` o ``[FAIL]`` y dice si pasó.

    El código recibido ayuda a ver la causa (401: la clave no coincide; 502: el
    modelo no responde). Nunca se imprime la clave.

    :param name: Nombre de la comprobación
    :type name: str
    :param expected: Código HTTP esperado
    :type expected: int
    :param send: Función que hace la petición
    :type send: Callable[[], httpx.Response]
    :return: ``True`` si el código fue el esperado
    :rtype: bool
    """
    try:
        status = send().status_code
    except httpx.HTTPError as error:
        print(f"  [FAIL] {name} -> {type(error).__name__} (esperado {expected})")
        return False
    passed = status == expected
    label = "OK" if passed else "FAIL"
    print(f"  [{label}] {name} -> {status} (esperado {expected})")
    return passed


def smoke(url: str, key: str, client: httpx.Client) -> bool:
    """Corre las tres comprobaciones contra ``url``.

    :param url: URL base del servicio, sin barra final
    :type url: str
    :param key: Clave de un cliente del servicio
    :type key: str
    :param client: Cliente HTTP con el que se hacen las peticiones
    :type client: httpx.Client
    :return: ``True`` si las tres pasan
    :rtype: bool
    """
    results = [
        check("GET /health", 200, lambda: client.get(f"{url}/health")),
        check(
            "POST /ask sin clave",
            401,
            lambda: client.post(f"{url}/ask", json=QUESTION),
        ),
        check(
            "POST /ask con clave",
            200,
            lambda: client.post(
                f"{url}/ask", json=QUESTION, headers={"X-API-Key": key}
            ),
        ),
    ]
    return all(results)


def main(args: list[str]) -> int:
    """Lee la URL y la clave y corre la prueba de humo.

    :param args: Argumentos de la línea de comandos; solo la URL
    :type args: list[str]
    :return: 0 si todo pasa, 1 si algo falla, 2 si falta la URL o la clave
    :rtype: int
    """
    key = os.environ.get("SMOKE_API_KEY", "")
    if len(args) != 1 or not key:
        print(USAGE)
        return 2
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        passed = smoke(args[0].rstrip("/"), key, client)
    print("[OK] smoke" if passed else "[FAIL] smoke")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
