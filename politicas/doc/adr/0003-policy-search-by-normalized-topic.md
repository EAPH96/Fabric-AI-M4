# ADR 0003: Búsqueda de políticas por tema normalizado y cita del id

Estado: aceptada

## Contexto

La especificación 06 pide `search_policies(topic)`, que devuelva las políticas cuyo `topic` o alguna `keyword`
«coincide» con el tema sin distinguir mayúsculas ni acentos, y un modelo simulado que pida esa herramienta si el
mensaje «menciona» un topic o una keyword. No dice si coincidir es ser igual o estar contenido, ni qué término
elige el modelo simulado cuando el mensaje menciona varios. La respuesta siempre cita el `id` de cada política.

## Decisión

- `normalize(text)` quita acentos (NFKD sin marcas), mayúsculas (`casefold`) y espacios en los extremos; se aplica
  al tema, al mensaje y a cada término.
- Una política coincide si su `topic` o una `keyword` normalizados son iguales al tema o están dentro de él. Así
  `vacaciones` y «días de vacaciones» encuentran `POL-001`, y `prima vacacional` encuentra `POL-002` sin traer
  `POL-001`.
- El modelo simulado recorre los términos en el orden del archivo (por política, primero el `topic` y luego sus
  `keywords`) y pide `search_policies` con el primero que aparece en el mensaje, escrito como en el archivo.
- `search_policies` devuelve `id` y `title`; `get_policy`, `id`, `title` y `text`. La cita sale del resultado de la
  herramienta; el `SYSTEM_PROMPT` del modelo real pide citar los `id` y no inventar.

## Alternativas descartadas

- Igualdad exacta: el modelo real suele mandar frases («días de vacaciones») y no encontraría nada.
- Que el término esté dentro del tema o el tema dentro del término: «días» traería vacaciones, festivos y
  aguinaldo a la vez.
- Búsqueda por palabras sueltas o por el texto de la política: más resultados de los que se pueden citar y otro
  comportamiento que el de la especificación.

## Consecuencias

- Hay coincidencias falsas por subcadena («ropa» en «Europa»); solo afectan al modelo simulado, que existe para
  las pruebas.
- El orden de `data/policies.json` decide el término del modelo simulado; cambiarlo puede cambiar respuestas de la
  evaluación.
- Los casos de `eval_set_politicas.json` y los contratos se revisaron contra esta regla.
