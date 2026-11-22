# Asistente de políticas de RH

Asistente que responde preguntas del personal sobre las políticas de la empresa (vacaciones,
aguinaldo, jornada, permisos y otras) desde una página web, y cita siempre el `id` de la política
que usó. Las diez políticas de `data/policies.json` (`POL-001` a `POL-010`) son **ficticias, de
ejemplo**, basadas en la Ley Federal del Trabajo: no son asesoría legal, y la página lo dice.

Es el HR Assistant de `product/` con otros datos, otras dos herramientas y otro modelo simulado
(especificación 06). Es una API FastAPI sin estado de negocio, con un solo agente que consulta el
catálogo de solo lectura a través de dos herramientas:

- `search_policies(topic)`: `id` y `title` de las políticas cuyo `topic` o alguna de sus
  `keywords` coincide con el tema, sin distinguir mayúsculas ni acentos.
- `get_policy(policy_id)`: `id`, `title` y `text` de una política.

El modelo vive detrás de una interfaz: puede ser simulado y determinista (`fake`, sin red) o real
(`gateway`: Cloudflare Workers AI a través de AI Gateway). El simulado pide `get_policy` si la
pregunta trae un id como `POL-003`, `search_policies` si menciona un tema o una palabra clave de
alguna política, y si no, responde «Pregúntame por una política (POL-001) o un tema, como
vacaciones.».

Vive en `product/politicas/`, en el mismo repositorio que el HR Assistant, y se publica como un
servicio aparte. No importa nada de `product/app/`: los módulos que son iguales se copiaron, así
que un arreglo en uno de ellos se hace también en el otro producto (ADR 0002).

Todo lo demás es igual al HR Assistant:

- **Costo medido** en cada respuesta, con cuatro palancas: enrutamiento al modelo barato
  (`MODEL_SMALL`) o al capaz (`MODEL_LARGE`), ventana de historial (`HISTORY_WINDOW`), tope de
  salida (`MODEL_MAX_TOKENS`) y caché de AI Gateway (`CACHE_TTL_SECONDS`).
- **Observabilidad**: un `request_id` por petición (encabezado `X-Request-ID`, cuerpo de
  `POST /ask` y página), log JSON en la salida estándar con `service: politicas-rh` (sin el texto
  de preguntas ni respuestas), `GET /metrics` y trazas opcionales en LangSmith, en el proyecto
  `LANGSMITH_PROJECT`.
- **Acceso**: una clave por cliente (`API_KEYS`, encabezado `X-API-Key`), límite por cliente
  (`RATE_LIMIT_PER_MINUTE`, `429` con `Retry-After`) y compliance como código con
  `ENVIRONMENT=production`. Las reglas son las de `../doc/compliance-checklist.md` del HR
  Assistant.
- **Enlace al otro producto**: con `COMPANION_URL`, el encabezado de la página enlaza al HR
  Assistant (texto de `COMPANION_NAME`), en otra pestaña. Sin `COMPANION_URL`, no hay enlace. Se
  arma al arrancar: para cambiarlo hay que reiniciar el proceso.

La arquitectura y las decisiones propias están en `doc/architecture.md` y `doc/adr/`; las
heredadas, en los ADR 0001 a 0014 del HR Assistant (`../doc/adr/`).

## Cómo correrlo

Desde la carpeta `product/politicas/`, con las dependencias de `requirements.txt` instaladas:

```bash
pip install -r requirements.txt
uvicorn app.main:app --no-access-log --port 8001
```

Con `uv`, desde la misma carpeta: `uv run uvicorn app.main:app --no-access-log --port 8001`.

La página queda en `http://127.0.0.1:8001/`. Se usa otro puerto para poder correrlo junto al HR
Assistant (que usa el 8000); con `COMPANION_URL=http://127.0.0.1:8000/` en el `.env` de
Políticas, y `COMPANION_URL=http://127.0.0.1:8001/` en el del HR, cada página enlaza a la otra.
`--no-access-log` evita que las líneas de acceso de `uvicorn` se mezclen con el log JSON.

Para preguntar hace falta una clave. Ponla en `API_KEYS` de tu `.env` (por ejemplo, un cliente
`local` con una clave que inventes, de 16 caracteres o más) y escríbela en el campo «Clave de
acceso» de la página. La página la guarda en `sessionStorage` con su propia llave (no comparte la
del HR) y la manda en `X-API-Key`. Con una clave equivocada la página dice «Clave inválida»; si
se pasa el límite, «Demasiadas preguntas; espera N segundos».

Desde la terminal:

```bash
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $POLITICAS_API_KEY" \
  -d '{"question": "¿Cuántos días de vacaciones me tocan?"}'
```

(`POLITICAS_API_KEY` es una variable de tu terminal con tu clave: así no queda en el historial.)
La respuesta cita `POL-001`.

### En un contenedor

El `Dockerfile` usa `python:3.12-slim`, corre con un usuario que no es root y escucha en
`${PORT:-8000}`. Se construye con `product/politicas/` como contexto:

```bash
docker build -t politicas-rh .
docker run --rm -p 8001:8000 --env-file .env politicas-rh
```

`.dockerignore` deja fuera `.env`: las variables se pasan al correr, nunca dentro de la imagen.

### Publicar en Render

Políticas es el servicio `Fabric-AI-M4-politicas` del mismo Blueprint (`product/render.yaml`)
que el HR Assistant:

1. El pipeline de `.github/workflows/ci.yml` corre, en cada push y pull request,
   `style-politicas`, `unit-politicas`, `e2e-politicas` y `docker-politicas` con
   `working-directory: politicas`, en paralelo con las cuatro etapas del HR.
2. El servicio usa `dockerfilePath: ./politicas/Dockerfile`, `dockerContext: ./politicas`,
   `ENVIRONMENT=production`, `MODEL_PROVIDER=gateway`, `HIDE_INPUTS=true`, `HIDE_OUTPUTS=true`,
   `SERVICE_NAME=politicas-rh` y `autoDeployTrigger: checksPass`: Render lo publica solo si pasan
   **todas** las etapas del commit, las del HR y las de Políticas.
3. Al sincronizar el Blueprint (Render > Blueprints > el del repositorio > Sync), Render crea el
   servicio nuevo sin tocar `Fabric-AI-M4`. Los secretos `API_KEYS`, `CF_ACCOUNT_ID`,
   `CF_API_TOKEN` y `COMPANION_URL` van con `sync: false`: se escriben en Render, nunca en el
   repositorio. Si Render no los pide al sincronizar, se escriben en Render >
   `Fabric-AI-M4-politicas` > Environment. `API_KEYS` lleva claves propias de Políticas,
   distintas de las del HR. `LANGSMITH_API_KEY` se agrega ahí solo si se encienden las trazas.
4. Enlaces entre los dos productos: en Políticas, `COMPANION_URL` es la URL del HR
   (`https://<servicio-hr>.onrender.com`). En el HR, `COMPANION_URL` no está en su `render.yaml`:
   se escribe a mano en Render > `Fabric-AI-M4` > Environment con la URL de Políticas. Cada
   servicio se reinicia al guardar y desde entonces muestra el enlace.
5. Si la configuración incumple una regla de compliance (por ejemplo, sin `API_KEYS`), el
   despliegue falla al arrancar y Render deja viva la versión anterior.
6. Prueba de humo, desde `product/politicas/`:
   `SMOKE_API_KEY=<clave> python scripts/smoke.py https://<servicio-politicas>.onrender.com`
   pregunta por vacaciones. La fábrica prueba los dos servicios con
   `uv run python -m verification production <url-hr> <url-politicas>`, con `SMOKE_API_KEY` (HR)
   y `SMOKE_API_KEY_POLITICAS` (Políticas) en el entorno.

### Con el modelo real

1. Copia `.env.example` a `.env` (en `product/politicas/`) y llena `CF_ACCOUNT_ID`,
   `CF_GATEWAY_ID` y `CF_API_TOKEN` con los datos de tu cuenta de Cloudflare. `.env` no se sube
   al repositorio.
2. Pon `MODEL_PROVIDER=gateway` en `.env`.
3. Arranca con las variables del archivo:
   `uv run --env-file .env uvicorn app.main:app --no-access-log --port 8001`.

Con `gateway`, si falta alguna de las tres `CF_*` (o un id tiene caracteres distintos de letras,
dígitos, `_` y `-`) el proceso no arranca. Tampoco arranca si `MODEL_SMALL` o `MODEL_LARGE` no
tienen precio en `PRICES_PATH`. Si el gateway falla, no responde a tiempo o responde algo
incompleto, `POST /ask` devuelve `502` con `{"detail": "model unavailable", "request_id": ...}`,
sin reintentar.

## Rutas

| Ruta | Clave | Para qué |
| --- | --- | --- |
| `GET /` | No | Página web para el personal |
| `GET /health` | No | `{"status": "ok", "pid": ...}` |
| `GET /docs` | No | Documentación interactiva de la API, con el título «Asistente de políticas de RH» |
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
  no la factura: actualiza `data/model_prices.json` cuando cambien los precios (es una copia del
  archivo del HR; los dos se actualizan juntos).

El modelo simulado también tiene precio: hay dos simulados que se llaman como `MODEL_SMALL` y
`MODEL_LARGE`, responden igual y cuestan lo que dice el precio de su nombre. Así las palancas se
miden sin red y sin gastar cuota.

Si algo falla de forma inesperada, la respuesta es `500` con
`{"detail": "internal error", "request_id": ...}`; ese id permite encontrar la petición en el log.

## Variables de entorno

Todas son opcionales, salvo las `CF_*` con `MODEL_PROVIDER=gateway`. Un valor inválido impide
arrancar, con un mensaje que nombra la variable. `.env.example` las lista todas, sin secretos.
Son las del HR Assistant salvo cuatro: `POLICIES_PATH` (en lugar de `EMPLOYEES_PATH`, que aquí no
se lee), `SERVICE_NAME`, `COMPANION_NAME` y `LANGSMITH_PROJECT`.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Proveedor del modelo: `fake` (simulado) o `gateway` (real) |
| `AGENT_MAX_STEPS` | `3` | Tope de llamadas al modelo por pregunta (entero mayor que 0) |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta (entero mayor que 0) |
| `POLICIES_PATH` | `data/policies.json` | Archivo de políticas (relativo a `product/politicas/` o absoluto) |
| `SERVICE_NAME` | `politicas-rh` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos (entero mayor que 0) |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas en LangSmith (`true` o `false`) |
| `LANGSMITH_API_KEY` | (sin valor) | Clave de LangSmith; sin ella no hay trazas ni conexión |
| `LANGSMITH_PROJECT` | `politicas-rh` | Proyecto de LangSmith de las trazas; separa las de Políticas de las del HR |
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
| `PRICES_PATH` | `data/model_prices.json` | Precios en USD por millón de tokens (relativo a `product/politicas/` o absoluto) |
| `ENVIRONMENT` | `development` | `development` o `production`; con `production` se aplican las reglas de compliance |
| `API_KEYS` | (sin valor) | Clientes y claves (secreto), con la forma `cliente:clave,cliente2:clave2` |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto (entero mayor que 0) |
| `COMPANION_URL` | (sin valor) | URL del HR Assistant en el encabezado; vacía: sin enlace |
| `COMPANION_NAME` | `HR Assistant` | Texto del enlace al otro producto |

`API_KEYS`:

- Cada entrada es `cliente:clave` y se parte en el primer `:` (la clave puede tener `:`). Se
  ignoran los espacios alrededor de cada entrada.
- El cliente tiene de 1 a 64 caracteres de `A-Z a-z 0-9 _ -`; la clave no puede estar vacía ni
  tener espacios. No se pueden repetir clientes ni claves.
- Si una entrada está mal, el proceso no arranca y el error dice el número de la entrada y su
  largo, nunca su valor.
- Sin `API_KEYS`, en `development` todo `POST /ask` responde `401`; en `production` el
  producto no arranca. En producción cada clave debe tener 16 caracteres o más.

Las claves `LANGSMITH_API_KEY`, `CF_API_TOKEN` y las de `API_KEYS` se leen solo del entorno: no
las escribas en el código ni en archivos versionados. Nunca aparecen en el log, en las trazas,
en los errores ni en la representación de la configuración.

La caché del gateway está apagada por omisión: al encenderla, Cloudflare guarda respuestas y
puede servir el texto viejo de una política mientras dure `CACHE_TTL_SECONDS`.

## Dónde mirar

- Log: la salida estándar del proceso (en Render, la del servicio `Fabric-AI-M4-politicas`).
  Para seguir una petición, filtra por su `request_id` (el que muestra la página o devuelve el
  encabezado `X-Request-ID`).
- Métricas: `GET /metrics` de cada copia del servicio, con una clave de Políticas; el `pid` dice
  de cuál. `cost_usd` es el costo acumulado de las respuestas de esa copia.
- Costo por respuesta: el evento `agent_run` del log trae `model`, `route`, `cached_calls` y
  `cost_usd` (sin el texto de la pregunta ni de la respuesta).
- Trazas: el proyecto `LANGSMITH_PROJECT` de LangSmith, solo si se encendieron con
  `LANGSMITH_TRACING=true` y clave. Cada traza lleva el `request_id` y el cliente en sus
  metadatos.
- Quién pregunta: los eventos `request` (con clave válida), `agent_run` y `audit` traen el campo
  `client` con el nombre del cliente, nunca su clave.

## Pruebas

Desde la raíz del repositorio; cada paso corre para los dos productos e imprime
`[OK] <paso> (politicas)`:

```bash
uv run python -m verification unit      # pruebas del producto, cobertura de 80 % o más
uv run python -m verification contract  # contrato de las specs 01 a 05 adaptado a Políticas
uv run python -m verification qa        # pylint, 88 columnas, sin emojis, documentos
uv run python -m verification e2e       # pruebas de Playwright de la página
uv run python -m verification evaluate  # 9 casos: misma calidad y menos costo que la línea base
```

Ninguna prueba usa la red: el gateway se prueba con un `httpx.MockTransport` inyectado, y el
contrato, las pruebas de punta a punta y la evaluación usan el modelo simulado.
