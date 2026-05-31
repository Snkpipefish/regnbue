"""Fase 3: logiske tester for scoring (syntetiske data → forventet score/grade)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from setups import store
from setups.score.context import ScoreContext
from setups.score.drivers import (
    cot_spec_net_percentile,
    degree_days_anomaly,
    etf_flow,
    frost_anomaly,
    price_ratio,
    price_vs_sma,
    rainfall_anomaly,
    seasonal_anomaly,
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


def test_etf_flow_inflow_is_bullish(conn):
    # ETF-beholdning stiger jevnt → siste vindus-endring positiv → bullish (bull_when high).
    dates = _days(120)
    for i, d in enumerate(dates):
        conn.execute(
            "INSERT INTO etf_holdings(ticker,date,tonnes_in_trust) VALUES (?,?,?)",
            ("gld", d, 800.0 + i * 2.0),  # monoton inn-flyt
        )
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = etf_flow(ctx, {"ticker": "gld", "horizon_days": 63, "bull_when": "high"})
    assert res.ok and res.score > 0.0


def test_etf_flow_excludes_future(conn):
    # Beholdning flat; en framtidig dag spretter opp. as_of FØR den → ikke bullish av spretten.
    dates = _days(120)
    for i, d in enumerate(dates):
        val = 800.0 if i < 119 else 1200.0
        conn.execute(
            "INSERT INTO etf_holdings(ticker,date,tonnes_in_trust) VALUES (?,?,?)",
            ("gld", d, val),
        )
    ctx = ScoreContext(conn, as_of=dates[100])  # ser ikke sluttspretten
    res = etf_flow(ctx, {"ticker": "gld", "horizon_days": 63, "bull_when": "high"})
    assert res.ok and abs(res.score) < 0.05


def _seed_seasonal_tmin(conn, region, years=5, start="2018-01-01"):
    """Daglig tmin med austral sesong-syklus (kaldest ~juli). Returnerer dato-liste."""
    import math as _m
    d0 = date.fromisoformat(start)
    dates = []
    for i in range(365 * years):
        d = d0 + timedelta(days=i)
        doy = d.timetuple().tm_yday
        tmin = 12.5 - 5.5 * _m.cos(2 * _m.pi * (doy - 196) / 365)  # ~7°C vinter, ~18°C sommer
        conn.execute(
            "INSERT OR REPLACE INTO weather(region,date,tmin) VALUES (?,?,?)",
            (region, d.isoformat(), round(tmin, 2)),
        )
        dates.append(d.isoformat())
    return dates


def test_frost_anomaly_cold_winter_is_bullish(conn):
    dates = _seed_seasonal_tmin(conn, "brazil_sul_minas")
    # Sett en anomalt kald natt (3°C) i midten av juli siste år — under abs-gate + sterkt negativ z.
    cold_day = "2022-07-15"
    conn.execute("INSERT OR REPLACE INTO weather(region,date,tmin) VALUES (?,?,?)",
                 ("brazil_sul_minas", cold_day, 3.0))
    ctx = ScoreContext(conn, as_of=cold_day)
    res = frost_anomaly(ctx, {"region": "brazil_sul_minas", "window_days": 10})
    assert res.ok and res.score > 0.3  # reell frost → bullish
    assert cold_day in dates  # innenfor den seedede perioden


def test_frost_anomaly_summer_coolspell_gated_to_zero(conn):
    _seed_seasonal_tmin(conn, "brazil_sul_minas")
    # Sommer-kjøling (14°C i januar): anomalt lavt for sesongen MEN over abs-gate (ingen frost).
    cool_day = "2022-01-15"
    conn.execute("INSERT OR REPLACE INTO weather(region,date,tmin) VALUES (?,?,?)",
                 ("brazil_sul_minas", cool_day, 14.0))
    ctx = ScoreContext(conn, as_of=cool_day)
    res = frost_anomaly(ctx, {"region": "brazil_sul_minas", "window_days": 10})
    assert res.ok and res.score == 0.0  # abs-gate hindrer falsk sommer-utslag


def test_price_ratio_low_is_bullish(conn):
    # Pt/Au-forhold synker til historisk bunn; bull_when low → mean-reversion bullish.
    dates = _days(60)
    for i, d in enumerate(dates):
        au = 1000.0  # gull flat
        pt = 900.0 - i * 5.0  # platina faller → ratio synker til bunn
        for sym, px in (("PLATINUM", pt), ("GOLD", au)):
            conn.execute(
                "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
                (sym, "D1", f"{d}T00:00:00Z", px, px, px, px),
            )
    ctx = ScoreContext(conn, as_of=dates[-1])
    res = price_ratio(ctx, {"numerator": "PLATINUM", "denominator": "GOLD", "bull_when": "low"})
    assert res.ok and res.score > 0.5  # ratio på bunn + bull_when low → bullish


def test_seasonal_anomaly_above_norm_is_bearish(conn):
    # Lager med sesong-syklus; siste verdi langt OVER samme-uke-norm → bull_when low → bearish.
    import math as _m
    d0 = date.fromisoformat("2018-01-01")
    for i in range(365 * 5):
        d = d0 + timedelta(days=i)
        doy = d.timetuple().tm_yday
        base = 400000 + 30000 * _m.sin(2 * _m.pi * doy / 365)
        val = base + (80000 if i == 365 * 5 - 1 else 0)  # siste dag: kraftig over norm
        conn.execute("INSERT OR REPLACE INTO macro_series VALUES (?,?,?)",
                     ("WCESTUS1", d.isoformat(), val))
    last = (d0 + timedelta(days=365 * 5 - 1)).isoformat()
    ctx = ScoreContext(conn, as_of=last)
    res = seasonal_anomaly(ctx, {"series": "WCESTUS1", "bull_when": "low"})
    assert res.ok and res.score < -0.3  # over sesong-norm + bull_when low → bearish


def test_degree_days_anomaly_extreme_cold_is_bullish(conn):
    # Vinter-temp-syklus; en nylig ekstrem kuldeperiode → høy degree-days → bullish (high).
    import math as _m
    d0 = date.fromisoformat("2018-01-01")
    n = 365 * 5
    for i in range(n):
        d = d0 + timedelta(days=i)
        doy = d.timetuple().tm_yday
        tmean = 12.0 - 12.0 * _m.cos(2 * _m.pi * (doy - 196) / 365)  # nordlig: kaldt ~jan
        if i >= n - 14:
            tmean -= 12.0  # siste 2 uker: kraftig kuldebølge
        conn.execute("INSERT OR REPLACE INTO weather(region,date,tmax,tmin) VALUES (?,?,?,?)",
                     ("us_gas_demand", d.isoformat(), tmean + 3, tmean - 3))
    last = (d0 + timedelta(days=n - 1)).isoformat()
    ctx = ScoreContext(conn, as_of=last)
    res = degree_days_anomaly(
        ctx, {"region": "us_gas_demand", "window_days": 14, "comfort_base_c": 18.0})
    assert res.ok and res.score > 0.3  # ekstrem kulde = etterspørsel = bullish


def _seed_drought_precip(conn, region):
    """Daglig nedbør (normal ~6/dag); siste 30 dager helt tørre. Returnerer slutt-dato."""
    d0 = date.fromisoformat("2018-01-01")
    n = 365 * 5
    last = d0
    for i in range(n):
        d = d0 + timedelta(days=i)
        precip = 0.0 if i >= n - 30 else 6.0  # siste måned: tørke
        conn.execute("INSERT OR REPLACE INTO weather(region,date,precip) VALUES (?,?,?)",
                     (region, d.isoformat(), precip))
        last = d
    return last.isoformat()


def test_rainfall_anomaly_drought_in_season_fires(conn):
    last = _seed_drought_precip(conn, "us_cornbelt")
    m = int(last[5:7])  # sluttmåneden = aktiv → tørke fyrer
    ctx = ScoreContext(conn, as_of=last)
    res = rainfall_anomaly(ctx, {"region": "us_cornbelt", "window_days": 30, "active_months": [m]})
    assert res.ok and res.score > 0.0  # tørke i vekstsesong → bullish


def test_rainfall_anomaly_gated_out_of_season(conn):
    last = _seed_drought_precip(conn, "us_cornbelt")
    m = int(last[5:7])
    other = (m % 12) + 1  # en annen måned enn slutt-måneden
    ctx = ScoreContext(conn, as_of=last)
    res = rainfall_anomaly(ctx, {"region": "us_cornbelt", "window_days": 30,
                                 "active_months": [other]})
    assert res.ok and res.score == 0.0  # utenfor sesong → ingen signal


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
