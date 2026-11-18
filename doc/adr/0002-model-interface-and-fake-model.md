# ADR 0002: El modelo detrás de una interfaz, con un modelo simulado

Estado: aceptada; ampliada por ADR 0007 y 0008 (sesión 3: modelos por nombre y modelo real `gateway`)

## Contexto

Queremos cambiar de proveedor de modelo sin tocar el agente, y probar todo sin red, sin costo y de
forma determinista. En la sesión 1 solo existía el modelo simulado (`MODEL_PROVIDER=fake`).

## Decisión

- `llm.py` define el protocolo `ChatModel` con un único método
  `complete(messages) -> Completion(text, input_tokens, output_tokens)`.
- `text` es siempre un objeto JSON: `{"tool": ..., "args": {...}}` o `{"answer": ...}`.
- `FakeModel` aplica las 4 reglas de la especificación, en ese orden, sobre el último mensaje.
  Recibe por constructor la lista de departamentos (no lee archivos) y cuenta tokens por palabras.
- `build_model(settings, directory)` elige la implementación; cualquier proveedor distinto de
  `fake` es un error de configuración. Desde la sesión 3 lo reemplaza `build_models` (ADR 0007), que
  acepta `fake` y `gateway`, y `Completion` gana `cached`.

## Consecuencias

- Agregar un modelo real es escribir una clase nueva y una rama en la fábrica de modelos (así se hizo
  con `GatewayModel`, ADR 0008).
- Las pruebas pueden inyectar modelos a medida (por ejemplo, uno que siempre pide herramienta).
- El conteo de tokens del modelo simulado es aproximado; con precio por nombre sirve para comparar
  configuraciones, no para estimar la factura real.
