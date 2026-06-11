"""Fase 2: FRED-parsing (nettverksfri, mocket)."""

from __future__ import annotations

import pytest

from setups.fetch import fred


class _FakeResp:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

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


def test_fetch_series_retries_on_429(monkeypatch):
    """429 én gang → backoff → suksess (uten å vente reelt)."""
    payload = {"observations": [{"date": "2026-01-01", "value": "4.50"}]}
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp({}, status_code=429, headers={"Retry-After": "0"})
        return _FakeResp(payload, status_code=200)

    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(fred.requests, "get", fake_get)
    monkeypatch.setattr(fred.time, "sleep", lambda *_: None)

    obs = fred.fetch_series("DGS10")
    assert obs == [("2026-01-01", 4.50)]
    assert calls["n"] == 2  # første feilet, andre lyktes


def test_fetch_series_gives_up_after_max_retries(monkeypatch):
    """Vedvarende 429 → reiser HTTPError (update.sh fanger og fortsetter)."""
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(fred.requests, "get",
                        lambda *a, **k: _FakeResp({}, status_code=429))
    monkeypatch.setattr(fred.time, "sleep", lambda *_: None)

    with pytest.raises(fred.requests.HTTPError):
        fred.fetch_series("DGS10")


@pytest.mark.skipif(True, reason="live FRED-kall; kjøres manuelt")
def test_fetch_series_live():
    obs = fred.fetch_series("DGS10", start="2026-05-01")
    assert len(obs) > 0
