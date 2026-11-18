# Arquitectura del HR Assistant

Asistente de Recursos Humanos que responde preguntas sobre empleados desde una página web.
API FastAPI sin estado de negocio, un solo agente con bucle con tope y un modelo detrás de una
interfaz. Desde la sesión 2, cada petición se puede rastrear (id, log JSON, auditoría, trazas) y
medir (`/metrics`). Desde la sesión 3, cada respuesta dice qué modelo usó, por qué y cuánto costó.
Desde la sesión 4, solo entra quien tiene clave, cada cliente tiene un límite por minuto, la
configuración de producción se revisa al arrancar y el producto se publica en Render solo si el
pipeline de CI pasa.

## Componentes

```mermaid
flowchart LR
    U[Personal de RH] --> P["Página web<br/>app/static/index.html<br/>clave en sessionStorage"]
    P -- "POST /ask con X-API-Key" --> MW["Middleware<br/>app/observability.py<br/>request_id, latencia, errores"]
    MW --> M["API<br/>app/main.py<br/>/, /health, /docs abiertos<br/>/ask, /metrics con clave"]
    C["Configuración<br/>app/config.py<br/>Settings + SecuritySettings"] --> CO["Compliance<br/>app/compliance.py<br/>al arrancar"]
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
    MW --> MET["Metrics<br/>app/metrics.py"]
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
            API-->>MW: 200 (o 502 si el gateway falla)
        end
    end
    MW->>LOG: request (method, path, status, latency_ms, client)
    MW-->>WEB: respuesta con X-Request-ID
    WEB->>WEB: 401 Clave inválida, 429 espera N segundos
```

## Del código a producción

```mermaid
flowchart LR
    F["Fábrica<br/>verification unit, contract,<br/>qa, e2e, evaluate"] --> AP{"Aprobación<br/>de una persona<br/>output/approved.txt"}
    AP -- "scripts/publish.py" --> GH[(GitHub, repositorio privado)]
    GH --> CI["GitHub Actions ci.yml<br/>style -> unit -> e2e -> docker"]
    CI -- "checksPass" --> RD["Render Blueprint<br/>render.yaml, runtime docker"]
    SEC["Secretos en Render > Environment<br/>API_KEYS, CF_ACCOUNT_ID, CF_API_TOKEN"] --> RD
    RD --> IMG["Imagen python:3.12-slim<br/>usuario no root<br/>uvicorn en PORT"]
    IMG -- "arranque: compliance" --> LIVE["Servicio Live<br/>healthCheckPath /health"]
    LIVE --> SM["verification production URL<br/>SMOKE_API_KEY"]
    SM -- "falla" --> TRI["triage<br/>security, deploy o persona"]
```

## Principios

- Sin estado de negocio: el historial vive en el navegador (ADR 0001).
- El agente solo conoce `complete(messages)` (ADR 0002) y un observador opcional (ADR 0006).
- Bucle con tope y herramientas de solo lectura (ADR 0003).
- Un `request_id` por petición y log JSON sin texto de preguntas ni respuestas (ADR 0004).
- Métricas en memoria de cada proceso, identificadas por `pid`, con costo acumulado (ADR 0005).
- Trazas en LangSmith opcionales, con entradas y salidas ocultas por omisión (ADR 0006).
- Enrutamiento por regla, modelo real por AI Gateway y costo medido (ADR 0007, 0008 y 0009).
- Una clave por cliente en una dependencia de ruta; la clave nunca se escribe, solo el nombre del
  cliente (ADR 0010).
- Límite por cliente en memoria con reloj inyectado; con varias copias se multiplica (ADR 0011).
- Compliance al arrancar con `ENVIRONMENT=production`; publicación solo con aprobación humana y CI en
  verde (ADR 0012). Detalle en `doc/compliance-checklist.md`.
- Inyección de dependencias en `create_app(settings, model, directory, observability, models)`; la
  hora llega por un `Clock` inyectado.

## Variables de la sesión 4

| Variable | Por omisión | Dónde actúa |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `compliance.py`; solo `development` o `production` |
| `API_KEYS` | vacía | `security.py`; secreto, `sync: false` en Render |
| `RATE_LIMIT_PER_MINUTE` | `30` | `ratelimit.py` |

## Dónde mirar

- Log: la salida estándar del proceso (en Render, la pestaña Logs); se filtra por `request_id` o por
  `client`.
- Métricas: `GET /metrics` con una clave; el `pid` dice de qué copia vienen.
- Pipeline: la pestaña Actions del repositorio, una etapa por trabajo.
- Producción: `uv run python -m verification production <url>` con `SMOKE_API_KEY` en el entorno.
