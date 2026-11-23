# ADR 0016: Dónde se cuenta cada métrica de negocio

Estado: aceptada (precisa los ADR 0004 y 0009; no reemplaza ninguno). Vale igual para el Asistente de políticas
de RH.

## Contexto

La especificación 07 pide que la suma de `status` sea igual a `requests`, que `by_model` cuente las respuestas
`200` de `POST /ask` con su `cost_usd`, que `cached_calls` sume lo que ya cuenta el medidor de costo, que `stopped`
cuente las respuestas cortadas por `AGENT_MAX_STEPS` y que `tools` cuente las veces que se ejecutó cada
herramienta. Hay que decidir en qué punto del código se suma cada una.

## Decisión

- **`status` en `record_request`**, el mismo método y la misma sección crítica que suman `requests`; lo llama el
  middleware con el código de cada respuesta, incluidas 401, 422, 429, 502 y la 500 que él arma. Clase por rango:
  `5xx` si es 500 o más (como `error_rate`), `4xx` de 400 a 499 y `2xx` en cualquier otro caso. Así la suma es
  `requests` siempre, también con el 307 que FastAPI responde a `/metrics/`.
- **`by_model`, `cached_calls`, `stopped` y `tools` en un método `record_answer`**, que `log_agent_run` llama una
  vez por cada `200` de `/ask` con los mismos datos del evento `agent_run`: `model` de la respuesta,
  `cost_usd` y `cached_calls` del `CostMeter`, `tools_used` y `stopped` del `AgentResult`. El mismo método suma el
  costo total, que antes sumaba `add_cost`; así el total y el costo por modelo cambian juntos.
- **`stopped` es `AgentResult.stopped`**: ya marca las respuestas que terminaron sin respuesta del modelo y
  muestran el mensaje del tope.

## Alternativas descartadas

- Una llave `3xx`: la especificación fija tres llaves; dejar fuera los 3xx rompería la suma.
- Contar herramientas en `RequestObserver.tool_called`: contaría también las de una corrida que termina en `502`,
  pero `tools` dejaría de cuadrar con los `tools_used` de las respuestas y el observador tendría que escribir
  métricas.
- Un indicador nuevo en `AgentResult` que separe «tope agotado» de «salida que no cumple el protocolo»: cambia el
  agente de los dos productos por un caso que solo da el modelo real y que la persona ve igual.

## Consecuencias

- Una corrida que termina en `502` no suma herramientas, caché ni costo, igual que hoy no suma tokens ni costo; sí
  suma 1 a `status.5xx`.
- `stopped` incluye las salidas del modelo real que no cumplen el protocolo; el evento `agent_run` ya las marcaba
  igual.
- Una redirección cuenta como `2xx` (no es error del cliente ni del servidor).
