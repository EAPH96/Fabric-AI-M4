# ADR 0012: Compliance al arrancar y publicación solo con el pipeline en verde

Estado: aceptada

## Contexto

Una configuración insegura en producción (modelo simulado, sin claves, claves cortas, trazas con texto de
empleados) no debe llegar a servir peticiones. Y nada debe publicarse sin pasar las mismas pruebas que la fábrica y
sin que una persona lo apruebe.

## Decisión

- `app/compliance.py` revisa las reglas de `spec/04-production.md` solo con `ENVIRONMENT=production`;
  `create_app` llama `enforce_compliance` antes de armar nada. Si una falla, `ConfigError` y el proceso no arranca.
  `ENVIRONMENT` solo acepta `development` y `production`.
- `doc/compliance-checklist.md` une cada regla con su código y su prueba.
- El producto se empaqueta en una imagen `python:3.12-slim` con usuario no root.
- `.github/workflows/ci.yml` corre `style`, `unit`, `e2e` y `docker` encadenados, con los mismos comandos que la
  verificación local.
- `render.yaml` usa `autoDeployTrigger: checksPass`; los secretos van con `sync: false` y se escriben en Render.
- `scripts/publish.py` solo corre con `output/approved.txt` (aprobación humana, reforzada por el hook).

## Consecuencias

- Un despliegue mal configurado falla al arrancar y Render mantiene la versión anterior.
- El CI es la segunda compuerta: si la fábrica y el CI usan comandos distintos, pueden contradecirse.
- La imagen instala también las librerías de prueba (un solo `requirements.txt`): más grande, pero sin una segunda
  lista que mantener.
