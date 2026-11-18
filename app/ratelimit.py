"""Límite de peticiones por cliente, en memoria y con reloj inyectado (ADR 0011).

Ventana deslizante de 60 segundos: por cada cliente se guardan las marcas de
``clock.monotonic()`` de sus peticiones aceptadas en el último minuto. Un
rechazo no se agrega a la ventana. El límite vive en este proceso: con varias
copias o varios workers, cada uno cuenta por su lado.
"""

import math
import threading
from collections import deque

WINDOW_SECONDS = 60
MIN_RETRY_AFTER_SECONDS = 1


class RateLimiter:
    """Cuenta las peticiones de cada cliente en el último minuto.

    Es seguro entre hilos: FastAPI atiende las dependencias síncronas en un
    grupo de hilos.

    :param limit_per_minute: Peticiones aceptadas por cliente en 60 segundos
    :type limit_per_minute: int
    :param clock: Reloj con ``monotonic()`` (el de ``Observability``)
    :type clock: app.clock.Clock
    """

    def __init__(self, limit_per_minute, clock):
        self._limit = limit_per_minute
        self._clock = clock
        self._accepted = {}
        self._lock = threading.Lock()

    def check(self, client):
        """Acepta la petición del cliente o dice cuánto debe esperar.

        :param client: Nombre del cliente ya identificado
        :type client: str
        :return: ``None`` si la petición pasa (y queda contada); si no, los
            segundos de ``Retry-After``, redondeados hacia arriba y nunca 0
        :rtype: int or None
        """
        with self._lock:
            now = self._clock.monotonic()
            accepted = self._accepted.setdefault(client, deque())
            while accepted and now - accepted[0] >= WINDOW_SECONDS:
                accepted.popleft()
            if len(accepted) >= self._limit:
                wait = math.ceil(accepted[0] + WINDOW_SECONDS - now)
                return max(MIN_RETRY_AFTER_SECONDS, wait)
            accepted.append(now)
            return None
