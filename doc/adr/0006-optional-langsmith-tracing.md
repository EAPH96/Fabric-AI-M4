# ADR 0006: Trazas opcionales en LangSmith detrás de un observador

Estado: aceptada

## Contexto

Queremos ver cada corrida del agente, cada llamada al modelo y cada herramienta en LangSmith, pero
el producto debe funcionar igual sin clave y sin red. `langsmith` está instalado en el entorno, pero
importarlo y decorar con `traceable` sin control puede leer el entorno e intentar mandar trazas por su
cuenta. Además, mandar preguntas a un tercero expone datos personales.

## Decisión

- `build_tracer(settings)` devuelve `NullTracer` salvo que `LANGSMITH_TRACING=true` y exista
  `LANGSMITH_API_KEY`. Solo entonces se importa `langsmith` (con `importlib`) y se crea su cliente,
  que se pasa de forma explícita a cada traza.
- El cliente se crea con `hide_inputs`/`hide_outputs` según `HIDE_INPUTS`/`HIDE_OUTPUTS`
  (`true` por omisión). Cada traza lleva `request_id` en sus metadatos.
- El agente no conoce LangSmith: recibe un `RequestObserver` que envuelve `model.complete` y las
  herramientas y avisa cada herramienta ejecutada (para el evento `audit`).
- La clave se lee del entorno, se guarda con `repr=False` y nunca se registra.

## Consecuencias

- Sin clave no hay importación ni conexión; las pruebas usan un módulo `langsmith` falso inyectado.
- Cambiar de proveedor de trazas es escribir otro tracer, sin tocar el agente.
- Con las entradas y salidas ocultas, LangSmith muestra tiempos y estructura, no el contenido.
