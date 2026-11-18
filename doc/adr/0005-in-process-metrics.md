# ADR 0005: Métricas en memoria de cada proceso

Estado: aceptada (precisa el ADR 0001)

## Contexto

La especificación pide `GET /metrics` con peticiones, tasa de error, latencia p50/p95, tokens y si se
cumple la meta `SLO_P95_MS`. El ADR 0001 dice que la API no guarda nada entre peticiones, y no hay
un almacén externo de métricas.

## Decisión

- `Metrics` vive en memoria del proceso y se protege con un candado (los endpoints corren en hilos).
- Es estado operativo, no de negocio: nunca influye en una respuesta de `/ask`, así que la API sigue
  siendo intercambiable entre copias.
- La latencia se guarda en una ventana acotada de las últimas `LATENCY_WINDOW` peticiones;
  p50 y p95 se calculan por rango más cercano. `error_rate` cuenta solo respuestas 5xx.
- `/metrics` incluye el `pid` para saber de qué copia vienen los números.

## Consecuencias

- Cada copia reporta solo lo suyo y reiniciar el proceso pone todo en cero.
- Una vista global requiere sumar copias desde afuera (por ejemplo, un recolector); queda fuera de
  esta sesión.
- La memoria usada es constante sin importar el tráfico.
