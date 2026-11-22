# ADR 0013: Peticiones simultáneas con el pool de hilos de FastAPI y candados en lo compartido

Estado: aceptada (precisa los ADR 0001, 0005 y 0011; no reemplaza ninguno)

## Contexto

La especificación 05 pide dejar escrito por qué la API atiende peticiones simultáneas y cuáles son sus límites, sin
cambiar el código. El contrato manda 20 `POST /ask` a la vez y espera 20 respuestas `200` con 20 `request_id`
distintos, y que `/metrics` las cuente todas.

## Decisión

- **Sin estado entre peticiones (ADR 0001).** Cada `POST /ask` crea su `Agent`, su `CostMeter` y su
  `RequestObserver`; el historial llega en el cuerpo y `request.state` es de cada petición.
- **Pool de hilos.** `ask`, `read_metrics` y la dependencia `require_client` son funciones `def` síncronas: FastAPI
  (Starlette y AnyIO) las corre en un pool de hilos, 40 por omisión. El middleware `observe_request` es `async` y
  corre en el bucle de eventos.
- **Lo único compartido que se escribe** son `Metrics` (ADR 0005), `JsonLogger` (ADR 0004) y `RateLimiter`
  (ADR 0011), cada uno con su `threading.Lock`. Lo demás es de solo lectura: configuración, directorio, tabla de
  precios, `ApiKeyAuth`, tracer y modelos (`FakeModel` no guarda nada; `httpx.Client` de `GatewayModel` y el
  cliente de LangSmith son seguros entre hilos).
- Un solo proceso uvicorn por copia (Dockerfile, sin `--workers`) y una sola instancia en el plan Free de Render.

## Alternativas descartadas

- Rutas `async def`: el agente, el directorio y `httpx.Client` son bloqueantes; bloquearían el bucle de eventos y
  las peticiones se atenderían de una en una.
- Varios workers de uvicorn: más capacidad, pero métricas y límite partidos por proceso sin un almacén compartido.
- Un almacén compartido (Redis u otro) para métricas y límite: fuera del alcance del reto.

## Consecuencias

- **Límite conocido:** métricas y límite viven en la memoria de cada proceso; con varias copias cada una lleva su
  cuenta (el límite real se multiplica y `/metrics` solo muestra su `pid`). Un despliegue los pone en cero.
- Con más de 40 peticiones síncronas a la vez, las demás esperan turno; una llamada lenta al gateway ocupa un hilo
  hasta su timeout (30 s).
- Las peticiones simultáneas de un cliente cuentan igual en su límite por minuto.
- Cualquier objeto compartido nuevo que se escriba debe llevar su candado; si no, este ADR deja de ser cierto.
