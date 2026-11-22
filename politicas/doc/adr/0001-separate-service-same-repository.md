# ADR 0001: Servicio aparte en el mismo repositorio

Estado: aceptada. Precisa el ADR 0012 del HR Assistant (publicación con aprobación y CI en verde) sin reemplazarlo.

## Contexto

La especificación 06 pide un segundo producto, el Asistente de políticas de RH, que viva en `product/politicas/`,
en el mismo repositorio que el HR Assistant, y que se despliegue como un servicio aparte. El HR ya se publica en
Render con un Blueprint (`render.yaml`) y un pipeline de cuatro etapas (`ci.yml`) que no deben cambiar.

## Decisión

- Políticas es una aplicación FastAPI completa en `product/politicas/`, con su `app/`, `data/`, `tests/`, `e2e/`,
  `Dockerfile`, `requirements.txt` y `doc/`. Se construye con `politicas/` como contexto de Docker.
- `render.yaml` agrega un segundo servicio web, `Fabric-AI-M4-politicas`, con `dockerfilePath:
  ./politicas/Dockerfile`, `dockerContext: ./politicas`, `healthCheckPath: /health` y `autoDeployTrigger:
  checksPass`; sus secretos (`API_KEYS`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `COMPANION_URL`) van con `sync: false`.
- `ci.yml` agrega `style-politicas -> unit-politicas -> e2e-politicas -> docker-politicas`, con
  `working-directory: politicas`, en paralelo con la cadena del HR.
- Cada servicio tiene sus propias claves de cliente; la prueba de humo de la fábrica usa `SMOKE_API_KEY` para el
  HR y `SMOKE_API_KEY_POLITICAS` para Políticas.

## Alternativas descartadas

- Un repositorio aparte: duplicaría la fábrica, los permisos y el proceso de publicación; la especificación pide
  el mismo repositorio.
- Servir las dos aplicaciones en un solo proceso (rutas `/hr` y `/politicas`): rompe el contrato de rutas de cada
  producto y obliga a publicarlos juntos.
- Un Blueprint por servicio: Render lee un solo `render.yaml` por repositorio.

## Consecuencias

- `checksPass` espera todas las etapas del commit: si una etapa de Políticas falla, tampoco se publica el HR, y al
  revés. Es lo que pide la especificación.
- El HR usa la raíz como contexto y no tiene filtro de rutas: un cambio solo en `politicas/` lo vuelve a publicar,
  con la misma imagen (su Dockerfile solo copia `app` y `data`).
- Cada servicio corre en su propia instancia de Render free: métricas, límite y log son de cada uno.
