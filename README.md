# HR Assistant

Asistente de Recursos Humanos que responde preguntas sobre empleados desde una página web.
Es una API FastAPI sin estado de negocio, con un solo agente que consulta un directorio de solo
lectura (`data/employees.json`) a través de dos herramientas (`get_employee` y
`search_by_department`). El modelo vive detrás de una interfaz: puede ser simulado y
determinista (`fake`, sin red) o real (`gateway`: Cloudflare Workers AI a través de AI Gateway).

Cada respuesta dice qué modelo la atendió y cuánto costó. Cuatro palancas bajan el costo sin
empeorar la respuesta:

1. **Enrutamiento:** una regla en código manda las preguntas simples al modelo barato
   (`MODEL_SMALL`) y las largas o que piden comparar, resumir, explicar, analizar, «por qué» o
   «todos» al modelo capaz (`MODEL_LARGE`).
2. **Ventana de historial:** al modelo solo llegan los últimos `HISTORY_WINDOW` mensajes.
3. **Tope de salida:** `MODEL_MAX_TOKENS` en cada llamada.
4. **Caché de AI Gateway:** con `CACHE_TTL_SECONDS` mayor que 0; una respuesta de la caché no
   cuesta.

Cada petición se puede rastrear y medir:

- Un `request_id` por petición: se respeta el encabezado `X-Request-ID` del cliente (1 a 128
  caracteres de `A-Z a-z 0-9 . _ : -`) o se genera un UUID. Toda respuesta lo devuelve en
  `X-Request-ID`; `POST /ask` también en el cuerpo, y la página lo muestra bajo cada respuesta.
- Log en JSON, una línea por evento, en la salida estándar: `request`, `agent_run`, `audit` y
  `error`. Nunca se registra el texto de preguntas ni respuestas, ni el mensaje de un error.
- `GET /metrics` con las métricas de este proceso y si se cumple la meta de latencia p95.
- Trazas opcionales en LangSmith, con entradas y salidas ocultas por omisión.

Y solo lo usa quien tiene clave:

- **Una clave por cliente** (`API_KEYS`). `POST /ask` y `GET /metrics` piden el encabezado
  `X-API-Key`; `/`, `/health` y `/docs` no. El nombre del cliente va en el log (`client`) y en
  las trazas; la clave nunca.
- **Límite por cliente**: más de `RATE_LIMIT_PER_MINUTE` peticiones en un minuto responden
  `429` con `Retry-After`.
- **Compliance como código**: con `ENVIRONMENT=production` el producto no arranca si usa el
  modelo simulado, si no hay claves o alguna tiene menos de 16 caracteres, o si las trazas
  están encendidas sin ocultar entradas y salidas. La lista completa, con dónde está cada regla
  en el código y cómo se comprueba, está en `doc/compliance-checklist.md`.

El encabezado de la página puede enlazar al otro producto, el Asistente de políticas de RH. Con
`COMPANION_URL`, la página muestra un enlace con el texto de `COMPANION_NAME` que se abre en otra
pestaña. Si `COMPANION_URL` está vacía, el enlace no aparece. El enlace se arma al arrancar, así
que para cambiarlo hay que reiniciar el proceso (ADR 0014).

La arquitectura y las decisiones están en `doc/architecture.md` y `doc/adr/`.

## Cómo correrlo

Desde la carpeta `product/`, con las dependencias de `requirements.txt` instaladas:

```bash
pip install -r requirements.txt
uvicorn app.main:app --no-access-log
```

Con `uv`, desde la misma carpeta: `uv run uvicorn app.main:app --no-access-log`.

La página queda en `http://127.0.0.1:8000/`. `--no-access-log` evita que las líneas de acceso de
`uvicorn` se mezclen con el log JSON.

Para preguntar hace falta una clave. Ponla en `API_KEYS` de tu `.env` (por ejemplo, un cliente
`local` con una clave que inventes, de 16 caracteres o más) y escríbela en el campo «Clave de
acceso» de la página. La página la guarda en `sessionStorage`: dura lo que dure la pestaña y se
manda en `X-API-Key`. Con una clave equivocada la página dice «Clave inválida»; si se pasa el
límite, «Demasiadas preguntas; espera N segundos».

Desde la terminal:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HR_API_KEY" \
  -d '{"question": "¿Quién es EMP-0004?"}'
```

(`HR_API_KEY` es una variable de tu terminal con tu clave: así no queda en el historial.)

### En un contenedor

El `Dockerfile` usa `python:3.12-slim`, corre con un usuario que no es root y escucha en
`${PORT:-8000}`:

```bash
docker build -t hr-assistant .
docker run --rm -p 8000:8000 --env-file .env hr-assistant
```

`.dockerignore` deja fuera `.env`: las variables se pasan al correr, nunca dentro de la imagen.

### Publicar en Render

1. El pipeline de `.github/workflows/ci.yml` corre `style`, `unit`, `e2e` y `docker` en cada
   push y pull request.
2. `render.yaml` es un Blueprint con `ENVIRONMENT=production`, `MODEL_PROVIDER=gateway` y
   `autoDeployTrigger: checksPass`: Render publica solo si el pipeline pasa.
3. Los secretos (`API_KEYS`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`) se escriben en Render al crear
   el Blueprint (`sync: false`), nunca en el repositorio. `LANGSMITH_API_KEY` se agrega en
   Render > Environment solo si se encienden las trazas.
4. `COMPANION_URL` no está en `render.yaml`: cuando exista la URL de Políticas, se escribe a
   mano en Render > Environment. Mientras no se escriba, la página no muestra el enlace.
5. Si la configuración incumple una regla de compliance, el despliegue falla al arrancar y
   Render deja viva la versión anterior.

### Con el modelo real

1. Copia `.env.example` a `.env` y llena `CF_ACCOUNT_ID`, `CF_GATEWAY_ID` y `CF_API_TOKEN` con
   los datos de tu cuenta de Cloudflare. `.env` no se sube al repositorio.
2. Pon `MODEL_PROVIDER=gateway` en `.env`.
3. Arranca con las variables del archivo: `uv run --env-file .env uvicorn app.main:app --no-access-log`.

Con `gateway`, si falta alguna de las tres `CF_*` (o un id tiene caracteres distintos de letras,
dígitos, `_` y `-`) el proceso no arranca. Tampoco arranca si `MODEL_SMALL` o `MODEL_LARGE` no
tienen precio en `PRICES_PATH`. Si el gateway falla, no responde a tiempo o responde algo
incompleto, `POST /ask` devuelve `502` con `{"detail": "model unavailable", "request_id": ...}`,
sin reintentar.

## Rutas

| Ruta | Clave | Para qué |
| --- | --- | --- |
| `GET /` | No | Página web para el personal de RH |
| `GET /health` | No | `{"status": "ok", "pid": ...}` |
| `GET /docs` | No | Documentación interactiva de la API |
| `POST /ask` | Sí | `{"question", "history"}` y devuelve `answer`, `steps`, `tools_used`, `input_tokens`, `output_tokens`, `request_id`, `model`, `route`, `cached_calls` y `cost_usd` |
| `GET /metrics` | Sí | `pid`, `requests`, `error_rate`, `latency_ms` (`p50`, `p95`), `tokens` (`input`, `output`), `slo` (`p95_ms_target`, `met`) y `cost_usd` acumulado |

Las rutas con clave piden `X-API-Key` y cuentan en el límite del cliente:

- Sin clave o con una que no es de ningún cliente: `401 {"detail": "invalid or missing API key"}`.
  Los `401` no cuentan en el límite.
- Más de `RATE_LIMIT_PER_MINUTE` peticiones del mismo cliente en los últimos 60 segundos:
  `429 {"detail": "rate limit exceeded"}` con `Retry-After` (segundos que faltan, al menos 1).
  El límite es por cliente y por proceso: con varias copias, cada una cuenta por su lado.

Campos de costo de `POST /ask`:

- `model`: el modelo que eligió el enrutador.
- `route`: por qué. `simple` (modelo barato), `long_question` (más de `ROUTER_MAX_CHARS`
  caracteres), `keyword:<palabra>` (por ejemplo `keyword:compara`) o `routing_disabled`
  (`ROUTING=false`).
- `cached_calls`: llamadas al modelo que respondió la caché del gateway.
- `cost_usd`: costo estimado en USD con los precios de `PRICES_PATH` (por millón de tokens), sin
  redondear. Las llamadas cacheadas no cuestan, pero sus tokens sí se cuentan. Es una estimación,
  no la factura: actualiza `data/model_prices.json` cuando cambien los precios.

El modelo simulado también tiene precio: hay dos simulados que se llaman como `MODEL_SMALL` y
`MODEL_LARGE`, responden igual y cuestan lo que dice el precio de su nombre. Así las palancas se
miden sin red y sin gastar cuota.

Si algo falla de forma inesperada, la respuesta es `500` con
`{"detail": "internal error", "request_id": ...}`; ese id permite encontrar la petición en el log.

## Variables de entorno

Todas son opcionales, salvo las `CF_*` con `MODEL_PROVIDER=gateway`. Un valor inválido impide
arrancar, con un mensaje que nombra la variable. `.env.example` las lista todas, sin secretos.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Proveedor del modelo: `fake` (simulado) o `gateway` (real) |
| `AGENT_MAX_STEPS` | `3` | Tope de llamadas al modelo por pregunta (entero mayor que 0) |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta (entero mayor que 0) |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados (relativo a `product/` o absoluto) |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos (entero mayor que 0) |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas en LangSmith (`true` o `false`) |
| `LANGSMITH_API_KEY` | (sin valor) | Clave de LangSmith; sin ella no hay trazas ni conexión |
| `HIDE_INPUTS` | `true` | No mandar a LangSmith las entradas (`true` o `false`) |
| `HIDE_OUTPUTS` | `true` | No mandar a LangSmith las salidas (`true` o `false`) |
| `CF_ACCOUNT_ID` | (sin valor) | Cuenta de Cloudflare; obligatoria con `gateway` |
| `CF_GATEWAY_ID` | `default` | Id del AI Gateway |
| `CF_API_TOKEN` | (sin valor) | Token de Cloudflare (secreto); obligatorio con `gateway` |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta (`true` o `false`; con `false` todo va al capaz) |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz (entero mayor que 0) |
| `HISTORY_WINDOW` | `6` | Mensajes del historial que se mandan al modelo (entero, 0 o más) |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida por llamada (entero mayor que 0) |
| `MODEL_TEMPERATURE` | `0` | Temperatura del modelo (número, 0 o más); con 0 las evaluaciones son repetibles |
| `CACHE_TTL_SECONDS` | `0` | Segundos de caché en AI Gateway (entero, 0 o más; 0 la apaga) |
| `PRICES_PATH` | `data/model_prices.json` | Precios en USD por millón de tokens (relativo a `product/` o absoluto) |
| `ENVIRONMENT` | `development` | `development` o `production`; con `production` se aplican las reglas de compliance |
| `API_KEYS` | (sin valor) | Clientes y claves (secreto), con la forma `cliente:clave,cliente2:clave2` |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto (entero mayor que 0) |
| `COMPANION_URL` | (sin valor) | URL del otro producto en el encabezado; vacía: sin enlace |
| `COMPANION_NAME` | `Asistente de políticas de RH` | Texto del enlace al otro producto |

`API_KEYS`:

- Cada entrada es `cliente:clave` y se parte en el primer `:` (la clave puede tener `:`). Se
  ignoran los espacios alrededor de cada entrada.
- El cliente tiene de 1 a 64 caracteres de `A-Z a-z 0-9 _ -`; la clave no puede estar vacía ni
  tener espacios. No se pueden repetir clientes ni claves.
- Si una entrada está mal, el proceso no arranca y el error dice el número de la entrada y su
  largo, nunca su valor (por ejemplo `API_KEYS entry 2 is malformed (length 27): has no ':'
  between client and key; expected client:key`).
- Sin `API_KEYS`, en `development` todo `POST /ask` responde `401`; en `production` el
  producto no arranca. En producción cada clave debe tener 16 caracteres o más.

Las claves `LANGSMITH_API_KEY`, `CF_API_TOKEN` y las de `API_KEYS` se leen solo del entorno: no
las escribas en el código ni en archivos versionados. Nunca aparecen en el log, en las trazas,
en los errores ni en la representación de la configuración.

La caché del gateway está apagada por omisión: al encenderla, Cloudflare guarda respuestas con
datos de empleados y puede servir datos viejos mientras dure `CACHE_TTL_SECONDS`.

## Dónde mirar

- Log: la salida estándar del proceso. Para seguir una petición, filtra por su `request_id`
  (el que muestra la página o devuelve el encabezado `X-Request-ID`).
- Métricas: `GET /metrics` de cada copia del servicio; el `pid` dice de cuál. `cost_usd` es el
  costo acumulado de las respuestas de esa copia.
- Costo por respuesta: el evento `agent_run` del log trae `model`, `route`, `cached_calls` y
  `cost_usd` (sin el texto de la pregunta ni de la respuesta).
- Trazas: el proyecto de LangSmith, solo si se encendieron con `LANGSMITH_TRACING=true` y clave.
  Cada traza lleva el `request_id` y el cliente en sus metadatos.
- Quién pregunta: los eventos `request` (con clave válida), `agent_run` y `audit` traen el campo
  `client` con el nombre del cliente, nunca su clave.

## Pruebas

Desde la raíz del repositorio:

```bash
uv run python -m verification unit      # pruebas del producto, cobertura de 80 % o más
uv run python -m verification contract  # contrato de las specs 01 a 05, por HTTP
uv run python -m verification qa        # pylint, 88 columnas, sin emojis, documentos
uv run python -m verification e2e       # pruebas de Playwright de la página
uv run python -m verification evaluate  # misma calidad y menos costo que la línea base
```

Ninguna prueba usa la red: el gateway se prueba con un `httpx.MockTransport` inyectado, y el
contrato, las pruebas de punta a punta y la evaluación usan el modelo simulado.
