"""Hemmeligheter for Regnbue.

Leser nøkkel/verdi fra ``~/.bedrock/secrets.env`` (gjenbrukt fra prosjekt #1/#2),
men lar ekte miljøvariabler **overstyre** filen. Slik kan CI/produksjon sette en
variabel uten å røre fila, og fila fungerer som lokal fallback.

Filen committes ALDRI (se ``.gitignore``). Egen, frisk implementasjon — ingen
kodekopiering fra bedrock; kun samme env-fil som datakilde.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Lar testene/CI peke et annet sted; ellers bedrock-fila.
SECRETS_PATH_ENV = "REGNBUE_SECRETS_ENV"
DEFAULT_SECRETS_PATH = Path("~/.bedrock/secrets.env")


def _secrets_path() -> Path:
    override = os.environ.get(SECRETS_PATH_ENV)
    path = Path(override) if override else DEFAULT_SECRETS_PATH
    return path.expanduser()


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parser en enkel ``KEY=VALUE`` env-fil. Hopper over blanke/#-linjer."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@lru_cache(maxsize=1)
def _file_secrets() -> dict[str, str]:
    return _parse_env_file(_secrets_path())


def get_secret(key: str, default: str | None = None) -> str | None:
    """Hent én hemmelighet. Miljøvariabel vinner over fila, fila over ``default``."""
    if key in os.environ:
        return os.environ[key]
    return _file_secrets().get(key, default)


def require_secret(key: str) -> str:
    """Som :func:`get_secret`, men kaster hvis den mangler."""
    value = get_secret(key)
    if value is None or value == "":
        raise KeyError(f"Mangler hemmelighet: {key} (verken i miljø eller {_secrets_path()})")
    return value


def reload_secrets() -> None:
    """Tøm cachen — nyttig i tester som bytter ``REGNBUE_SECRETS_ENV``."""
    _file_secrets.cache_clear()
