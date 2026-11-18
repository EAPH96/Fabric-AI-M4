# ADR 0007: Enrutamiento por regla y modelos elegidos por nombre

Estado: aceptada

## Contexto

Queremos mandar las preguntas simples a un modelo barato y las complejas a uno capaz. Usar otro modelo
para decidir costaría tokens y no sería repetible. Además, las palancas deben medirse sin red: el modelo
simulado tiene que costar como el modelo real que representa.

## Decisión

- `router.py` define `choose_route(question, routing) -> Route(model, reason)`, una regla pura en este
  orden: `routing_disabled`, `long_question` (más de `ROUTER_MAX_CHARS`), `keyword:<palabra>` (subcadena
  en `casefold()`), y si nada aplica `simple` al modelo pequeño.
- `build_models` devuelve un diccionario `{MODEL_SMALL: modelo, MODEL_LARGE: modelo}`; con `fake` son dos
  `FakeModel` con ese nombre, con `gateway` dos `GatewayModel`.
- El precio se busca por el nombre de la ruta, no por la clase del modelo.

## Consecuencias

- La regla se prueba sin modelo y es determinista; el `reason` explica cada decisión en la respuesta y el log.
- Un falso positivo (por ejemplo «métodos» contiene «todos») solo encarece la respuesta, no la empeora.
- Cambiar los modelos es cambiar variables de entorno y precios, no código.
