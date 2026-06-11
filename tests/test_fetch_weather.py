"""Open-Meteo vær-henting: parsing + 429/backoff (nettverksfri, mocket)."""

from __future__ import annotations

import pytest

from setups.fetch import weather


class _FakeResp:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_region_parses_daily(monkeypatch):
    payload = {"daily": {
        "time": ["2026-01-01", "2026-01-02"],
        "precipitation_sum": [0.0, 3.2],
        "temperature_2m_max": [28.0, 27.5],
        "temperature_2m_min": [18.0, 17.0],
    }}
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: _FakeResp(payload))

    rows = weather.fetch_region("brazil_cs_cane", -21.17, -47.81, start="2026-01-01")
    assert rows == [
        ("2026-01-01", 28.0, 18.0, 0.0),
        ("2026-01-02", 27.5, 17.0, 3.2),
    ]


def test_fetch_region_handles_empty(monkeypatch):
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: _FakeResp({}))
    assert weather.fetch_region("x", 0.0, 0.0) == []


def test_fetch_region_retries_on_429(monkeypatch):
    """429 én gang → backoff → suksess (uten å vente reelt)."""
    payload = {"daily": {
        "time": ["2026-01-01"],
        "precipitation_sum": [1.0],
        "temperature_2m_max": [20.0],
        "temperature_2m_min": [10.0],
    }}
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp({}, status_code=429, headers={"Retry-After": "0"})
        return _FakeResp(payload, status_code=200)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda *_: None)

    rows = weather.fetch_region("x", 0.0, 0.0)
    assert rows == [("2026-01-01", 20.0, 10.0, 1.0)]
    assert calls["n"] == 2  # første feilet, andre lyktes


def test_fetch_region_retries_on_5xx(monkeypatch):
    """503 (uten Retry-After) → eksponentiell backoff → suksess."""
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp({}, status_code=503)
        return _FakeResp({"daily": {}}, status_code=200)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda *_: None)

    assert weather.fetch_region("x", 0.0, 0.0) == []
    assert calls["n"] == 2


def test_fetch_region_gives_up_after_max_retries(monkeypatch):
    """Vedvarende 429 → reiser HTTPError (update.sh fanger og fortsetter)."""
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _FakeResp({}, status_code=429)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda *_: None)

    with pytest.raises(weather.requests.HTTPError):
        weather.fetch_region("x", 0.0, 0.0)
    assert calls["n"] == weather.MAX_RETRIES


@pytest.mark.skipif(True, reason="live Open-Meteo-kall; kjøres manuelt")
def test_fetch_region_live():
    rows = weather.fetch_region("brazil_cs_cane", -21.17, -47.81, start="2026-05-01")
    assert len(rows) > 0
