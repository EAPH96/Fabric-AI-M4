"""Trazas opcionales en LangSmith (ADR 0006 del HR).

``build_tracer`` devuelve un ``NullTracer`` salvo que ``LANGSMITH_TRACING`` sea
``true`` y exista ``LANGSMITH_API_KEY``. Solo en ese caso se importa
``langsmith``, de forma perezosa, para no leer el entorno ni abrir conexiones al
arrancar. La clave se pasa al cliente y nunca se registra. Las trazas van al
proyecto de ``LANGSMITH_PROJECT`` para no mezclarse con las del HR.
"""

import importlib


class NullTracer:
    """Tracer apagado: devuelve las funciones sin cambios."""

    # pylint: disable-next=unused-argument
    def wrap(self, function, run_type, request_id, client=None):
        """Devuelve la misma función, sin trazar.

        :param function: Función a envolver
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza (``chain``, ``llm`` o ``tool``)
        :type run_type: str
        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta, o ``None``
        :type client: str or None
        :return: La misma función
        :rtype: collections.abc.Callable
        """
        return function


class LangSmithTracer:
    """Tracer que envuelve funciones con ``langsmith.traceable``.

    :param traceable: Decorador ``traceable`` del módulo ``langsmith``
    :type traceable: collections.abc.Callable
    :param client: Cliente de LangSmith que reciben todas las trazas
    :type client: object
    :param project_name: Proyecto de LangSmith donde quedan las trazas
    :type project_name: str
    """

    def __init__(self, traceable, client, project_name):
        self._traceable = traceable
        self._client = client
        self._project_name = project_name

    def wrap(self, function, run_type, request_id, client=None):
        """Envuelve una función como traza con ``request_id`` y cliente.

        Los dos van en los metadatos de la traza. Solo viaja el nombre del
        cliente, nunca su clave.

        :param function: Función a envolver
        :type function: collections.abc.Callable
        :param run_type: Tipo de traza (``chain``, ``llm`` o ``tool``)
        :type run_type: str
        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta, o ``None``
        :type client: str or None
        :return: Función trazada con la misma firma
        :rtype: collections.abc.Callable
        """
        metadata = {"request_id": request_id}
        if client is not None:
            metadata["client"] = client
        decorator = self._traceable(
            run_type=run_type,
            name=getattr(function, "__name__", run_type),
            metadata=metadata,
            client=self._client,
            project_name=self._project_name,
        )
        return decorator(function)


def build_tracer(settings, importer=importlib.import_module):
    """Construye el tracer indicado por la configuración.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param importer: Función que importa un módulo por nombre (se inyecta en
        las pruebas)
    :type importer: collections.abc.Callable
    :return: ``LangSmithTracer`` si la traza está encendida y hay clave; si no,
        ``NullTracer``
    :rtype: NullTracer or LangSmithTracer
    """
    options = settings.observability
    if not (options.langsmith_tracing and options.langsmith_api_key):
        return NullTracer()
    langsmith = importer("langsmith")
    client = langsmith.Client(
        api_key=options.langsmith_api_key,
        hide_inputs=options.hide_inputs,
        hide_outputs=options.hide_outputs,
    )
    return LangSmithTracer(langsmith.traceable, client, options.langsmith_project)
