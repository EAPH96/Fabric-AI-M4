# ADR 0017: Costos en producción: caché solo en Políticas y sin enrutamiento al modelo pequeño

Estado: aceptada (precisa los ADR 0007, 0008 y 0009; no reemplaza ninguno). Vale para los dos productos: el HR
Assistant y el Asistente de políticas de RH, que hereda los ADR del HR.

## Contexto

Las cuatro palancas de costo existen desde la especificación 03 y se encienden con variables de entorno; hasta
ahora `render.yaml` no fijaba ninguna, así que producción usaba los valores por omisión (`ROUTING=true`,
`CACHE_TTL_SECONDS=0`). La medición con el modelo real (`verification/evaluate.py --real`) mostró:

- Con el enrutamiento, las preguntas cortas van a `llama-3.1-8b-instruct-fast`, que casi nunca pidió una
  herramienta y respondió con datos inventados: en Políticas, 0 de 9 casos y 0 % de calidad; en el HR, 7 de 8
  casos con historial de relleno, pero 1 de 8 en tráfico real sin historial.
- Sin el enrutamiento, con la ventana de historial y el tope de salida, la calidad no bajó respecto a la línea
  base de la misma corrida (HR 100 % contra 88 %; Políticas 89 % contra 89 %) y el costo bajó 13 % en el HR
  (0.003006 a 0.002618 USD) y 10 % en Políticas (0.004411 a 0.003950 USD).

Políticas responde reglas generales, sin datos de personas, con preguntas que se repiten y políticas que cambian
pocas veces al año. El HR responde con datos de empleados.

## Decisión

- **Sin enrutamiento en producción.** Los dos servicios de `render.yaml` llevan `ROUTING="false"`: toda pregunta va
  a `MODEL_LARGE` con `route: routing_disabled`. `HISTORY_WINDOW` (6) y `MODEL_MAX_TOKENS` (300) siguen con su
  valor por omisión.
- **Caché solo en Políticas.** `Fabric-AI-M4-politicas` lleva `CACHE_TTL_SECONDS="3600"`; `Fabric-AI-M4` no lleva
  la variable y queda en 0 (sin cabecera `cf-aig-cache-ttl`, ADR 0008).
- **Solo cambia `render.yaml`.** El código del enrutador (ADR 0007), los valores por omisión de `config.py` y los
  `.env.example` no cambian: el desarrollo, las pruebas y `verification evaluate` siguen midiendo las palancas.

## Alternativas descartadas

- Mantener el enrutamiento: con el modelo real ahorraba cerca de 87 % en el HR y 93 % en Políticas, pero con
  respuestas sin herramientas y datos inventados.
- Enrutar solo en el HR: 7 de 8 casos con historial de relleno, pero 1 de 8 en tráfico real sin historial.
- Quitar el código del enrutamiento o cambiar `ROUTING` por omisión a `false`: rompe las pruebas y contratos de la
  especificación 03 y la medición de `evaluate`, y cierra la opción de volver a enrutar.
- Probar otro `MODEL_SMALL`: no está medido; queda para una medición futura.
- Caché en el HR: guardaría datos personales en Cloudflare y podría mostrar un dato que ya cambió.

## Consecuencias

- Se pierde el ahorro del enrutamiento; se ganan respuestas que usan las herramientas, con costo 13 % y 10 % menor
  que la línea base.
- En producción `by_model` de `/metrics` solo muestra `MODEL_LARGE`; la latencia es la del modelo grande en todas
  las preguntas y se vigila con `latency_ms` y `slo`.
- En Políticas una pregunta repetida dentro de la hora sale de la caché: cuenta en `cached_calls` y no cuesta. Una
  respuesta puede tener hasta una hora de antigüedad, y la caché es común a todos los clientes de Políticas: si la
  persona escribe un dato suyo en la pregunta, ese texto queda en la caché de Cloudflare hasta una hora.
- `CACHE_TTL_SECONDS` no se agrega a mano en Render > Environment del HR: la regla vive en `render.yaml` y la
  comprueba `verification/contract/test_contract_08.py`.
- Volver a enrutar exige una medición con `evaluate --real` que pase con el modelo pequeño y un ADR nuevo que
  reemplace a este.
