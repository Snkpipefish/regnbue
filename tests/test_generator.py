"""Generator-fikser: SL-gulv (#5) + base-rate på setup-ens faktiske R:R via ScoredPanel (#1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from setups import store
from setups.generator import build_setup
from setups.outcomes import build_scored_panel, swap_cost_r


def _days(n: int, start="2022-01-01") -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _seed_uptrend(conn, symbol="GOLD", n=320):
    """Stigende pris med sagtann (ATR>0 + reelle swinger). Returnerer datoene."""
    dates = _days(n)
    for i, d in enumerate(dates):
        base = 100.0 + i * 0.2
        zig = 1.5 if i % 2 == 0 else -1.5
        close = base + zig
        high = max(close, base) + 0.8
        low = min(close, base) - 0.8
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            (symbol, "D1", f"{d}T00:00:00Z", base, high, low, close),
        )
    return dates


_FP = {
    "id": "Gold", "ticker": "GOLD",
    "drivers": [{"name": "price_vs_sma", "weight": 1.0,
                 "params": {"symbol": "GOLD", "window": 50}}],
    "grade_thresholds": {"A_plus": 0.55, "A": 0.40, "B": 0.25},
    "base_rate": {"horizon_days": 10, "min_effective_n": 30},
}


def test_scored_panel_shares_scoring_but_varies_rr(tmp_path):
    # Samme scoring (RR-uavhengig), ulik RR → ulike utfall. Beviser at base-raten kan
    # materialiseres med nettopp den R:R-en setup-en bruker (#1).
    with store.connect(tmp_path / "g.db") as conn:
        store.init_db(conn)
        _seed_uptrend(conn)
        sp = build_scored_panel(conn, _FP, horizon=10, min_history=60, step=1)
        tight = sp.outcomes(1.0, 2.0)
        wide = sp.outcomes(1.0, 6.0)

    assert len(tight.rows) == len(wide.rows) > 30
    # Score + retning er identiske (deler scoring); kun utfallene avhenger av RR.
    assert [r.score for r in tight.rows] == [r.score for r in wide.rows]
    assert [r.direction for r in tight.rows] == [r.direction for r in wide.rows]
    # Bredere TP → strengere å nå → ikke flere treff enn den smale.
    assert sum(r.hit for r in wide.rows) <= sum(r.hit for r in tight.rows)


def test_build_setup_enforces_sl_floor(tmp_path):
    # Uansett hvor nær nærmeste swing ligger, skal risikoen være >= sl_floor_atr * ATR (#5).
    with store.connect(tmp_path / "g.db") as conn:
        store.init_db(conn)
        dates = _seed_uptrend(conn)
        sp = build_scored_panel(conn, _FP, horizon=10, min_history=60, step=5)
        setup = build_setup(conn, _FP, dates[-1], sl_floor_atr=0.5, panel=sp)

    assert setup is not None
    risk = abs(setup.entry - setup.sl)
    assert risk >= 0.5 * setup.atr - 1e-9      # SL-gulvet håndhevet
    assert setup.rr > 0 and setup.base_rate is not None
    # Gaten kjørte på effektiv n (horisont sendt inn).
    assert setup.base_rate.n_eff <= setup.base_rate.n


def test_swap_cost_r_debit_credit_and_noop():
    # Debet (positiv cpd) → positiv kostnad i R; kreditt (negativ) → negativ; ingen swap → 0.
    assert swap_cost_r({"long_cost_pct_per_day": 0.001}, "LONG", 10, 100.0, 5.0) == \
        pytest.approx(0.001 * 100.0 * 10 / 5.0)            # 0.2 R
    assert swap_cost_r({"short_cost_pct_per_day": -0.001}, "SHORT", 10, 100.0, 5.0) < 0
    assert swap_cost_r(None, "LONG", 10, 100.0, 5.0) == 0.0
    assert swap_cost_r({"long_cost_pct_per_day": 0.001}, "LONG", 0, 100.0, 5.0) == 0.0


def test_swap_lowers_panel_expectancy(tmp_path):
    # Carry-kostnad (#10) trekkes fra hvert utfall pr holdetid → lavere expectancy, men
    # antall treff (hit) er uendret (swap flytter ikke barrierene).
    with store.connect(tmp_path / "g.db") as conn:
        store.init_db(conn)
        _seed_uptrend(conn)
        sp = build_scored_panel(conn, _FP, horizon=10, min_history=60, step=1)
        base = sp.outcomes(1.0, 2.0)
        sp.swap = {"long_cost_pct_per_day": 0.003, "short_cost_pct_per_day": 0.003}
        costed = sp.outcomes(1.0, 2.0)

    assert len(base.rows) == len(costed.rows) > 30
    base_exp = sum(r.outcome_r for r in base.rows) / len(base.rows)
    costed_exp = sum(r.outcome_r for r in costed.rows) / len(costed.rows)
    assert costed_exp < base_exp                          # carry reduserer expectancy
    assert sum(r.hit for r in base.rows) == sum(r.hit for r in costed.rows)
