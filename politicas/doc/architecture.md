# Arquitectura del Asistente de políticas de RH

Asistente que responde preguntas del personal sobre las políticas de la empresa (vacaciones, aguinaldo, jornada,
permisos y otras) y cita siempre la política que usó. Es el HR Assistant de `product/` con otros datos, otras dos
herramientas y otro modelo simulado (especificación 06). Hereda sus decisiones: los ADR 0001 a 0018 del HR
Assistant (`product/doc/adr/`) valen igual aquí. Vive en `product/politicas/` y se publica como un servicio aparte
(ADR 0001), sin importar nada de `product/app/` (ADR 0002). Desde la especificación 07, `/metrics` agrega las
métricas de negocio con el mismo comportamiento que el HR (ADR 0015 y 0016 del HR). Desde la especificación 08, en
producción todas las preguntas van al modelo grande y las respuestas del gateway se guardan en caché una hora
(ADR 0017 del HR); el código no cambia. Desde la especificación 09, los datos personales se enmascaran igual que en
el HR, el log audita los rechazos y la PII, y una respuesta que cita una política que ninguna herramienta devolvió
en esa petición se reemplaza por un texto fijo (ADR 0018 del HR).

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
    M --> AU["ApiKeyAuth y RateLimiter<br/>app/security.py, app/ratelimit.py<br/>401 + auth_failed, 429 + rate_limited"]
    M -- "pregunta, historial y respuesta" --> PII["mask_pii<br/>app/pii.py<br/>copia del HR"]
    M -- "respuesta y policy_ids" --> CIT["check_citations<br/>app/citations.py"]
    M -- "Route(model, reason)" --> R["Enrutador<br/>app/router.py"]
    M -- "un Agent y un CostMeter por petición" --> A["Agente<br/>app/agent.py<br/>AgentResult.policy_ids"]
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
    M -- "agent_run, pii_detected,<br/>auth_failed, rate_limited" --> LOG
    MW -- "record_request: requests,<br/>latencia, status" --> MET["Metrics<br/>/metrics, un candado"]
    M -- "record_answer: by_model, cached_calls,<br/>stopped, tools, costo" --> MET
```

## Una pregunta a `/ask`

```mermaid
sequenceDiagram
    participant WEB as Página
    participant API as Middleware y main.py
    participant PII as pii.py
    participant AG as Agent
    participant MOD as Modelo
    participant CAT as PolicyCatalog
    participant CIT as citations.py
    participant MET as Metrics
    WEB->>API: POST /ask con X-API-Key
    API->>API: request_id, clave (401 + auth_failed), límite (429 + rate_limited), cuerpo (422)
    API->>PII: mask_pii(pregunta) y cada mensaje del historial
    PII-->>API: texto con marcas, pii_detected si hubo
    API->>API: ruta con el texto enmascarado
    API->>AG: run(pregunta, historial) enmascarados, traza chain
    AG->>MOD: complete(messages)
    alt la pregunta trae POL-xxx
        MOD-->>AG: tool get_policy(policy_id)
        AG->>CAT: get_policy
        CAT-->>AG: id, title, text (anota el id) o «not found» (no anota)
    else menciona un tema
        MOD-->>AG: tool search_policies(topic)
        AG->>CAT: search
        CAT-->>AG: id y title de cada coincidencia (anota los id)
    else nada de eso
        MOD-->>AG: answer con la ayuda
    end
    AG->>MOD: Resultado de la herramienta: ...
    MOD-->>AG: answer que cita los id
    AG-->>API: resultado con policy_ids, tokens y costo
    API->>CIT: check_citations(answer, policy_ids)
    alt cita un POL-xxx que no está en policy_ids
        CIT-->>API: «No encontré esa información en las políticas...»
    else todas las citas salieron de una herramienta, o no hay citas
        CIT-->>API: la misma respuesta
    end
    API->>PII: mask_pii(respuesta), pii_detected si hubo
    API->>MET: record_answer (solo con 200)
    API->>MET: record_request (toda petición, status por clase)
    API-->>WEB: 200 con answer, request_id, model, cost_usd, pii_masked
```

## Citas validadas

Desde la especificación 09 (ADR 0018 del HR). Solo cuenta como devuelto un id que el catálogo entregó en esta
petición: un «Policy POL-999 not found» no cuenta, ni una política que vino en el historial. La regla no tiene
excepciones, así que la ayuda del modelo simulado, que trae `(POL-001)` como ejemplo sin consultar una
herramienta, también se reemplaza por el texto fijo, que da la misma guía. La validación corre una vez y antes de
enmascarar: el texto de reemplazo trae `POL-001` y no se vuelve a revisar.

```mermaid
flowchart LR
    T1["search_policies<br/>id de cada resultado"] --> IDS["AgentResult.policy_ids"]
    T2["get_policy encontrada<br/>su id"] --> IDS
    T3["get_policy not found"] -. "no anota" .-> IDS
    ANS["answer del modelo"] --> CC{"cada POL-xxx citado<br/>está en policy_ids"}
    IDS --> CC
    CC -- "sí, o sin citas" --> SAME["respuesta sin cambios"]
    CC -- "no" --> NF["NOT_FOUND_ANSWER"]
    SAME --> MK["mask_pii"]
    NF --> MK
    MK --> RESP["AskResponse"]
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

## Configuración de producción

`render.yaml` fija para `Fabric-AI-M4-politicas` `ROUTING=false` y `CACHE_TTL_SECONDS=3600` (ADR 0017 del HR).
Con el enrutamiento, el modelo pequeño no pidió ninguna herramienta en 0 de 9 casos de la medición con el modelo
real; sin él, la calidad fue igual a la línea base y el costo bajó 10 %. La caché es segura aquí porque Políticas
responde reglas generales sin datos de personas, sus preguntas se repiten y una política cambia pocas veces al año.
El HR no lleva caché. Desde la especificación 09 la caché solo recibe texto enmascarado: si la persona escribe un
dato suyo, a Cloudflare llega la marca, no el valor.

```mermaid
sequenceDiagram
    participant API as main.py
    participant RT as Enrutador
    participant GW as GatewayModel
    participant AIG as AI Gateway
    participant MET as Metrics
    API->>RT: choose_route con ROUTING=false
    RT-->>API: MODEL_LARGE, routing_disabled
    API->>GW: complete(messages enmascarados)
    GW->>AIG: petición con cf-aig-cache-ttl: 3600
    alt la misma petición en la última hora
        AIG-->>GW: respuesta con cf-aig-cache-status: HIT
        GW-->>API: llamada cacheada, costo 0
    else petición nueva
        AIG-->>GW: respuesta del modelo grande
        GW-->>API: llamada con tokens y costo
    end
    API->>MET: record_answer: cached_calls y cost_usd
```

En desarrollo, en las pruebas y en `verification evaluate` siguen los valores por omisión (`ROUTING=true`,
`CACHE_TTL_SECONDS=0`). Una respuesta de la caché puede tener hasta una hora de antigüedad y la caché es común a
todos los clientes del servicio.

## Módulos copiados y adaptados (ADR 0002)

| Estado | Módulos de `app/` |
| --- | --- |
| Copiados del HR sin cambios de lógica | `clock`, `errors`, `logs`, `metrics`, `observability`, `protocol`, `router`, `pricing`, `security`, `ratelimit`, `compliance`, `page`, `pii` |
| Adaptados | `agent` (herramientas y `policy_ids`), `llm` (modelo simulado), `gateway` (`SYSTEM_PROMPT`), `config` (variables), `tracing` (`LANGSMITH_PROJECT`), `main` (título, catálogo y validación de citas), `static/index.html` (textos y aviso) |
| Propios | `policies` (en lugar de `directory`), `citations` |

Un arreglo en un módulo copiado se hace también en el otro producto. En la especificación 07, `metrics.py` cambia
igual en los dos productos y sigue siendo copia; `log_agent_run` de `main.py` cambia igual en los dos. En la
especificación 08 ningún módulo cambia. En la especificación 09, `pii.py` nace como copia idéntica, y el
enmascaramiento y la auditoría de `main.py` cambian igual en los dos; `citations.py` y `policy_ids` son solo de
Políticas.

## Principios

- Todo lo del HR Assistant: sin estado, bucle con tope, herramientas de solo lectura, `request_id` y log JSON sin
  texto de preguntas, métricas por proceso, costo medido, claves por cliente, límite, compliance al arrancar,
  concurrencia con candados, enlace armado al arrancar, métricas de negocio en la misma `Metrics`, configuración
  de costos de producción y datos personales enmascarados con auditoría de rechazos (ADR 0001 a 0018 del HR).
- Servicio aparte en el mismo repositorio, con su propio contexto de Docker y sus propias etapas de CI (ADR 0001).
- Ningún import de `product/app/`: los módulos se copian (ADR 0002).
- Un tema coincide si un `topic` o una `keyword`, sin acentos ni mayúsculas, es igual a él o está dentro; la
  respuesta cita los `id` (ADR 0003).
- Solo se cita lo que devolvió una herramienta en la misma petición; si no, texto fijo (ADR 0018 del HR).
- Políticas ficticias de ejemplo; la página lo dice y no son asesoría legal.

## Variables propias de Políticas

Las demás variables y sus valores por omisión son los del HR Assistant. Las especificaciones 07, 08 y 09 no
agregan variables; la 08 fija en `render.yaml` `ROUTING=false` y `CACHE_TTL_SECONDS=3600` para este servicio.

| Variable | Por omisión | Dónde actúa |
| --- | --- | --- |
| `POLICIES_PATH` | `data/policies.json` | `config.py` y `policies.py`; reemplaza a `EMPLOYEES_PATH` |
| `SERVICE_NAME` | `politicas-rh` | Campo `service` del log |
| `COMPANION_NAME` | `HR Assistant` | `page.py`; texto del enlace |
| `COMPANION_URL` | vacía | `page.py`; en Render, secreto con `sync: false` |
| `LANGSMITH_PROJECT` | `politicas-rh` | `tracing.py`; proyecto de las trazas |

## Dónde mirar

- Log: salida estándar del servicio `Fabric-AI-M4-politicas` en Render; se filtra por `request_id` o `client`, y
  por `auth_failed`, `rate_limited` y `pii_detected` para los rechazos y la PII.
- Métricas: `GET /metrics` con una clave de Políticas. Uso y costo por modelo en `by_model`, `search_policies` y
  `get_policy` en `tools`, respuestas cortadas en `stopped`, caché en `cached_calls` y clases de código en
  `status`. En producción `by_model` solo muestra `MODEL_LARGE` y `cached_calls` cuenta las llamadas servidas por
  la caché del gateway, que no suman costo.
- Respuestas de `/ask` en producción: `route` es `routing_disabled`; `cached_calls` mayor que 0 indica que la
  respuesta salió de la caché; `pii_masked` lista los tipos enmascarados. Una respuesta igual a «No encontré esa
  información en las políticas...» indica una cita que ninguna herramienta respaldó.
- Configuración de producción: `render.yaml`, servicio `Fabric-AI-M4-politicas`; la comprueba
  `verification/contract/test_contract_08.py`.
- PII y auditoría: `verification/contract/test_contract_09_politicas.py`; controles en
  `doc/compliance-checklist.md`.
- Documentación de la API: Swagger en `/docs`, con el título «Asistente de políticas de RH».
- Pipeline: las etapas `*-politicas` en la pestaña Actions.
- Producción: `uv run python -m verification production <url-hr> <url-politicas>` con `SMOKE_API_KEY` y
  `SMOKE_API_KEY_POLITICAS` en el entorno. El `scripts/smoke.py` propio de Políticas lee la clave de
  `SMOKE_API_KEY`, como el del HR.
