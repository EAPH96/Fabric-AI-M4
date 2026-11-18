# ADR 0003: Un solo agente con bucle con tope y herramientas de solo lectura

Estado: aceptada

## Contexto

Un agente que decide qué herramienta usar puede entrar en ciclos y gastar llamadas sin fin. Los
datos de empleados son sensibles: el agente no debe poder modificarlos.

## Decisión

- Un único agente con dos herramientas de solo lectura: `get_employee` y `search_by_department`.
- Cada vuelta es una llamada al modelo y cuenta como un paso (`steps`). El tope es
  `AGENT_MAX_STEPS` (por omisión 3, mínimo 1, validado al arrancar).
- Si se agota el tope sin respuesta, el agente contesta exactamente
  `No pude completar la respuesta. Intenta con una pregunta más concreta.`
- Los errores de herramienta (empleado inexistente, herramienta desconocida, argumentos inválidos)
  se devuelven como texto al modelo, no como excepciones. Una salida del modelo que no es JSON
  válido termina el bucle con el mensaje de tope.

## Consecuencias

- El costo por pregunta está acotado y es predecible.
- Preguntas que necesiten más de `AGENT_MAX_STEPS - 1` herramientas no se pueden responder; se
  sube el tope por configuración.
- Agregar herramientas es registrar una función de solo lectura en el agente.
