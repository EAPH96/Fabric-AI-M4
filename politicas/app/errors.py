"""Errores compartidos por la configuración y la seguridad.

``ConfigError`` vive aquí para que ``app.config`` y ``app.security`` lo usen sin
importarse en círculo; ``app.config`` lo vuelve a exportar, así que
``from app.config import ConfigError`` sigue funcionando.
"""


class ConfigError(ValueError):
    """Error de configuración: un valor de entorno es inválido."""
