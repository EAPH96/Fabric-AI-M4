# Arquitectura del Asistente de políticas de RH

Asistente que responde preguntas del personal sobre las políticas de la empresa (vacaciones, aguinaldo, jornada,
permisos y otras) y cita siempre la política que usó. Es el HR Assistant de `product/` con otros datos, otras dos
herramientas y otro modelo simulado (especificación 06). Hereda sus decisiones: los ADR 0001 a 0014 del HR
Assistant (`product/doc/adr/`) valen igual aquí. Vive en `product/politicas/` y se publica como un servicio aparte
(ADR 0001), sin importar nada de `product/app/` (ADR 0002).

## Componentes

```mermaid
flowchart LR
    U[Personal] --> P["Página web<br/>app/static/index.html<br/>aviso legal, clave en sessionStorage"]
    PG["Página armada al arrancar<br/>app/page.py"] --> P
    C["Configuración<br/>app/config.py<br/>POLICIES_PATH, SERVICE_NAME,<br/>COMPANION_NAME, LANGSMITH_PROJECT"] --> PG
    P -. "enlace, otra pestaña" .-> HR[("HR Assistant<br/>COMPANION_URL")]
    P -- "POST /ask con X-API-Key" --> MW["Middleware<br/>app/observability.py"]
    MW --> M["API<br/>app/main.py<br/>título: Asistente de políticas de RH"]
    C --> CO["Compliance<br/>app/compliance.py"]
    CO --> M
    M --> AU["ApiKeyAuth y RateLimiter<br/>app/security.py, app/ratelimit.py<br/>401, 429"]
    M -- "Route(model, reason)" --> R["Enrutador<br/>app/router.py"]
    M -- "un Agent y un CostMeter por petición" --> A["Agente<br/>app/agent.py"]
    A --> CM["CostMeter<br/>app/pricing.py"]
    CM --> L["Modelos<br/>app/llm.py"]
    L -- "fake" --> F["FakeModel<br/>reglas de políticas"]
    L -- "gateway" --> G["GatewayModel<br/>app/gateway.py"]
    G --> AIG[(Cloudflare AI Gateway)]
    A -- "search_policies, get_policy" --> PC["PolicyCatalog<br/>app/policies.py<br/>normalize sin acentos"]
    PC --> J[("data/policies.json<br/>POL-001 a POL-010")]
    A -. "trazas, proyecto politicas-rh" .-> TR["Tracer<br/>app/tracing.py"]
    TR -. "opcional" .-> LS[(LangSmith)]
    MW --> LOG["JsonLogger<br/>service: politicas-rh"]
    MW --> MET["Metrics<br/>/metrics"]
```

## Una pregunta a `/ask`

```mermaid
sequenceDiagram
    participant WEB as Página
    participant API as Middleware y main.py
    participant AG as Agent
    participant MOD as Modelo
    participant CAT as PolicyCatalog
    WEB->>API: POST /ask con X-API-Key
    API->>API: request_id, clave (401), límite (429), cuerpo (422), ruta
    API->>AG: run(question, history)
    AG->>MOD: complete(messages)
    alt la pregunta trae POL-xxx
        MOD-->>AG: tool get_policy(policy_id)
        AG->>CAT: get_policy
        CAT-->>AG: id, title, text o «not found»
    else menciona un tema
        MOD-->>AG: tool search_policies(topic)
        AG->>CAT: search
        CAT-->>AG: id y title de cada coincidencia
    else nada de eso
        MOD-->>AG: answer con la ayuda
    end
    AG->>MOD: Resultado de la herramienta: ...
    MOD-->>AG: answer que cita los id
    AG-->>API: resultado, tokens y costo
    API-->>WEB: 200 con answer, request_id, model, cost_usd
```

## Del código a producción

```mermaid
flowchart LR
    F["Fábrica<br/>verification ... (hr) y (politicas)"] --> AP{"Aprobación<br/>de una persona"}
    AP --> GH[(GitHub)]
    GH --> CIH["ci.yml, cadena del HR<br/>style -> unit -> e2e -> docker"]
    GH --> CIP["ci.yml, cadena de Políticas<br/>working-directory: politicas<br/>style -> unit -> e2e -> docker"]
    CIH -- "checksPass: todas las etapas" --> RD["Render Blueprint<br/>render.yaml"]
    CIP -- "checksPass: todas las etapas" --> RD
    RD --> SH["Fabric-AI-M4<br/>contexto: raíz"]
    RD --> SP["Fabric-AI-M4-politicas<br/>contexto: politicas/<br/>politicas/Dockerfile"]
    SEC["Secretos de Políticas<br/>API_KEYS, CF_ACCOUNT_ID,<br/>CF_API_TOKEN, COMPANION_URL"] --> SP
    SP -- "arranque: compliance" --> LV["Servicio Live<br/>healthCheckPath /health"]
    LV --> SM["verification production url-hr url-politicas<br/>SMOKE_API_KEY_POLITICAS"]
```

## Módulos copiados y adaptados (ADR 0002)

| Estado | Módulos de `app/` |
| --- | --- |
| Copiados del HR sin cambios de lógica | `clock`, `errors`, `logs`, `metrics`, `observability`, `protocol`, `router`, `pricing`, `security`, `ratelimit`, `compliance`, `page` |
| Adaptados | `agent` (herramientas), `llm` (modelo simulado), `gateway` (`SYSTEM_PROMPT`), `config` (variables), `tracing` (`LANGSMITH_PROJECT`), `main` (título y catálogo), `static/index.html` (textos y aviso) |
| Propio | `policies` (en lugar de `directory`) |

Un arreglo en un módulo copiado se hace también en el otro producto.

## Principios

- Todo lo del HR Assistant: sin estado, bucle con tope, herramientas de solo lectura, `request_id` y log JSON sin
  texto de preguntas, métricas por proceso, costo medido, claves por cliente, límite, compliance al arrancar,
  concurrencia con candados y enlace armado al arrancar (ADR 0001 a 0014 del HR).
- Servicio aparte en el mismo repositorio, con su propio contexto de Docker y sus propias etapas de CI (ADR 0001).
- Ningún import de `product/app/`: los módulos se copian (ADR 0002).
- Un tema coincide si un `topic` o una `keyword`, sin acentos ni mayúsculas, es igual a él o está dentro; la
  respuesta cita los `id` (ADR 0003).
- Políticas ficticias de ejemplo; la página lo dice y no son asesoría legal.

## Variables propias de Políticas

Las demás variables y sus valores por omisión son los del HR Assistant.

| Variable | Por omisión | Dónde actúa |
| --- | --- | --- |
| `POLICIES_PATH` | `data/policies.json` | `config.py` y `policies.py`; reemplaza a `EMPLOYEES_PATH` |
| `SERVICE_NAME` | `politicas-rh` | Campo `service` del log |
| `COMPANION_NAME` | `HR Assistant` | `page.py`; texto del enlace |
| `COMPANION_URL` | vacía | `page.py`; en Render, secreto con `sync: false` |
| `LANGSMITH_PROJECT` | `politicas-rh` | `tracing.py`; proyecto de las trazas |

## Dónde mirar

- Log: salida estándar del servicio `Fabric-AI-M4-politicas` en Render; se filtra por `request_id` o `client`.
- Métricas: `GET /metrics` con una clave de Políticas.
- Documentación de la API: Swagger en `/docs`, con el título «Asistente de políticas de RH».
- Pipeline: las etapas `*-politicas` en la pestaña Actions.
- Producción: `uv run python -m verification production <url-hr> <url-politicas>` con `SMOKE_API_KEY` y
  `SMOKE_API_KEY_POLITICAS` en el entorno. El `scripts/smoke.py` propio de Políticas lee la clave de
  `SMOKE_API_KEY`, como el del HR.
