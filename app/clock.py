"""Reloj inyectable: el único lugar del producto que lee la hora del sistema.

Las piezas que necesitan la hora (log y middleware) reciben un ``Clock``; las
pruebas pasan uno falso para ser deterministas.
"""

import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Interfaz de un reloj: hora de pared en UTC y un contador monotónico."""

    def now(self) -> datetime:
        """Devuelve la hora actual con zona UTC.

        :return: Hora actual con ``tzinfo`` UTC
        :rtype: datetime.datetime
        """

    def monotonic(self) -> float:
        """Devuelve segundos de un contador que nunca retrocede.

        :return: Segundos desde un origen arbitrario
        :rtype: float
        """


class SystemClock:
    """Reloj real del sistema operativo."""

    def now(self):
        """Devuelve la hora actual del sistema con zona UTC.

        :return: Hora actual con ``tzinfo`` UTC
        :rtype: datetime.datetime
        """
        return datetime.now(timezone.utc)

    def monotonic(self):
        """Devuelve el contador monotónico del sistema.

        :return: Segundos desde un origen arbitrario
        :rtype: float
        """
        return time.monotonic()
