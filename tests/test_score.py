"""Fase 3: logiske tester for scoring (syntetiske data → forventet score/grade)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from setups import store
from setups.score.context import ScoreContext
from setups.score.drivers import (
    cot_spec_net_percentile,
    price_vs_sma,
    series_spread_percentile,
)
from setups.score.engine import score_instrument
from setups.score.grade import grade_score


def _days(n: int, start="2024-01-01") -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


@pytest.fixture
def conn(tmp_path):
    with store.connect(tmp_path / "s.db") as c:
        store.init_db(c)
        yield c


def test_price_vs_sma_bullish_when_above(conn):
    dates = _days(6)
    closes = [10, 10, 10, 10, 10, 12]  # siste godt over snittet
    for d, c in zip(dates, closes, strict=True):
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            ("GOLD", "D1", f"{d}T00:00:00Z", c, c, c, c),
        )
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = price_vs_sma(ctx, {"symbol": "GOLD", "window": 5})
    assert res.ok and res.score > 0.5


def test_as_of_excludes_future(conn):
    # Historikk flat på 10; en framtidig dag spretter til 50. as_of FØR den dagen.
    dates = _days(7)
    closes = [10, 10, 10, 10, 10, 10, 50]
    for d, c in zip(dates, closes, strict=True):
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            ("GOLD", "D1", f"{d}T00:00:00Z", c, c, c, c),
        )
    ctx = ScoreContext(conn, as_of=dates[5])  # ser ikke dag 7 (=50)
    res = price_vs_sma(ctx, {"symbol": "GOLD", "window": 5})
    # Siste synlige close = 10 = snittet → ~nøytral, IKKE bullish av framtids-spretten.
    assert abs(res.score) < 0.05


def test_cot_spec_net_percentile_extreme_long(conn):
    dates = _days(25)
    for i, d in enumerate(dates):
        conn.execute(
            "INSERT INTO cot_positions(market,report_date,report_type,long_spec,short_spec,"
            "open_interest) VALUES (?,?,?,?,?,?)",
            ("Gold", d, "disaggregated", 1000 + i * 100, 500, 5000),  # net stiger monotont
        )
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = cot_spec_net_percentile(ctx, {"market": "Gold", "lookback_weeks": 156,
                                         "bull_when": "high"})
    assert res.ok and res.score > 0.9  # høyeste net på hele lookback → p≈1


def test_spread_percentile_low_is_bullish(conn):
    # Realrente-proxy: DGS10 faller, T10YIE flat → spread synker til bunn-nivå.
    dates = _days(25)
    for i, d in enumerate(dates):
        conn.execute("INSERT INTO macro_series VALUES (?,?,?)", ("DGS10", d, 5.0 - i * 0.1))
        conn.execute("INSERT INTO macro_series VALUES (?,?,?)", ("T10YIE", d, 2.0))
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = series_spread_percentile(ctx, {"minuend": "DGS10", "subtrahend": "T10YIE",
                                         "lookback_days": 504, "bull_when": "low"})
    assert res.ok and res.score > 0.9  # spread på sitt laveste + bull_when low → bullish


def test_engine_weighted_aggregate_and_grade(conn):
    # To drivere med kjente scorer via syntetisk data:
    #  - price_vs_sma sterkt bullish (~+1), vekt 0.5
    #  - cot ekstrem long (~+1), vekt 0.5  → samlet ~+1 → grade A+, LONG
    dates = _days(25)
    for i, d in enumerate(dates):
        c = 10 if i < 24 else 14
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            ("GOLD", "D1", f"{d}T00:00:00Z", c, c, c, c),
        )
        conn.execute(
            "INSERT INTO cot_positions(market,report_date,report_type,long_spec,short_spec,"
            "open_interest) VALUES (?,?,?,?,?,?)",
            ("Gold", d, "disaggregated", 1000 + i * 100, 500, 5000),
        )
    fingerprint = {
        "id": "Gold", "ticker": "GOLD",
        "drivers": [
            {"name": "price_vs_sma", "weight": 0.5, "params": {"symbol": "GOLD", "window": 5}},
            {"name": "cot_spec_net_percentile", "weight": 0.5,
             "params": {"market": "Gold", "bull_when": "high"}},
        ],
        "grade_thresholds": {"A_plus": 0.55, "A": 0.40, "B": 0.25},
    }
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = score_instrument(ctx, fingerprint)
    assert res.score > 0.7
    assert res.grade.direction == "LONG"
    assert res.grade.grade == "A+"
    # Explain-trace bærer vekt + bidrag.
    trace = res.explain()
    assert all(d["weight"] == 0.5 for d in trace["drivers"])
    assert all(d["contribution"] is not None for d in trace["drivers"])


def test_engine_renormalizes_when_driver_missing(conn):
    # Kun price-driver har data; cot mangler → vekt re-normaliseres til price alene.
    dates = _days(6)
    for d, c in zip(dates, [10, 10, 10, 10, 10, 12], strict=True):
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            ("GOLD", "D1", f"{d}T00:00:00Z", c, c, c, c),
        )
    fingerprint = {
        "id": "Gold", "ticker": "GOLD",
        "drivers": [
            {"name": "price_vs_sma", "weight": 0.4, "params": {"symbol": "GOLD", "window": 5}},
            {"name": "cot_spec_net_percentile", "weight": 0.6, "params": {"market": "Gold"}},
        ],
    }
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = score_instrument(ctx, fingerprint)
    missing = [d for d in res.drivers if not d.ok]
    assert len(missing) == 1 and missing[0].name == "cot_spec_net_percentile"
    # Samlet score = price-driverens score (re-normalisert), ikke uthulet av manglende cot.
    price_res = next(d for d in res.drivers if d.name == "price_vs_sma")
    assert res.score == pytest.approx(price_res.score, abs=1e-6)


def test_grade_thresholds():
    assert grade_score(0.6).grade == "A+"
    assert grade_score(0.45).grade == "A"
    assert grade_score(0.30).grade == "B"
    assert grade_score(0.10).direction == "NEUTRAL"
    assert grade_score(-0.6).direction == "SHORT"
