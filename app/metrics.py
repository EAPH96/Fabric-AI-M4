"""Métricas en memoria de este proceso.

Son estado operativo, no de negocio (ADR 0005): cada copia del servicio tiene
las suyas y las identifica con su ``pid``. Las latencias se guardan en una
ventana acotada para que la memoria no crezca sin límite.
"""

import math
import os
import threading
from collections import deque

LATENCY_WINDOW = 1000
SERVER_ERROR_STATUS = 500
PERCENT = 100


def nearest_rank(sorted_values, percentile):
    """Calcula un percentil por el método del rango más cercano.

    :param sorted_values: Valores ordenados de menor a mayor
    :type sorted_values: list[float]
    :param percentile: Percentil entre 1 y 100
    :type percentile: int
    :return: Valor del percentil, o ``0`` si no hay valores
    :rtype: float
    """
    if not sorted_values:
        return 0
    rank = math.ceil(percentile / PERCENT * len(sorted_values))
    return sorted_values[max(rank, 1) - 1]


class Metrics:
    """Contadores de peticiones, errores, latencias y tokens del proceso.

    Es seguro entre hilos: los endpoints síncronos corren en varios hilos.

    :param window: Número máximo de latencias que se guardan
    :type window: int
    """

    def __init__(self, window=LATENCY_WINDOW):
        self._lock = threading.Lock()
        self._latencies = deque(maxlen=window)
        self._requests = 0
        self._server_errors = 0
        self._tokens = {"input": 0, "output": 0}
        self._cost_usd = 0.0

    def record_request(self, status, latency_ms):
        """Registra una petición atendida.

        :param status: Código HTTP de la respuesta
        :type status: int
        :param latency_ms: Latencia de la petición en milisegundos
        :type latency_ms: float
        """
        with self._lock:
            self._requests += 1
            if status >= SERVER_ERROR_STATUS:
                self._server_errors += 1
            self._latencies.append(float(latency_ms))

    def add_tokens(self, input_tokens, output_tokens):
        """Suma los tokens de una corrida del agente.

        :param input_tokens: Tokens de entrada
        :type input_tokens: int
        :param output_tokens: Tokens de salida
        :type output_tokens: int
        """
        with self._lock:
            self._tokens["input"] += input_tokens
            self._tokens["output"] += output_tokens

    def add_cost(self, cost_usd):
        """Suma el costo de una respuesta.

        :param cost_usd: Costo en USD, sin redondear
        :type cost_usd: float
        """
        with self._lock:
            self._cost_usd += cost_usd

    def snapshot(self, slo_p95_ms):
        """Devuelve las métricas actuales con el estado de la meta de latencia.

        :param slo_p95_ms: Meta de latencia p95 en milisegundos
        :type slo_p95_ms: int
        :return: ``pid``, ``requests``, ``error_rate``, ``latency_ms``,
            ``tokens``, ``slo`` y ``cost_usd`` acumulado
        :rtype: dict
        """
        with self._lock:
            latencies = sorted(self._latencies)
            requests = self._requests
            server_errors = self._server_errors
            tokens = dict(self._tokens)
            cost_usd = self._cost_usd
        p95 = nearest_rank(latencies, 95)
        error_rate = round(server_errors / requests, 4) if requests else 0.0
        return {
            "pid": os.getpid(),
            "requests": requests,
            "error_rate": error_rate,
            "latency_ms": {"p50": nearest_rank(latencies, 50), "p95": p95},
            "tokens": tokens,
            "slo": {"p95_ms_target": slo_p95_ms, "met": p95 < slo_p95_ms},
            "cost_usd": cost_usd,
        }
