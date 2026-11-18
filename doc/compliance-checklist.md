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

## Cómo revisarlo a mano

1. Desde la raíz del repositorio: `uv run python -m verification unit` y `uv run python -m verification contract`.
2. Para ver una regla fallar, arranca con `ENVIRONMENT=production` y `MODEL_PROVIDER=fake`: el proceso termina con
   `production compliance failed: MODEL_PROVIDER must not be 'fake' in production`.
