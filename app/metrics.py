"""Métricas en memoria de este proceso.

No influyen en las respuestas (ADR 0005 y 0015): cada copia del servicio tiene
las suyas y las identifica con su ``pid``. Las latencias se guardan en una
ventana acotada para que la memoria no crezca sin límite.

Las métricas de negocio (``by_model``, ``cached_calls``, ``stopped``,
``tools`` y ``status``) usan el mismo candado; sus llaves son nombres de
modelo, de herramienta o de clase de código, nunca textos ni datos personales
(ADR 0015). Dónde se suma cada una lo fija el ADR 0016.
"""

import math
import os
import threading
from collections import deque
from dataclasses import dataclass, field

LATENCY_WINDOW = 1000
CLIENT_ERROR_STATUS = 400
SERVER_ERROR_STATUS = 500
PERCENT = 100
STATUS_OK = "2xx"
STATUS_CLIENT_ERROR = "4xx"
STATUS_SERVER_ERROR = "5xx"


def status_class(status):
    """Clasifica un código HTTP en ``2xx``, ``4xx`` o ``5xx``.

    Todo lo que no es error del cliente ni del servidor (por ejemplo, una
    redirección) cuenta como ``2xx``, para que la suma de las tres clases sea
    siempre el número de peticiones (ADR 0016).

    :param status: Código HTTP de la respuesta
    :type status: int
    :return: ``5xx`` si es 500 o más, ``4xx`` de 400 a 499 y ``2xx`` si no
    :rtype: str
    """
    if status >= SERVER_ERROR_STATUS:
        return STATUS_SERVER_ERROR
    if status >= CLIENT_ERROR_STATUS:
        return STATUS_CLIENT_ERROR
    return STATUS_OK


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


def empty_status():
    """Crea el conteo por clase de código con las tres llaves en cero.

    :return: ``2xx``, ``4xx`` y ``5xx`` en ``0``
    :rtype: dict[str, int]
    """
    return {STATUS_OK: 0, STATUS_CLIENT_ERROR: 0, STATUS_SERVER_ERROR: 0}


@dataclass
class BusinessCounts:
    """Métricas de negocio del proceso.

    No tiene candado propio: ``Metrics`` la cambia y la lee solo dentro del
    suyo.

    :param by_model: Por nombre de modelo, ``requests`` y ``cost_usd``
    :type by_model: dict[str, dict]
    :param cached_calls: Llamadas que respondió la caché del gateway
    :type cached_calls: int
    :param stopped: Respuestas cortadas por el tope de pasos
    :type stopped: int
    :param tools: Por nombre de herramienta, las veces que se ejecutó
    :type tools: dict[str, int]
    :param status: Peticiones por clase de código
    :type status: dict[str, int]
    """

    by_model: dict = field(default_factory=dict)
    cached_calls: int = 0
    stopped: int = 0
    tools: dict = field(default_factory=dict)
    status: dict = field(default_factory=empty_status)

    def as_dict(self):
        """Copia las métricas de negocio para devolverlas.

        :return: ``by_model`` (copiado modelo por modelo), ``cached_calls``,
            ``stopped``, ``tools`` y ``status``
        :rtype: dict
        """
        return {
            "by_model": {
                model: dict(entry) for model, entry in self.by_model.items()
            },
            "cached_calls": self.cached_calls,
            "stopped": self.stopped,
            "tools": dict(self.tools),
            "status": dict(self.status),
        }


class Metrics:
    """Contadores de peticiones, errores, latencias, tokens y negocio.

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
        self._business = BusinessCounts()

    def record_request(self, status, latency_ms):
        """Registra una petición atendida y su clase de código.

        :param status: Código HTTP de la respuesta
        :type status: int
        :param latency_ms: Latencia de la petición en milisegundos
        :type latency_ms: float
        """
        with self._lock:
            self._requests += 1
            if status >= SERVER_ERROR_STATUS:
                self._server_errors += 1
            self._business.status[status_class(status)] += 1
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

    def record_answer(self, model, cost_usd, cached_calls, tools, stopped):
        """Suma una respuesta ``200`` de ``POST /ask`` a las métricas de negocio.

        En una sola sección crítica suma la respuesta y su costo a su modelo,
        el costo al total, las llamadas de la caché, el corte por el tope y
        cada herramienta ejecutada (una repetida suma dos veces).

        :param model: Nombre del modelo que dio la respuesta
        :type model: str
        :param cost_usd: Costo de la respuesta en USD, sin redondear
        :type cost_usd: float
        :param cached_calls: Llamadas que respondió la caché del gateway
        :type cached_calls: int
        :param tools: Nombres de las herramientas ejecutadas, en orden
        :type tools: list[str]
        :param stopped: Si la respuesta la cortó el tope de pasos
        :type stopped: bool
        """
        with self._lock:
            business = self._business
            entry = business.by_model.setdefault(
                model, {"requests": 0, "cost_usd": 0.0}
            )
            entry["requests"] += 1
            entry["cost_usd"] += cost_usd
            self._cost_usd += cost_usd
            business.cached_calls += cached_calls
            if stopped:
                business.stopped += 1
            for name in tools:
                business.tools[name] = business.tools.get(name, 0) + 1

    def snapshot(self, slo_p95_ms):
        """Devuelve las métricas actuales con el estado de la meta de latencia.

        Copia todo dentro del candado: lo que se devuelve no cambia con las
        peticiones que siguen, ni cambiarlo altera la siguiente lectura.

        :param slo_p95_ms: Meta de latencia p95 en milisegundos
        :type slo_p95_ms: int
        :return: ``pid``, ``requests``, ``error_rate``, ``latency_ms``,
            ``tokens``, ``slo``, ``cost_usd`` acumulado, ``by_model``,
            ``cached_calls``, ``stopped``, ``tools`` y ``status``
        :rtype: dict
        """
        with self._lock:
            latencies = sorted(self._latencies)
            requests = self._requests
            server_errors = self._server_errors
            tokens = dict(self._tokens)
            cost_usd = self._cost_usd
            business = self._business.as_dict()
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
            **business,
        }
