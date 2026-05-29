"""Fase 0 røyktest: pakken importeres og secrets-laster fungerer."""

from __future__ import annotations

import setups
from setups import secrets


def test_package_imports() -> None:
    assert setups.__doc__


def test_env_overrides_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text('FRED_API_KEY="from_file"\n# kommentar\nEMPTY=\n')
    monkeypatch.setenv(secrets.SECRETS_PATH_ENV, str(env_file))
    secrets.reload_secrets()

    # Fila brukes som fallback ...
    assert secrets.get_secret("FRED_API_KEY") == "from_file"
    # ... men ekte miljøvariabel vinner.
    monkeypatch.setenv("FRED_API_KEY", "from_env")
    assert secrets.get_secret("FRED_API_KEY") == "from_env"

    assert secrets.get_secret("MANGLER", "fallback") == "fallback"
