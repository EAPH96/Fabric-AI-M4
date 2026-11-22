"""Pruebas de los cuatro valores por omisión que cambian en Políticas.

``LANGSMITH_PROJECT`` leído del entorno se prueba en ``test_tracing.py``, donde
también se ve que llega a ``traceable``.
"""

from pathlib import Path

import pytest

from app.config import ConfigError, load_settings

PRODUCT_DIR = Path(__file__).resolve().parents[1]


def test_default_settings_match_the_specification_and_ignore_employees_path():
    settings = load_settings({"EMPLOYEES_PATH": "does-not-exist.json"})

    expected_path = (PRODUCT_DIR / "data" / "policies.json").resolve()
    assert Path(settings.policies_path).resolve() == expected_path
    assert settings.observability.service_name == "politicas-rh"
    assert settings.observability.langsmith_project == "politicas-rh"
    assert settings.page.companion_name == "HR Assistant"


def test_policies_path_to_a_missing_file_raises_config_error_naming_it():
    with pytest.raises(ConfigError, match="POLICIES_PATH"):
        load_settings({"POLICIES_PATH": "data/does-not-exist.json"})
