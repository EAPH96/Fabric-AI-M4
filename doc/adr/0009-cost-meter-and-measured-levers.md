# ADR 0009: Costo por respuesta con un medidor y palancas que se miden

Estado: aceptada

## Contexto

Cada respuesta debe decir cuánto costó, y cada palanca (enrutamiento, ventana de historial, tope de salida,
caché) solo se usa si baja el costo sin bajar la calidad. El agente ya funciona y no queremos que conozca
precios.

## Decisión

- `pricing.py` carga `PriceTable` de `PRICES_PATH` al arrancar y exige precio para `MODEL_SMALL` y
  `MODEL_LARGE`; si falta, `ConfigError`.
- Por petición, `CostMeter` envuelve el modelo elegido: delega `complete`, cuenta `cached_calls` y suma
  `(input * precio_in + output * precio_out) / 1e6` solo de llamadas no cacheadas. Sin redondeo.
- La ventana recorta solo el historial del cliente (`recent_history`), nunca los mensajes de herramienta.
- `Metrics` acumula `cost_usd`; `agent_run` registra `model`, `route`, `cached_calls` y `cost_usd`.
- Toda palanca se valida con `verification evaluate` (línea base contra configuración por omisión).

## Consecuencias

- `Agent` no cambia de firma; el costo es otra envoltura de `complete`, como las trazas.
- Los tokens reportados incluyen las llamadas cacheadas; el costo no.
- El costo es una estimación con la tabla de precios, no la factura; los precios se actualizan en el archivo.
