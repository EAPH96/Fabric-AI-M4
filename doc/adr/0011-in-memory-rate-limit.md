# ADR 0011: Límite de peticiones en memoria, por cliente y con reloj inyectado

Estado: aceptada (precisa los ADR 0001 y 0005)

## Contexto

Cada cliente puede hacer como máximo `RATE_LIMIT_PER_MINUTE` peticiones por minuto; la siguiente recibe `429` con
`Retry-After`. El ADR 0001 dice que la API no guarda nada entre peticiones y no hay un almacén compartido (Redis u
otro) en esta sesión.

## Decisión

- `RateLimiter` en `app/ratelimit.py` guarda, por cliente, las marcas de `clock.monotonic()` de los últimos 60 s
  (ventana deslizante) y se protege con un candado.
- Corre en la misma dependencia que la clave, después de identificar al cliente. Un 401 no cuenta; un 429 no se
  agrega a la ventana.
- `Retry-After` es `ceil(marca_más_antigua + 60 - ahora)`, mínimo 1.
- El reloj es el de `Observability`, el mismo `FakeClock` en las pruebas.

## Consecuencias

- Es estado operativo, como las métricas: no cambia ninguna respuesta de negocio. La memoria está acotada por el
  número de clientes de `API_KEYS` por el límite.
- Con N copias o N workers, el límite real es N veces el configurado, y un despliegue lo reinicia. Render free usa
  una instancia y el Dockerfile un solo proceso; un límite global pediría un almacén compartido.
