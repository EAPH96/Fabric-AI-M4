# Lista de compliance del HR Assistant

Las reglas de producción se revisan solas al arrancar: con `ENVIRONMENT=production`, `create_app` llama
`enforce_compliance` antes de armar nada y, si una regla falla, lanza `ConfigError` y el proceso termina sin servir
ni una petición (ADR 0012). En `development` estas reglas no se aplican. Los mensajes nombran la variable, el
cliente y el largo de la clave, nunca su valor.

## Reglas que impiden arrancar en producción

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| `MODEL_PROVIDER` no puede ser `fake` | `app/compliance.py`, `_model_violations` | Escenario «Production refuses to start with the fake model» (`tests/features/security.feature`); contrato `test_production_refuses_the_fake_model` |
| `API_KEYS` tiene al menos un cliente | `app/compliance.py`, `_api_key_violations` | `tests/test_compliance.py`, caso `no_api_keys` |
| Toda clave de `API_KEYS` tiene 16 caracteres o más | `app/compliance.py`, `_api_key_violations` (`MIN_API_KEY_LENGTH`) | `tests/test_compliance.py`, caso `key_shorter_than_16` (el mensaje no muestra la clave) |
| Con `LANGSMITH_TRACING=true`, `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` | `app/compliance.py`, `_tracing_violations` | `tests/test_compliance.py`, caso `traces_show_inputs` |
| Una configuración de producción correcta arranca; `development` no aplica reglas | `app/compliance.py`, `compliance_violations` | `tests/test_compliance.py`, `test_development_and_a_correct_production_have_no_violations` |
| Las reglas se revisan antes de servir | `app/main.py`, `create_app` llama `enforce_compliance` | Escenario de producción con modelo simulado; contrato 04 (`import app.main` termina con código distinto de 0) |

## Reglas de acceso que valen en todo entorno

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| `ENVIRONMENT` solo acepta `development` o `production` (un error de dedo no se salta compliance) | `app/config.py`, `_environment` | `tests/test_security_config.py`, `test_unknown_environment_or_zero_rate_limit_prevents_start` |
| `API_KEYS` mal formada impide arrancar; el error dice la entrada y su largo, nunca su valor | `app/security.py`, `parse_api_keys` (error lanzado `from None`) | `tests/test_security.py`, `test_malformed_api_keys_entry_is_reported_without_its_value`; contrato `test_a_broken_api_keys_never_leaks_the_key` |
| Las claves no salen en `repr` de la configuración | `app/config.py`, `SecuritySettings.api_keys` con `repr=False` | `tests/test_security_config.py`, `test_api_keys_are_loaded_but_never_shown_in_the_settings` |
| `POST /ask` y `GET /metrics` piden `X-API-Key`; sin ella o inválida, `401 {"detail": "invalid or missing API key"}` | `app/main.py`, `build_client_guard` (dependencia de ruta) | Escenarios «Asking without a key is rejected», «Asking with a wrong key is rejected» y de `/metrics`; contrato 04 |
| `/`, `/health` y `/docs` no piden clave | `app/main.py`: la dependencia solo está en `/ask` y `/metrics` | Escenario «The page, the health check and the docs are open but the metrics need a key» |
| Las claves se comparan en tiempo constante, contra todas, sin tronar con texto no ASCII | `app/security.py`, `ApiKeyAuth.identify` (`hmac.compare_digest` sobre bytes) | `tests/test_security.py`, `test_identify_accepts_only_the_key_of_a_known_client` |
| El log y las trazas llevan el nombre del cliente, nunca la clave | `app/observability.py` (`RequestObserver`, middleware) y `app/tracing.py` (`metadata`) | Escenario «A valid key answers and the log names the client but never the key»; `tests/test_tracing.py`, `test_trace_metadata_names_the_request_id_and_the_client` |
| Más de `RATE_LIMIT_PER_MINUTE` peticiones por cliente en un minuto: `429 {"detail": "rate limit exceeded"}` con `Retry-After` | `app/ratelimit.py`, `RateLimiter.check`; `app/main.py`, `build_client_guard` | `tests/test_ratelimit.py`; escenarios de límite de `security.feature`; contrato `test_too_many_requests_returns_429_with_retry_after` |
| `RATE_LIMIT_PER_MINUTE` es un entero de 1 o más | `app/config.py`, `_security` | `tests/test_security_config.py` |
| La página guarda la clave solo en `sessionStorage` (nunca en el almacenamiento persistente ni en el HTML) y la manda en `X-API-Key` | `app/static/index.html`, `currentApiKey` y `ask` | `tests/test_main.py`, `test_home_page_asks_for_the_key_and_keeps_it_only_for_the_session`; pruebas e2e de `e2e/test_chat_page.py` |
| La página muestra «Clave inválida» con `401` y «Demasiadas preguntas; espera N segundos» con `429` | `app/static/index.html`, `errorMessage` y `rateLimitMessage` | `tests/test_main.py`; prueba e2e `test_a_wrong_api_key_shows_an_invalid_key_message` |

## Datos personales y auditoría (especificación 09)

Valen en todo entorno y no se pueden apagar (ADR 0018). El valor de un dato personal o de una clave nunca se
escribe en el log, la traza, las métricas ni la respuesta: solo su tipo o el motivo. Los escenarios están en
`tests/features/privacy.feature`; los contratos, en `verification/contract/test_contract_09.py`.

| Control | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| Se detectan CURP, RFC, correo, CLABE, tarjeta, NSS y teléfono solo con `re`, en ese orden, con sus marcas y con límites de palabra; cada coincidencia se reemplaza por su marca antes de buscar el siguiente tipo | `app/pii.py`, `PII_RULES` y `mask_pii` | `tests/test_pii.py`: `test_rules_follow_the_order_and_marks_of_the_specification`, `test_every_type_is_replaced_by_its_mark`, `test_a_card_is_masked_with_spaces_dashes_or_no_separators`, `test_a_phone_is_masked_with_spaces_or_dashes` |
| Una CURP no cuenta también como RFC, ni una CLABE como tarjeta o teléfono; `EMP-0004`, `POL-003` y una fecha no son PII | `app/pii.py`, `PII_RULES` (orden y `\b`) | `tests/test_pii.py`: `test_a_curp_is_not_also_counted_as_an_rfc`, `test_a_clabe_is_not_counted_as_a_card_or_a_phone`, `test_ids_and_dates_are_not_personal_data` |
| La pregunta y cada mensaje del historial se enmascaran antes del enrutador, el modelo, las herramientas y la traza; la pregunta con PII no se rechaza (`200`) | `app/main.py`, `ask` | Escenarios «A question with a CURP and an email is masked before the model» y «A phone number in the history is masked before the model» (el modelo espía no recibe el valor) |
| La respuesta se enmascara antes de devolverla, dentro de la traza `chain` | `app/main.py`, `ask` | Escenarios «An email in the answer is masked before it is returned» y «The chain trace only sees the masked question and the masked answer» |
| `AskResponse.pii_masked` lista los tipos enmascarados en pregunta, historial y respuesta, ordenados y sin repetir; nunca los valores; vacía si no hubo PII | `app/main.py`, `AskResponse` y `ask`; `app/pii.py`, `mask_pii` | `tests/test_pii.py`, `test_types_are_sorted_and_never_repeated`; escenarios «Personal data in the question, the history and the answer is reported once per place» y «A question without personal data is not changed»; contrato `test_personal_data_is_masked_and_never_logged` |
| Un `pii_detected` por cada lugar con PII, con `where` (`question`, `history` o `answer`) y `types`, nunca el valor | `app/main.py`, `log_pii` | Escenario «Personal data in the question, the history and the answer is reported once per place»; contrato `test_personal_data_is_masked_and_never_logged` (ninguna línea del log contiene la CURP ni el correo) |
| `auth_failed` por cada `401`: `reason` `missing` sin encabezado o con encabezado vacío, `invalid` si la clave no es de nadie; nunca la clave ni una parte | `app/main.py`, `build_client_guard` | Escenarios «Asking without a key is audited as missing», «Asking with an empty key is audited as missing» y «Asking with a wrong key is audited as invalid and the key is never logged»; contrato `test_rejected_keys_are_audited_without_the_key` |
| `rate_limited` con `client` y `retry_after` por cada `429` | `app/main.py`, `build_client_guard` | Escenario «Passing the limit is audited with the client and the seconds to wait»; contrato `test_the_rate_limit_is_audited` |

## Cómo revisarlo a mano

1. Desde la raíz del repositorio: `uv run python -m verification unit` y `uv run python -m verification contract`.
2. Para ver una regla fallar, arranca con `ENVIRONMENT=production` y `MODEL_PROVIDER=fake`: el proceso termina con
   `production compliance failed: MODEL_PROVIDER must not be 'fake' in production`.
3. Para ver la PII enmascarada, pregunta «Mi correo es ana.prueba@ejemplo.com, ¿quién es EMP-0004?» con una clave
   válida: la respuesta trae `pii_masked: ["email"]`, el log tiene `pii_detected` y no contiene el correo.
