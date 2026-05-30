"""Fase 5: JSON-kontrakt for setups.json."""

from __future__ import annotations

import json
import re

from setups import publish
from setups.gate import BaseRate
from setups.generator import Setup

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _setup(instrument, score, published, **kw):
    defaults = dict(
        ticker=instrument.upper(), as_of="2026-05-28", direction="LONG", grade="A",
        score=score, entry=100.0, sl=98.0, tp=104.0, rr=2.0, atr=1.0,
        base_rate=BaseRate(35, 0.6, (0.55, 0.74), 0.5, (0.2, 0.8), published, "godkjent"),
        published=published, reject_reason="", drivers=[{"name": "x", "ok": True,
                                                         "score": 0.5, "detail": "d"}],
    )
    defaults.update(kw)
    return Setup(instrument=instrument, **defaults)


def test_payload_shape_and_ordering():
    setups = [
        _setup("Gold", 0.2, False),     # forkastet, svakere
        _setup("EURUSD", 0.7, True),    # publisert, sterkere
    ]
    payload = publish.build_payload(setups, as_of="2026-05-28")

    assert payload["schema_version"] == publish.SCHEMA_VERSION
    assert ISO_RE.match(payload["generated"])
    assert payload["as_of"] == "2026-05-28"
    assert len(payload["signals"]) == 2
    # Publiserte først.
    assert payload["signals"][0]["instrument"] == "EURUSD"
    assert payload["signals"][0]["published"] is True

    sig = payload["signals"][0]
    for key in ("instrument", "ticker", "direction", "grade", "score", "published",
                "entry", "sl", "tp", "rr", "atr", "base_rate", "drivers", "reject_reason"):
        assert key in sig
    assert sig["base_rate"]["n"] == 35
    assert sig["base_rate"]["hit_rate_ci"] == [0.55, 0.74]


def test_write_json_roundtrip(tmp_path):
    payload = publish.build_payload([_setup("Gold", 0.7, True)], as_of="2026-05-28")
    out = publish.write_json(payload, tmp_path / "d" / "setups.json")
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["signals"][0]["ticker"] == "GOLD"
    assert loaded["schema_version"] == 1
