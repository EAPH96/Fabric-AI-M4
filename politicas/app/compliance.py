"""Compliance como código: reglas que se revisan al arrancar (ADR 0012 del HR).

Solo con ``ENVIRONMENT=production``. Si una regla falla, ``create_app`` lanza
``ConfigError`` y el proceso no sirve ni una petición. Los mensajes nombran la
variable, el cliente y el largo de la clave, nunca su valor. Las reglas son las
mismas del HR, cuya tabla está en su ``doc/compliance-checklist.md``.
"""

from app.config import FAKE_PROVIDER, PRODUCTION, ConfigError

MIN_API_KEY_LENGTH = 16


def _model_violations(settings):
    """Regla 1: en producción no se usa el modelo simulado.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :return: Violaciones encontradas
    :rtype: list[str]
    """
    if settings.model_provider == FAKE_PROVIDER:
        return [f"MODEL_PROVIDER must not be '{FAKE_PROVIDER}' in production"]
    return []


def _api_key_violations(settings):
    """Reglas 2 y 3: hay al menos una clave y todas tienen 16 caracteres o más.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :return: Violaciones encontradas, con cliente y largo, nunca la clave
    :rtype: list[str]
    """
    api_keys = settings.security.api_keys
    if not api_keys:
        return ["API_KEYS must name at least one client in production"]
    return [
        f"API_KEYS key of client '{client}' must have at least "
        f"{MIN_API_KEY_LENGTH} characters in production (length {len(key)})"
        for client, key in api_keys.items()
        if len(key) < MIN_API_KEY_LENGTH
    ]


def _tracing_violations(settings):
    """Regla 4: con trazas encendidas, entradas y salidas van ocultas.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :return: Violaciones encontradas
    :rtype: list[str]
    """
    options = settings.observability
    if not options.langsmith_tracing:
        return []
    flags = (
        ("HIDE_INPUTS", options.hide_inputs),
        ("HIDE_OUTPUTS", options.hide_outputs),
    )
    return [
        f"{name} must be true when LANGSMITH_TRACING is true in production"
        for name, hidden in flags
        if not hidden
    ]


def compliance_violations(settings):
    """Lista las reglas de producción que la configuración incumple.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :return: Un mensaje por regla incumplida; vacía en ``development`` o si
        todo se cumple
    :rtype: list[str]
    """
    if settings.security.environment != PRODUCTION:
        return []
    return [
        *_model_violations(settings),
        *_api_key_violations(settings),
        *_tracing_violations(settings),
    ]


def enforce_compliance(settings):
    """Impide arrancar si la configuración incumple alguna regla de producción.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :raises app.config.ConfigError: Con todas las reglas incumplidas, sin
        ningún valor secreto
    """
    violations = compliance_violations(settings)
    if violations:
        raise ConfigError(
            "production compliance failed: " + "; ".join(violations)
        )
