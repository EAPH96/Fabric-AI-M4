"""Pruebas del límite de peticiones por cliente con un reloj manual.

``RateLimiter.check`` devuelve ``None`` si la petición pasa, o los segundos de
``Retry-After`` si el cliente ya usó su límite en los últimos 60 segundos.
"""

from app.ratelimit import RateLimiter


class ManualClock:
    """Reloj que solo avanza cuando la prueba lo pide.

    :param seconds: Valor inicial de ``monotonic``
    :type seconds: float
    """

    def __init__(self, seconds=0.0):
        self.seconds = seconds

    def monotonic(self):
        """Devuelve los segundos que fijó la prueba.

        :return: Segundos actuales
        :rtype: float
        """
        return self.seconds


def check_at(limiter, clock, seconds, client="hr"):
    """Mueve el reloj al segundo indicado y revisa al cliente."""
    clock.seconds = seconds
    return limiter.check(client)


def test_retry_after_rounds_up_and_is_never_zero():
    clock = ManualClock()
    limiter = RateLimiter(limit_per_minute=1, clock=clock)

    assert check_at(limiter, clock, 0.0) is None
    assert check_at(limiter, clock, 10.2) == 50
    assert check_at(limiter, clock, 59.99) == 1


def test_the_window_slides_and_a_rejection_is_not_counted():
    clock = ManualClock()
    limiter = RateLimiter(limit_per_minute=2, clock=clock)

    assert check_at(limiter, clock, 0.0) is None
    assert check_at(limiter, clock, 30.0) is None
    assert check_at(limiter, clock, 45.0) == 15
    assert check_at(limiter, clock, 61.0) is None
    assert check_at(limiter, clock, 62.0) == 28
