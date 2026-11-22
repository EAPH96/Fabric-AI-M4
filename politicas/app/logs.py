"""Log estructurado: una línea JSON por evento.

Cada línea lleva ``ts`` (ISO 8601 en UTC), ``service``, ``event`` y
``request_id``, más los campos propios del evento. Se escribe con
``ensure_ascii=True`` para que ninguna consola rompa con acentos.
"""

import json
import threading


class JsonLogger:
    """Escribe eventos como líneas JSON en un flujo de texto.

    Es seguro entre hilos: cada línea se escribe completa y con ``flush``.

    :param stream: Destino del log (por ejemplo ``sys.stdout``)
    :type stream: typing.TextIO
    :param clock: Reloj que da la hora de cada evento
    :type clock: app.clock.Clock
    :param service: Nombre del servicio para el campo ``service``
    :type service: str
    """

    def __init__(self, stream, clock, service):
        self._stream = stream
        self._clock = clock
        self._service = service
        self._lock = threading.Lock()

    def event(self, name, request_id, **fields):
        """Escribe un evento en una sola línea JSON.

        :param name: Nombre del evento (``request``, ``agent_run``, ``audit``...)
        :type name: str
        :param request_id: Id de la petición a la que pertenece el evento
        :type request_id: str
        :param fields: Campos propios del evento; deben ser serializables a JSON
        :type fields: dict
        """
        record = {
            "ts": self._clock.now().isoformat(),
            "service": self._service,
            "event": name,
            "request_id": request_id,
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=True, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()
