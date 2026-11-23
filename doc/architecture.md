# Arquitectura del HR Assistant

Asistente de Recursos Humanos que responde preguntas sobre empleados desde una página web.
API FastAPI sin estado de negocio, un solo agente con bucle con tope y un modelo detrás de una
interfaz. Desde la sesión 2, cada petición se puede rastrear (id, log JSON, auditoría, trazas) y
medir (`/metrics`). Desde la sesión 3, cada respuesta dice qué modelo usó, por qué y cuánto costó.
Desde la sesión 4, solo entra quien tiene clave, cada cliente tiene un límite por minuto, la
configuración de producción se revisa al arrancar y el producto se publica en Render solo si el
pipeline de CI pasa. Desde la especificación 05, queda escrito por qué atiende peticiones
simultáneas y la página enlaza con el segundo producto, el Asistente de políticas de RH. Desde la
especificación 06, ese segundo producto vive en `politicas/` del mismo repositorio y se publica como
otro servicio del mismo Blueprint; el código del HR no cambia (ver `politicas/doc/architecture.md`).
Desde la especificación 07, `/metrics` también dice cómo se usa el producto y cuánto cuesta cada
modelo: respuestas y costo por modelo, llamadas de caché, respuestas cortadas, herramientas y clases
de código HTTP (ADR 0015 y 0016), igual en los dos productos.

## Componentes

```mermaid
flowchart LR
    U[Personal de RH] --> P["Página web<br/>app/static/index.html<br/>clave en sessionStorage"]
    PG["Página armada al arrancar<br/>app/page.py<br/>enlace companion-link"] --> P
    C["Configuración<br/>app/config.py<br/>Settings, PageSettings,<br/>SecuritySettings"] --> PG
    P -. "enlace, otra pestaña" .-> POL[("Asistente de políticas de RH<br/>COMPANION_URL")]
    P -- "POST /ask con X-API-Key" --> MW["Middleware<br/>app/observability.py<br/>request_id, latencia, errores"]
    MW --> M["API<br/>app/main.py<br/>/, /health, /docs abiertos<br/>/ask, /metrics con clave"]
    C --> CO["Compliance<br/>app/compliance.py<br/>al arrancar"]
    CO --> M
    M -- "dependencia de cliente" --> AU["ApiKeyAuth<br/>app/security.py<br/>401"]
    AU -- "cliente" --> RL["RateLimiter<br/>app/ratelimit.py<br/>429 + Retry-After"]
    CLK["Clock<br/>app/clock.py"] --> RL
    CLK --> MW
    M -- "Route(model, reason)" --> R["Enrutador<br/>app/router.py"]
    M -- "un Agent, un RequestObserver con cliente<br/>y un CostMeter por petición" --> A["Agente<br/>app/agent.py"]
    A -- "complete(messages)" --> CM["CostMeter<br/>app/pricing.py"]
    CM --> L["Modelos<br/>app/llm.py"]
    L -- "fake" --> F["FakeModel x2"]
    L -- "gateway" --> G["GatewayModel<br/>app/gateway.py"]
    G --> AIG[(Cloudflare AI Gateway)]
    A -- "herramientas" --> D["Directorio<br/>app/directory.py"]
    D --> J[("data/employees.json")]
    MW -- "request (con client)" --> LOG["JsonLogger<br/>app/logs.py"]
    M -- "agent_run (con client)" --> LOG
    A -- "audit (con client)" --> LOG
    LOG --> OUT[("stdout")]
    MW -- "record_request: requests,<br/>latencia, status" --> MET["Metrics<br/>app/metrics.py<br/>un candado"]
    M -- "record_answer: by_model, cached_calls,<br/>stopped, tools, costo" --> MET
    A -. "trazas con request_id y client" .-> TR["Tracer<br/>app/tracing.py"]
    TR -. "opcional, entradas y salidas ocultas" .-> LS[(LangSmith)]
```

## Una petición a `/ask`

```mermaid
sequenceDiagram
    participant WEB as Página
    participant MW as Middleware
    participant DEP as Dependencia de cliente
    participant API as main.py
    participant AG as Agent y CostMeter
    participant LOG as JsonLogger
    participant MET as Metrics
    WEB->>MW: POST /ask con X-API-Key
    MW->>MW: resuelve request_id, inicia reloj
    MW->>DEP: petición
    alt sin clave o clave inválida
        DEP-->>MW: 401 invalid or missing API key
    else clave válida
        DEP->>DEP: request.state.client = cliente
        alt pasó el límite del minuto
            DEP-->>MW: 429 rate limit exceeded con Retry-After
        else dentro del límite
            DEP->>API: cliente
            API->>API: valida cuerpo (422), enruta, recorta historial
            API->>AG: run(question, history) con observador del cliente
            AG->>LOG: audit (tool, args, client)
            AG-->>API: resultado y costo
            API->>LOG: agent_run (conteos, costo, client)
            API->>MET: tokens y record_answer (solo con 200)
            API-->>MW: 200 (o 502 si el gateway falla)
        end
    end
    MW->>MET: record_request (requests, latencia, status por clase)
    MW->>LOG: request (method, path, status, latency_ms, client)
    MW-->>WEB: respuesta con X-Request-ID
    WEB->>WEB: 401 Clave inválida, 429 espera N segundos
```

## Métricas de negocio

Los cinco campos de la especificación 07 viven en `Metrics`, bajo el mismo candado que `requests`,
latencia, tokens y costo (ADR 0015). Cada uno se suma en un solo punto (ADR 0016).

```mermaid
flowchart TB
    subgraph MID["Middleware, cada petición"]
        RR["record_request(status, latency_ms)"]
    end
    subgraph ASK["log_agent_run, cada 200 de POST /ask"]
        RA["record_answer(model, cost_usd,<br/>cached_calls, tools_used, stopped)"]
    end
    subgraph MET["Metrics, un threading.Lock"]
        REQ["requests, error_rate, latency_ms"]
        ST["status: 2xx, 4xx, 5xx<br/>(5xx si es 500 o más, 4xx de 400 a 499,<br/>2xx el resto; suma = requests)"]
        BM["by_model: requests y cost_usd<br/>por nombre de modelo"]
        CC["cached_calls, stopped"]
        TL["tools: veces por herramienta ejecutada"]
        CU["cost_usd total"]
    end
    RR --> REQ
    RR --> ST
    RA --> BM
    RA --> CC
    RA --> TL
    RA --> CU
    MET -- "snapshot: copia dentro del candado" --> GM["GET /metrics<br/>sin textos, claves ni datos personales"]
```

## La página y el enlace al otro producto

```mermaid
sequenceDiagram
    participant ENV as Entorno
    participant CFG as load_settings
    participant APP as create_app
    participant PAGE as page.py
    participant WEB as Navegador
    ENV->>CFG: COMPANION_URL, COMPANION_NAME
    CFG->>APP: Settings con PageSettings
    APP->>PAGE: render_index(index.html, page)
    alt COMPANION_URL vacía
        PAGE-->>APP: HTML sin marcador ni enlace
    else con URL
        PAGE-->>APP: HTML con a data-testid=companion-link (escapado)
    end
    WEB->>APP: GET / (sin clave)
    APP-->>WEB: el mismo HTML armado al arrancar
    WEB-->>WEB: el enlace abre el otro producto en otra pestaña
```

## Peticiones simultáneas

Un solo proceso uvicorn por copia. Lo que se escribe entre peticiones lleva candado; lo demás es de
solo lectura o vive solo durante una petición (ADR 0013). Las métricas de negocio no agregan otro
objeto compartido: van dentro de `Metrics` (ADR 0015).

```mermaid
flowchart TB
    subgraph PROC["Proceso uvicorn (uno por copia; Render free: una copia)"]
        EL["Bucle de eventos<br/>middleware async"]
        subgraph POOL["Pool de hilos de AnyIO (40 por omisión)"]
            H1["Hilo: POST /ask<br/>require_client + Agent, CostMeter<br/>y RequestObserver nuevos"]
            H2["Hilo: POST /ask<br/>require_client + Agent, CostMeter<br/>y RequestObserver nuevos"]
            H3["Hilo: GET /metrics"]
        end
        EL --> POOL
        subgraph SHARED["Compartido y escrito, con threading.Lock"]
            MET["Metrics<br/>incluye las métricas de negocio"]
            LOG["JsonLogger"]
            RL["RateLimiter"]
        end
        subgraph RO["Compartido de solo lectura"]
            CFG["Settings"]
            DIR["Directorio"]
            PRI["PriceTable"]
            AUTH["ApiKeyAuth"]
            TRC["Tracer y cliente de LangSmith"]
            MOD["Modelos y httpx.Client"]
        end
        EL --> MET
        EL --> LOG
        H1 --> SHARED
        H2 --> SHARED
        H3 --> MET
        H1 --> RO
        H2 --> RO
    end
```

Límite conocido: métricas y límite de peticiones viven en la memoria de cada proceso; con varias
copias, cada una lleva su propia cuenta. Más de 40 peticiones a la vez esperan turno.

## Del código a producción

Desde la especificación 06, `render.yaml` y `ci.yml` son de los dos servicios. El bloque del HR y sus
cuatro etapas no cambian; se agregan el servicio y las etapas de Políticas (ADR 0001 de Políticas).

```mermaid
flowchart LR
    F["Fábrica<br/>verification unit, contract,<br/>qa, e2e, evaluate (hr) y (politicas)"] --> AP{"Aprobación<br/>de una persona<br/>output/approved.txt"}
    AP -- "scripts/publish.py" --> GH[(GitHub, repositorio privado)]
    GH --> CI["ci.yml, cadena del HR<br/>style -> unit -> e2e -> docker"]
    GH --> CIP["ci.yml, cadena de Políticas<br/>style-politicas -> unit-politicas<br/>-> e2e-politicas -> docker-politicas"]
    CI -- "checksPass: las 8 etapas" --> RD["Render Blueprint<br/>render.yaml, runtime docker"]
    CIP -- "checksPass: las 8 etapas" --> RD
    SEC["Secretos en Render > Environment<br/>API_KEYS, CF_ACCOUNT_ID, CF_API_TOKEN<br/>(COMPANION_URL a mano)"] --> RD
    RD --> IMG["Fabric-AI-M4<br/>Dockerfile en la raíz<br/>python:3.12-slim, usuario no root"]
    RD --> IMGP["Fabric-AI-M4-politicas<br/>politicas/Dockerfile<br/>contexto politicas/"]
    IMG -- "arranque: compliance" --> LIVE["Cada servicio Live<br/>healthCheckPath /health"]
    IMGP -- "arranque: compliance" --> LIVE
    LIVE --> SM["verification production url-hr url-politicas<br/>SMOKE_API_KEY y SMOKE_API_KEY_POLITICAS"]
    SM -- "falla" --> TRI["triage<br/>security, deploy o persona"]
```

## Principios

- Sin estado de negocio: el historial vive en el navegador (ADR 0001).
- El agente solo conoce `complete(messages)` (ADR 0002) y un observador opcional (ADR 0006).
- Bucle con tope y herramientas de solo lectura (ADR 0003).
- Un `request_id` por petición y log JSON sin texto de preguntas ni respuestas (ADR 0004).
- Métricas en memoria de cada proceso, identificadas por `pid`, con costo acumulado (ADR 0005).
- Métricas de negocio en la misma `Metrics` y el mismo candado; nunca influyen en una respuesta y no
  llevan textos, claves ni datos personales (ADR 0015). `status` se suma junto con `requests`; lo demás,
  una vez por cada `200` de `/ask` con los datos del evento `agent_run` (ADR 0016).
- Trazas en LangSmith opcionales, con entradas y salidas ocultas por omisión (ADR 0006).
- Enrutamiento por regla, modelo real por AI Gateway y costo medido (ADR 0007, 0008 y 0009).
- Una clave por cliente en una dependencia de ruta; la clave nunca se escribe, solo el nombre del
  cliente (ADR 0010).
- Límite por cliente en memoria con reloj inyectado; con varias copias se multiplica (ADR 0011).
- Compliance al arrancar con `ENVIRONMENT=production`; publicación solo con aprobación humana y CI en
  verde (ADR 0012). Detalle en `doc/compliance-checklist.md`.
- Peticiones simultáneas en el pool de hilos de FastAPI; solo métricas, log y límite se comparten y
  escriben, con candado (ADR 0013).
- El enlace al otro producto se arma en el servidor al arrancar, escapado y en otra pestaña; sin
  `COMPANION_URL` no aparece (ADR 0014).
- Políticas no importa nada de `app/`: copia sus módulos y se construye con su propia carpeta; un
  fallo de sus etapas de CI también frena la publicación del HR (ADR 0001 y 0002 de Políticas).
- Inyección de dependencias en `create_app(settings, model, directory, observability, models)`; la
  hora llega por un `Clock` inyectado.

## Variables de la sesión 4

| Variable | Por omisión | Dónde actúa |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `compliance.py`; solo `development` o `production` |
| `API_KEYS` | vacía | `security.py`; secreto, `sync: false` en Render |
| `RATE_LIMIT_PER_MINUTE` | `30` | `ratelimit.py` |

## Variables de la especificación 05

| Variable | Por omisión | Dónde actúa |
| --- | --- | --- |
| `COMPANION_URL` | vacía | `page.py`; vacía: sin enlace. En Render se escribe a mano en Environment |
| `COMPANION_NAME` | `Asistente de políticas de RH` | `page.py`; texto del enlace |

La especificación 07 no agrega variables.

## Dónde mirar

- Log: la salida estándar del proceso (en Render, la pestaña Logs); se filtra por `request_id` o por
  `client`.
- Métricas: `GET /metrics` con una clave; el `pid` dice de qué copia vienen. Uso y costo por modelo en
  `by_model`, herramientas en `tools`, respuestas cortadas en `stopped`, caché en `cached_calls` y
  clases de código en `status`.
- Documentación de la API: Swagger en `/docs`, abierto sin clave, con «Authorize» para `X-API-Key`.
- Pipeline: la pestaña Actions del repositorio, una etapa por trabajo; las de Políticas terminan en
  `-politicas`.
- Producción: `uv run python -m verification production <url-hr> <url-politicas>` con `SMOKE_API_KEY`
  y `SMOKE_API_KEY_POLITICAS` en el entorno (solo la URL del HR si Políticas aún no está publicada).
