# ADR 0004: Un id por petición y log JSON sin datos personales

Estado: aceptada

## Contexto

Soporte debe poder responder "qué pasó con la petición X" con datos. Las preguntas tratan de
empleados: su texto y las respuestas son datos personales que no deben quedar en el log.
Las pruebas deben ser deterministas, así que la hora no puede leerse directo del sistema.

## Decisión

- Un middleware único (`app/observability.py`) resuelve el `request_id`: usa `X-Request-ID` del
  cliente si tiene 1 a 128 caracteres de `[A-Za-z0-9._:-]`; si no, genera un UUID. Lo devuelve en el
  encabezado de toda respuesta y en el cuerpo de `POST /ask`.
- El mismo middleware mide la latencia, escribe el evento `request` y captura cualquier excepción:
  escribe `error` con el tipo (nunca el mensaje) y responde 500 con `request_id`.
- `JsonLogger` escribe una línea JSON por evento en la salida estándar con `ts` (UTC), `service`,
  `event` y `request_id`. `agent_run` lleva solo conteos; `audit` lleva herramienta y argumentos.
- La hora sale de un `Clock` inyectado; `SystemClock` es el único que lee el reloj del sistema.

## Consecuencias

- Con un `request_id` se filtran todas las líneas de una petición en cualquier copia.
- Un id del cliente fuera de formato se reemplaza: el cliente debe leer el id del encabezado.
- El log no sirve para reconstruir la conversación; esa información no se guarda en ningún lado.
