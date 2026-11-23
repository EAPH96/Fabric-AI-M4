# ADR 0018: PII enmascarada con `re`, citas de Políticas validadas y auditoría de los rechazos

Estado: aceptada (precisa los ADR 0004, 0006, 0010 y 0011; no reemplaza ninguno). Vale para los dos productos: el
HR Assistant y el Asistente de políticas de RH, que hereda los ADR del HR. La validación de citas aplica solo a
Políticas.

## Contexto

Hasta la especificación 08 el log no lleva el texto de preguntas ni respuestas (ADR 0004) y las trazas lo ocultan
en producción (ADR 0006), pero el texto completo sí llega al modelo, al gateway y, en Políticas, a la caché de
Cloudflare (ADR 0017). Una persona puede escribir su CURP o su correo sin mala intención. En Políticas, un modelo
puede responder «según la política POL-002» sin haberla consultado. Y los rechazos de clave (`401`) y de límite
(`429`) solo dejaban el evento `request`, sin decir por qué.

## Decisión

- **PII con `re` en un solo módulo.** `app/pii.py`, copia idéntica en los dos productos, detecta los 7 tipos de la
  especificación 09 en su orden, con límites de palabra, y reemplaza cada coincidencia por su marca antes de
  buscar el siguiente tipo. Devuelve el texto enmascarado y los tipos, en orden alfabético y sin repetir.
- **Se enmascara en la entrada, no se rechaza.** La pregunta y el historial (después de la ventana) se enmascaran
  en `main.py` antes del enrutador, del agente y de la traza; desde ahí el texto original no se usa.
- **Se enmascara en la salida.** La respuesta se revisa con los mismos patrones dentro de la función trazada como
  `chain`. `AskResponse.pii_masked` dice los tipos, nunca los valores; el evento `pii_detected` dice dónde
  (`question`, `history` o `answer`) y los tipos.
- **Citas de Políticas contra lo que devolvieron las herramientas.** El agente de Políticas anota en
  `AgentResult.policy_ids` los id que el catálogo devolvió en esa petición. Si la respuesta cita un `POL-xxx` que
  no está ahí, se reemplaza completa por el texto fijo de la especificación. La regla es literal y sin
  excepciones: también reemplaza un «Policy POL-999 not found» y la ayuda del modelo simulado, que trae
  `(POL-001)` como ejemplo. Se valida antes de enmascarar y una sola vez.
- **Auditoría de los rechazos.** La dependencia de cliente escribe `auth_failed` (`reason`: `missing` o
  `invalid`, nunca la clave) y `rate_limited` (`client`, `retry_after`) antes de responder `401` o `429`.

## Alternativas descartadas

- Rechazar la pregunta con PII (`422`): la persona que escribe su correo no ataca el sistema; la spec lo prohíbe.
- Una biblioteca de detección (Presidio u otra): agrega dependencias y modelos; la spec pide `re` y los tipos
  mexicanos se describen bien con expresiones regulares.
- Enmascarar en el agente o en el `JsonLogger`: el agente no conoce la observabilidad (ADR 0002 y 0006) y el log
  no ve la traza ni el modelo; `main.py` es el único punto por el que pasa todo.
- Validar citas buscando `POL-` en el texto del resultado de la herramienta: un «not found» contaría como cita
  válida.
- Exceptuar la ayuda del modelo simulado o quitarle el ejemplo `(POL-001)`: sería una regla a la medida de un
  doble de prueba, o cambiaría el texto que fija la especificación 06; el texto de reemplazo da la misma guía.
- Un evento por cada respuesta reemplazada: la spec no lo pide.

## Consecuencias

- El modelo, el gateway, la caché de Políticas, el log y las trazas `chain` nunca ven un dato personal; las trazas
  `llm` guardan el texto del modelo, que solo recibió texto enmascarado, y en producción van ocultas (ADR 0012).
- Los patrones pueden fallar en los dos sentidos: un formato raro no se detecta y una cifra de 10 dígitos que no es
  teléfono se enmascara. Se acepta: es una protección de mejor esfuerzo, no una garantía.
- Si la persona necesita que el modelo lea su dato (por ejemplo, «¿está bien escrito mi RFC?»), el producto no
  puede ayudar: verá la marca.
- En Políticas, una respuesta que cita una política del historial sin volver a consultarla se reemplaza; dos
  escenarios de la especificación 06 cambian su resultado esperado.
- Soporte puede filtrar el log por `auth_failed`, `rate_limited` y `pii_detected`; ninguno lleva claves ni valores.
