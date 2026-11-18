# ADR 0008: Modelo real a través de AI Gateway con cliente HTTP inyectado

Estado: aceptada

## Contexto

Con `MODEL_PROVIDER=gateway` el producto llama a Workers AI a través de Cloudflare AI Gateway. Las pruebas
no deben usar red ni cuota, el token es secreto y un modelo real puede fallar o no seguir el protocolo JSON.

## Decisión

- `gateway.py` define `GatewayModel`, que cumple `complete(messages)` (ADR 0002). Recibe un `httpx.Client`
  inyectado; en producción lo crea `build_models`, en pruebas se usa `httpx.MockTransport`.
- Cuerpo exacto `{"model", "messages", "max_tokens", "temperature"}`, con un mensaje `system` fijo que explica
  el protocolo; `cf-aig-cache-ttl` solo si `CACHE_TTL_SECONDS > 0`; `cf-aig-cache-status: HIT` marca la
  llamada como cacheada.
- Cualquier falla (red, tiempo agotado, estado no 2xx, respuesta incompleta) lanza `ModelUnavailableError`;
  `/ask` responde `502 {"detail": "model unavailable", "request_id"}`. Sin reintentos.
- Las tres `CF_*` son obligatorias con `gateway`; el token se guarda con `repr=False` y nunca se registra.

## Consecuencias

- El agente no sabe si habla con el simulado o con el real.
- Un reintento automático no duplica el costo; la persona reintenta desde la página.
- La calidad con el modelo real depende del mensaje `system`; se limpia el texto de cercos de código.
