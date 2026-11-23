# Lista de compliance del Asistente de políticas de RH

Políticas copia del HR Assistant los módulos de seguridad (`security`, `ratelimit`, `compliance`, `observability`,
`pii`) sin cambios de lógica, y `tracing` solo cambia el nombre del proyecto (ADR 0002). Las reglas de arranque en
producción y las de acceso son las mismas: ver `product/doc/compliance-checklist.md`. Cada regla está en el archivo
del mismo nombre bajo `product/politicas/app/` y se comprueba con los contratos de Políticas
(`test_contract_politicas.py`, `test_contract_07_politicas.py` y `test_contract_09_politicas.py`). Aquí se listan
los controles de la especificación 09 y el único propio de Políticas, la validación de citas (ADR 0018 del HR).

## Datos personales y auditoría (especificación 09)

Los escenarios están en `tests/features/privacy.feature`; los contratos, en
`verification/contract/test_contract_09_politicas.py`.

| Control | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| Se detectan CURP, RFC, correo, CLABE, tarjeta, NSS y teléfono solo con `re`, en ese orden, con sus marcas y con límites de palabra; cada coincidencia se reemplaza por su marca antes de buscar el siguiente tipo | `app/pii.py`, `PII_RULES` y `mask_pii` (copia idéntica del HR) | `tests/test_pii.py`, las mismas pruebas que el HR |
| Una CURP no cuenta también como RFC, ni una CLABE como tarjeta o teléfono; `POL-003`, `EMP-0004` y una fecha no son PII | `app/pii.py`, `PII_RULES` | `tests/test_pii.py`: `test_a_curp_is_not_also_counted_as_an_rfc`, `test_a_clabe_is_not_counted_as_a_card_or_a_phone`, `test_ids_and_dates_are_not_personal_data` |
| La pregunta y cada mensaje del historial se enmascaran antes del enrutador, el modelo, el gateway (y su caché), las herramientas y la traza; la pregunta con PII no se rechaza (`200`) | `app/main.py`, `ask` | Escenarios «A question with a CURP and an email is masked before the model» y «A phone number in the history is masked before the model» |
| La respuesta se enmascara antes de devolverla, dentro de la traza `chain` | `app/main.py`, `ask` | Escenarios «An email in the answer is masked before it is returned» y «The chain trace only sees the masked question and the masked answer» |
| `AskResponse.pii_masked` lista los tipos, ordenados y sin repetir; nunca los valores; vacía si no hubo PII | `app/main.py`, `AskResponse` y `ask` | `tests/test_pii.py`, `test_types_are_sorted_and_never_repeated`; escenario «A question without personal data is not changed»; contrato `test_personal_data_is_masked_and_never_logged` |
| `pii_detected` con `where` y `types`, nunca el valor | `app/main.py`, `log_pii` | Escenarios de PII de `privacy.feature`; contrato `test_personal_data_is_masked_and_never_logged` |
| `auth_failed` con `reason` `missing` o `invalid` por cada `401`, nunca la clave | `app/main.py`, `build_client_guard` | Escenarios «Asking without a key is audited as missing» y «Asking with a wrong key is audited as invalid and the key is never logged»; contrato `test_rejected_keys_are_audited_without_the_key` |
| `rate_limited` con `client` y `retry_after` por cada `429` | `app/main.py`, `build_client_guard` | Escenario «Passing the limit is audited with the client and the seconds to wait»; contrato `test_the_rate_limit_is_audited` |

## Citas de Políticas (especificación 09)

| Control | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| El agente anota los id que el catálogo devolvió en la petición (`search_policies` y `get_policy`); un «not found» no cuenta | `app/agent.py`, `AgentResult.policy_ids` | `tests/test_citations.py`: `test_the_agent_records_the_policies_returned_by_both_tools` y `test_a_policy_or_topic_that_was_not_found_is_not_recorded` |
| Si la respuesta cita un `POL-` con 3 dígitos que no está en `policy_ids`, se reemplaza completa por «No encontré esa información en las políticas. Pregunta por una política (POL-001) o un tema, como vacaciones.»; `POL-0001` no es una cita | `app/citations.py`, `check_citations` y `NOT_FOUND_ANSWER` | `tests/test_citations.py`: `test_a_citation_no_tool_returned_replaces_the_whole_answer` y `test_an_id_with_four_digits_is_not_a_citation`; escenario «A policy the model cites without consulting it is replaced by the not found text»; escenarios «Asking for an unknown policy gets the not found text» y «A question without a policy id or a topic gets the not found text» (`tests/features/policies.feature`) |
| Una respuesta sin citas, o con citas que sí devolvió una herramienta, no cambia | `app/citations.py`, `check_citations` | `tests/test_citations.py`: `test_citations_returned_by_a_tool_keep_the_answer` y `test_an_answer_without_citations_is_unchanged`; escenarios «A policy returned by a tool keeps its citation» y «Asking for a policy by its id cites it» |
| La validación corre una vez, antes de enmascarar, así el texto de reemplazo no se vuelve a validar | `app/main.py`, `ask` | Escenario «A policy the model cites without consulting it is replaced by the not found text» (el texto llega intacto y sin tipos enmascarados) |

## Cómo revisarlo a mano

1. Desde la raíz del repositorio: `uv run python -m verification unit` y `uv run python -m verification contract`.
2. Pregunta «¿Qué dice la política POL-999?» con una clave válida: la respuesta es el texto de reemplazo, porque
   ninguna herramienta devolvió esa política.
3. Pregunta «Mi correo es ana.prueba@ejemplo.com, ¿cuántos días de vacaciones me tocan?»: la respuesta cita
   `POL-001`, trae `pii_masked: ["email"]` y el log no contiene el correo.
