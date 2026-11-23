# ADR 0015: Métricas de negocio en la misma memoria y el mismo candado que las métricas del proceso

Estado: aceptada (precisa los ADR 0005 y 0013; no reemplaza ninguno). Vale igual para el Asistente de políticas
de RH, que hereda los ADR del HR.

## Contexto

La especificación 07 pide que `GET /metrics` diga cómo se usa cada producto y cuánto cuesta cada parte:
`by_model`, `cached_calls`, `stopped`, `tools` y `status`, guardados en la memoria del proceso y con el mismo
candado que las métricas actuales, sin texto de preguntas ni respuestas, sin claves ni datos personales, e igual en
los dos productos. El ADR 0005 llamó a `Metrics` «estado operativo, no de negocio»: quería decir que nunca influye
en una respuesta de `/ask`, y eso sigue siendo cierto.

## Decisión

- Los cinco campos viven en la clase `Metrics` que ya existe (`app/metrics.py`), bajo su único `threading.Lock`;
  no hay una clase ni un candado nuevos. `snapshot` conserva sus siete campos y agrega los cinco, copiados dentro
  del candado (`by_model` se copia por modelo) para que una lectura nunca vea una suma a medias.
- Las llaves son nombres que no vienen de la persona: `by_model` usa el nombre del modelo que eligió el enrutador
  (`MODEL_SMALL` o `MODEL_LARGE`) y `tools` solo las herramientas que el agente ejecutó, que son las de su registro.
  Nunca se guardan argumentos, textos, claves ni el nombre del cliente.
- `cost_usd` de cada modelo se suma sin redondear, como el total (ADR 0009).
- El cambio es el mismo en los dos productos: `metrics.py` sigue siendo copia del HR en Políticas (ADR 0002 de
  Políticas) y `log_agent_run` de `main.py` cambia igual en los dos.

## Alternativas descartadas

- Una clase `BusinessMetrics` con su propio candado: dos candados dejan ver `requests` y `status` desfasados en una
  lectura concurrente, y la especificación pide el mismo candado.
- Calcularlas desde el log (eventos `request` y `agent_run`) con un recolector externo: es la vista global que el
  ADR 0005 dejó fuera del reto.
- `prometheus_client` con etiquetas: una dependencia nueva y otro formato de `/metrics` que rompería los contratos
  anteriores.

## Consecuencias

- Siguen las limitaciones del ADR 0005: cada copia cuenta lo suyo, identificada por `pid`, y reiniciar pone todo en
  cero.
- La memoria sigue acotada: a lo más dos modelos y las herramientas del registro (dos por producto); un nombre de
  herramienta inventado por el modelo no se ejecuta y no crea llave.
- Lo único compartido que se escribe sigue siendo `Metrics`, `JsonLogger` y `RateLimiter`, cada uno con su candado
  (ADR 0013).
