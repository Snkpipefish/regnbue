"""Fase 2: FRED-parsing (nettverksfri, mocket)."""

from __future__ import annotations

import pytest

from setups.fetch import fred


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_series_skips_missing_and_parses(monkeypatch):
    payload = {"observations": [
        {"date": "2026-01-01", "value": "4.50"},
        {"date": "2026-01-02", "value": "."},      # manglende → hoppes over
        {"date": "2026-01-03", "value": ""},         # tom → hoppes over
        {"date": "2026-01-04", "value": "4.55"},
    ]}
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: _FakeResp(payload))

    obs = fred.fetch_series("DGS10", start="2026-01-01")
    assert obs == [("2026-01-01", 4.50), ("2026-01-04", 4.55)]


def test_fetch_series_handles_empty(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: _FakeResp({}))
    assert fred.fetch_series("DGS10") == []


@pytest.mark.skipif(True, reason="live FRED-kall; kjøres manuelt")
def test_fetch_series_live():
    obs = fred.fetch_series("DGS10", start="2026-05-01")
    assert len(obs) > 0
