"""Dealer-gamma: ren GEX-beregning (uten nett) + gamma_regime-driver (DATA_KARTLEGGING §3b)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from setups import store
from setups.fetch.gamma import bs_gamma, compute_snapshot
from setups.score.context import ScoreContext
from setups.score.drivers import gamma_regime

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _c(name, oi=100.0, iv=50.0):
    return {"instrument_name": name, "open_interest": oi, "mark_iv": iv, "interest_rate": 0.0}


# --- BS-gamma ---
def test_bs_gamma_peaks_atm_and_guards():
    assert bs_gamma(100, 100, 0.1, 0.5) > bs_gamma(100, 200, 0.1, 0.5) >= 0
    assert bs_gamma(100, 100, 0.0, 0.5) == 0.0      # ingen tid → 0
    assert bs_gamma(0, 100, 0.1, 0.5) == 0.0        # degenerert spot → 0


# --- compute_snapshot ---
def test_compute_snapshot_call_positive_put_negative():
    sc = compute_snapshot([_c("BTC-02MAR26-65000-C")], 65000, NOW)
    assert sc["net_gex"] > 0 and abs(sc["gamma_center"] - 65000) < 1
    sp = compute_snapshot([_c("BTC-02MAR26-65000-P")], 65000, NOW)
    assert sp["net_gex"] < 0


def test_compute_snapshot_center_between_strikes():
    cs = [_c("BTC-02MAR26-60000-C"), _c("BTC-02MAR26-70000-C")]
    snap = compute_snapshot(cs, 65000, NOW)
    assert 60000 < snap["gamma_center"] < 70000


def test_compute_snapshot_skips_bad_and_empty():
    # Uparsbart navn + null-OI hoppes; tomt → None.
    assert compute_snapshot([_c("RUBBISH", oi=0)], 65000, NOW) is None
    assert compute_snapshot([], 65000, NOW) is None


# --- gamma_regime-driver ---
@pytest.fixture
def conn(tmp_path):
    with store.connect(tmp_path / "g.db") as c:
        store.init_db(c)
        yield c


def _put(conn, inst, dte, spot, net_gex, center):
    conn.execute("INSERT INTO gamma(instrument,date,spot,net_gex,gamma_center) VALUES (?,?,?,?,?)",
                 (inst, dte, spot, net_gex, center))


def test_gamma_regime_long_gamma_pin_above_is_bullish(conn):
    _put(conn, "btc", "2026-06-15", 65000.0, 5.0, 68000.0)   # magnet over spot
    res = gamma_regime(ScoreContext(conn, as_of="2026-06-16"), {"instrument": "btc"})
    assert res.ok and res.score > 0.3


def test_gamma_regime_short_gamma_is_zero(conn):
    _put(conn, "btc", "2026-06-15", 65000.0, -5.0, 68000.0)  # forsterkende → ingen pin
    res = gamma_regime(ScoreContext(conn, as_of="2026-06-16"), {"instrument": "btc"})
    assert res.ok and res.score == 0.0


def test_gamma_regime_stale_snapshot_misses(conn):
    _put(conn, "btc", "2026-06-01", 65000.0, 5.0, 68000.0)   # 15 dager gammelt
    res = gamma_regime(ScoreContext(conn, as_of="2026-06-16"),
                       {"instrument": "btc", "max_age_days": 5})
    assert not res.ok


def test_gamma_regime_lookahead_safe(conn):
    _put(conn, "btc", "2026-06-20", 65000.0, 5.0, 68000.0)   # FRAMTIDIG snapshot
    res = gamma_regime(ScoreContext(conn, as_of="2026-06-16"), {"instrument": "btc"})
    assert not res.ok                                         # ser ikke framtiden


def test_gamma_regime_no_data_misses(conn):
    assert not gamma_regime(ScoreContext(conn, as_of="2026-06-16"), {"instrument": "btc"}).ok
