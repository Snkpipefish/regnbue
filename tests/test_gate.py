"""Fase 4: look-ahead-vern (audit V4) + base-rate-gate-logikk.

Disse testene må være grønne FØR base-rate stoles på.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from setups import gate, store
from setups.outcomes import Bars, PanelRow, build_panel, triple_barrier


def _days(n: int, start="2020-01-01") -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


# ---------- triple-barrier / look-ahead ----------
def test_triple_barrier_long_tp_then_sl():
    dates = _days(10)
    closes = [100] * 10
    highs = [100, 101, 125, 100, 100, 100, 100, 100, 100, 100]  # TP-treff dag 2
    lows = [100] * 10
    bars = Bars(dates, highs, lows, closes)
    label, r = triple_barrier(bars, 0, "LONG", sl_dist=10, tp_dist=20, horizon=5, rr=2.0)
    assert label == "TP" and r == 2.0


def test_triple_barrier_sl_first_when_ambiguous():
    dates = _days(10)
    closes = [100] * 10
    # Samme bar treffer både SL (lo=85) og TP (hi=125): konservativt = SL.
    highs = [100, 125, 100, 100, 100, 100, 100, 100, 100, 100]
    lows = [100, 85, 100, 100, 100, 100, 100, 100, 100, 100]
    bars = Bars(dates, highs, lows, closes)
    label, r = triple_barrier(bars, 0, "LONG", sl_dist=10, tp_dist=20, horizon=5, rr=2.0)
    assert label == "SL" and r == -1.0


def test_triple_barrier_ignores_moves_after_horizon():
    # Look-ahead-bevis: en enorm spike ETTER horisonten må IKKE påvirke utfallet.
    dates = _days(20)
    closes = [100] * 20
    highs = [100] * 20
    lows = [100] * 20
    highs[10] = 130  # spike utenfor horizon=5 fra inngang ved i=0
    bars = Bars(dates, highs, lows, closes)
    label, r = triple_barrier(bars, 0, "LONG", sl_dist=10, tp_dist=20, horizon=5, rr=2.0)
    assert label == "TIME"  # spiken dag 10 er usynlig for et 5-dagers vindu


def test_panel_excludes_future_and_is_as_of_safe(tmp_path):
    # Flat prishistorikk + sen spike. Tidlige rader skal ikke "se" spiken.
    dates = _days(120)
    closes = [100.0] * 120
    closes[118] = 500.0  # sen spike
    with store.connect(tmp_path / "p.db") as conn:
        store.init_db(conn)
        for d, c in zip(dates, closes, strict=True):
            # Liten intrabar-range så ATR > 0 (ellers droppes alle beslutningsdatoer).
            conn.execute(
                "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
                ("GOLD", "D1", f"{d}T00:00:00Z", c, c + 1, c - 1, c),
            )
        fp = {"id": "Gold", "ticker": "GOLD",
              "drivers": [{"name": "price_vs_sma", "weight": 1.0,
                           "params": {"symbol": "GOLD", "window": 10}}]}
        panel = build_panel(conn, fp, horizon=5, min_history=20, step=1)

    # Ingen paneldato innenfor horizon av siste bar.
    assert max(r.date for r in panel.rows) <= dates[120 - 5 - 1]
    # Rader FØR spiken så bare flat pris → score ~0 (ikke påvirket av framtidig spike).
    early = [r for r in panel.rows if r.date < dates[100]]
    assert early and all(abs(r.vector["price_vs_sma"]) < 0.05 for r in early)


# ---------- gate-logikk ----------
def _rows(n, hit, r_value, direction="LONG", score=0.5):
    return [PanelRow(date=f"2020-01-{i+1:02d}", vector={"d": score}, direction=direction,
                     outcome_r=r_value, hit=hit, score=score) for i in range(n)]


def test_gate_rejects_too_few_neighbors():
    rows = _rows(10, hit=True, r_value=2.0)
    br = gate.evaluate(rows, 0.5, "LONG", min_effective_n=30)
    assert not br.passes and "for få" in br.reason
    assert br.n == 10


def test_gate_accepts_strong_evidence():
    # 40 analoger, 85% hit → Wilson nedre grense godt over 55%, klart positiv expectancy.
    rows = (_rows(34, hit=True, r_value=2.0) + _rows(6, hit=False, r_value=-1.0))
    br = gate.evaluate(rows, 0.5, "LONG",
                       min_effective_n=30, min_hit_rate_pct=55, min_expectancy_r=0.3)
    assert br.passes and br.n == 40
    assert br.hit_rate == pytest.approx(0.85, abs=1e-6)
    assert br.hit_rate_ci[0] * 100 >= 55  # nedre CI-grense over terskel
    assert br.expectancy_r > 0.3


def test_gate_rejects_low_hit_rate():
    rows = (_rows(18, hit=True, r_value=1.0) + _rows(22, hit=False, r_value=-1.0))
    br = gate.evaluate(rows, 0.5, "LONG", min_effective_n=30, min_hit_rate_pct=55)
    assert not br.passes and "hit-rate" in br.reason


def test_gate_filters_by_score_band_and_direction():
    near = _rows(35, hit=True, r_value=2.0, score=0.50)
    far = _rows(35, hit=True, r_value=2.0, score=0.95)       # utenfor båndet
    wrong_dir = _rows(35, hit=True, r_value=2.0, direction="SHORT")
    rows = near + far + wrong_dir
    br = gate.evaluate(rows, 0.50, "LONG", band=0.1, min_effective_n=30)
    assert br.n == 35  # kun LONG-naboer i score-båndet teller


def test_wilson_bounds():
    lo, hi = gate._wilson(30, 30)
    assert 0.8 < lo <= 1.0 and hi == 1.0
    assert gate._wilson(0, 0) == (0.0, 0.0)


# ---------- effektiv n (overlappende forward-vinduer) ----------
def test_effective_n_collapses_overlapping_windows():
    # 40 analoger på påfølgende dager med horizon 30 → vinduene overlapper kraftig →
    # bare ~2 uavhengige blokker, ikke 40.
    dates = _days(40)
    assert gate._effective_n(dates, 30) == 2
    # Spredt med >=30 dagers mellomrom → hver er uavhengig.
    spread = [(date.fromisoformat("2020-01-01") + timedelta(days=40 * i)).isoformat()
              for i in range(5)]
    assert gate._effective_n(spread, 30) == 5


def test_gate_uses_effective_n_with_horizon():
    # 40 påfølgende dager består uten horisont (n_eff=n=40) men FALLER med horizon=30
    # fordi de overlappende vinduene bare gir ~2 uavhengige observasjoner.
    dates = _days(40)
    rows = [PanelRow(date=dates[i], vector={"d": 0.5}, direction="LONG",
                     outcome_r=2.0, hit=True, score=0.5) for i in range(40)]
    without = gate.evaluate(rows, 0.5, "LONG", min_effective_n=30)
    assert without.passes and without.n_eff == 40
    withh = gate.evaluate(rows, 0.5, "LONG", min_effective_n=30, horizon_days=30)
    assert not withh.passes and withh.n_eff == 2 and "uavhengige" in withh.reason
