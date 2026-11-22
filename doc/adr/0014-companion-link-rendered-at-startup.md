# ADR 0014: Enlace al otro producto armado en el servidor al arrancar

Estado: aceptada

## Contexto

La especificación 05 pide un enlace al Asistente de políticas de RH en el encabezado de la página, con
`COMPANION_URL` y `COMPANION_NAME`, que no aparezca si la URL está vacía. No puede cambiar rutas ni respuestas, y el
contrato busca `data-testid="companion-link"` en el HTML de `GET /`. Políticas (especificación 06) copiará el mismo
mecanismo con «HR Assistant» como nombre.

## Decisión

- `app/page.py` arma el `<a data-testid="companion-link">` con la URL y el nombre escapados con `html.escape`, y lo
  pone en lugar del marcador `<!-- COMPANION_LINK -->` del `<header>` de `index.html`. Sin URL, el marcador se
  borra y no hay enlace.
- `create_app` arma la página una sola vez al arrancar; `GET /` devuelve siempre el mismo HTML.
- El enlace abre otra pestaña (`target="_blank"`, `rel="noopener noreferrer"`): la conversación vive solo en el
  navegador (ADR 0001) y no se pierde.
- Las dos variables viven en `PageSettings`, junto con `max_question_chars`, para que `Settings` siga con 7 campos.

## Alternativas descartadas

- Armarlo con JavaScript leyendo un endpoint de configuración: ruta nueva (la especificación no lo permite) y el
  contrato no vería el enlace en `GET /`.
- Plantillas Jinja2: una dependencia nueva para sustituir una sola línea.
- Abrir el enlace en la misma pestaña: borraría la conversación.

## Consecuencias

- Cambiar `COMPANION_URL` pide reiniciar el proceso, como cualquier otra variable.
- Si alguien borra el marcador de `index.html`, el enlace deja de salir; una prueba unitaria lo vigila.
- La URL no se valida: la pone quien opera el servicio y el escape impide salir del atributo `href`.
- Políticas copia `app/page.py` sin cambios; solo cambia el valor por omisión de `COMPANION_NAME`.
