# ADR 0010: Una clave por cliente, revisada en una dependencia de ruta

Estado: aceptada

## Contexto

El producto se publica en Internet. Hay que saber quién pregunta y cerrar `/ask` y `/metrics`, pero `/`, `/health`
y `/docs` deben seguir abiertos (la página, el chequeo de Render y la documentación). La clave es un secreto: no
puede aparecer en el log, en las trazas, en un error ni en la salida de arranque.

## Decisión

- `API_KEYS` (`cliente:clave,cliente2:clave2`) se valida al arrancar en `app/security.py`; un error nombra la
  entrada y su largo, nunca su valor, y se lanza sin excepción encadenada.
- La revisión es una **dependencia de FastAPI** en `/ask` y `/metrics`, no un middleware: así `/docs` y
  `/openapi.json` no piden clave.
- `ApiKeyAuth.identify` compara bytes UTF-8 con `hmac.compare_digest` contra todas las claves, sin cortar al primer
  acierto. Sin clave o con una inválida: `401 {"detail": "invalid or missing API key"}`.
- Lo único que viaja después es el **nombre del cliente** (`request.state.client`): va en `request`, `agent_run`,
  `audit` y en los metadatos de la traza.

## Consecuencias

- Las pruebas deben mandar `X-API-Key`; `conftest.py` lo hace por omisión.
- Rotar una clave exige cambiar `API_KEYS` en Render y redesplegar.
- Los 401 no tienen límite de peticiones; la defensa contra fuerza bruta es el largo mínimo de 16 en producción
  (ADR 0012) y la comparación en tiempo constante.
