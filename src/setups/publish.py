"""Publisering: setups → `web/data/setups.json`.

JSON-kontrakt (stabil for UI-et):
  schema_version : int
  generated      : ISO UTC (når payloaden ble bygd)
  as_of          : 'YYYY-MM-DD' (beslutningsdato på NIVÅ-feeden)
  signals        : liste av setups (både publiserte og forkastede, med grunn)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from setups.generator import Setup

SCHEMA_VERSION = 1
DEFAULT_OUT = Path("web/data/setups.json")


def _setup_to_signal(s: Setup) -> dict:
    br = asdict(s.base_rate) if s.base_rate is not None else None
    if br is not None:  # tupler → lister (JSON-native, så in-memory == serialisert)
        br["hit_rate_ci"] = list(br["hit_rate_ci"])
        br["expectancy_ci"] = list(br["expectancy_ci"])
    return {
        "instrument": s.instrument,
        "ticker": s.ticker,
        "direction": s.direction,
        "grade": s.grade,
        "score": s.score,
        "published": s.published,
        "entry": s.entry,
        "sl": s.sl,
        "tp": s.tp,
        "rr": s.rr,
        "atr": s.atr,
        "reject_reason": s.reject_reason,
        "base_rate": br,
        "scenario": s.scenario,
        "drivers": s.drivers,
    }


def build_payload(setups: list[Setup], as_of: str) -> dict:
    signals = [_setup_to_signal(s) for s in setups]
    # Publiserte først, deretter sterkest signal.
    signals.sort(key=lambda x: (not x["published"], -abs(x["score"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "signals": signals,
    }


def write_json(payload: dict, out: Path | str = DEFAULT_OUT) -> Path:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path
