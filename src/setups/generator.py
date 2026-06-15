"""Setup-generator: reelle nivåer på Skilling-feeden + base-rate-gate.

Nivåene (entry/SL/TP) regnes ALLTID på `prices` (Skilling/cTrader) — ett koordinatsystem
(K3/§5b). Setup bygges asymmetrisk: entry ved siste close, SL bak nærmeste beskyttende
swing (buffer×ATR), TP ved neste reelle nivå (swing/rundt tall). Publiseres kun hvis grade
holder, R:R >= floor OG base-rate-gaten godkjenner.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from setups import gate
from setups.outcomes import (
    ScoredPanel,
    atr_series,
    build_scored_panel,
    load_bars,
)
from setups.score.context import ScoreContext
from setups.score.engine import score_instrument


@dataclass
class Setup:
    instrument: str
    ticker: str
    as_of: str
    direction: str
    grade: str
    score: float
    entry: float
    sl: float
    tp: float
    rr: float
    atr: float
    base_rate: gate.BaseRate | None
    published: bool
    reject_reason: str = ""
    drivers: list[dict] = field(default_factory=list)
    # Forward, sti-avhengig base-rate fra den kalibrerte scenario-fordelingen (#12). Vises
    # ved siden av den historiske analog-base-raten; gater ikke med mindre fingerprintet ber.
    scenario: dict | None = None


def _fractal_levels(highs, lows, lo_idx, hi_idx, wing: int = 3):
    """Swing-høyder/lavpunkter (fraktaler) i [lo_idx, hi_idx)."""
    sh, sl = [], []
    for i in range(lo_idx + wing, hi_idx - wing):
        window_h = highs[i - wing:i + wing + 1]
        window_l = lows[i - wing:i + wing + 1]
        if highs[i] == max(window_h):
            sh.append(highs[i])
        if lows[i] == min(window_l):
            sl.append(lows[i])
    return sh, sl


def _scenario_rate(closes: list[float], direction: str, entry: float, risk: float,
                   reward: float, horizon: int, n_paths: int = 2000,
                   swap: dict | None = None) -> dict | None:
    """Forward sti-avhengig base-rate (P(TP før SL) + expectancy) fra FHS-fordelingen (#12).

    Returnerer summary-dict eller None hvis for kort/ugyldig historikk. Importeres lokalt så
    `numpy`/scenario-modulen ikke kreves for ren scoring/test uten denne stien.
    """
    if entry <= 0 or risk <= 0 or reward <= 0 or len(closes) < 80:
        return None
    try:
        import numpy as np

        from setups.scenario import fhs_barrier_prob, log_returns
        rets = log_returns(np.asarray(closes, dtype=float))
        rets = rets[np.isfinite(rets)]
        if len(rets) < 60:
            return None
        bp = fhs_barrier_prob(rets, len(rets) - 1, direction=direction,
                              tp_ret=reward / entry, sl_ret=risk / entry,
                              horizon=horizon, n_paths=n_paths, swap=swap)
        return bp.summary()
    except Exception:
        return None


def _round_levels(price: float, n: int = 3) -> list[float]:
    """Nærliggende runde tall (psykologiske nivåer), skalert til prisstørrelsen."""
    import math
    if price <= 0:
        return []
    step = 10 ** (math.floor(math.log10(price)) - 1)  # ~1% av prisen
    base = round(price / step) * step
    return [round(base + k * step, 10) for k in range(-n, n + 1)]


def build_setup(conn: sqlite3.Connection, fingerprint: dict, as_of: str, *,
                level_lookback: int = 180, sl_atr: float = 1.0, tp_atr: float = 2.0,
                rr_floor: float = 1.5, sl_buffer_atr: float = 0.25,
                sl_floor_atr: float = 0.5,
                panel: object | None = None) -> Setup | None:
    """Bygg setup for `as_of`. Returnerer None hvis ingen prisdata/ATR.

    `sl_floor_atr` håndhever en minste SL-avstand (i ATR) så en swing rett ved entry ikke
    gir en mikroskopisk risiko og en kunstig høy R:R som stoppes ut umiddelbart i praksis.
    """
    ticker = fingerprint["ticker"]
    br_cfg = fingerprint.get("base_rate", {})
    horizon = br_cfg.get("horizon_days", 30)

    ctx = ScoreContext(conn, as_of=as_of)
    res = score_instrument(ctx, fingerprint)
    bars = load_bars(conn, ticker)
    # Indeks for siste bar t.o.m. as_of.
    hi_idx = next((j for j, d in enumerate(bars.dates) if d > as_of), len(bars.dates))
    if hi_idx < level_lookback:
        return None
    atr = atr_series(bars, br_cfg.get("atr_window", 14))[hi_idx - 1]
    if not atr or atr <= 0:
        return None

    entry = bars.closes[hi_idx - 1]
    direction = "LONG" if res.score >= 0 else "SHORT"
    drivers = [{"name": d.name, "ok": d.ok, "score": d.score, "detail": d.detail}
               for d in res.drivers]

    lo_idx = max(0, hi_idx - level_lookback)
    sh, sl_levels = _fractal_levels(bars.highs, bars.lows, lo_idx, hi_idx)
    rounds = _round_levels(entry)

    min_sl = sl_floor_atr * atr
    if direction == "LONG":
        ups = [lv for lv in sh + rounds if lv > entry + 0.3 * atr]
        downs = [lv for lv in sl_levels + rounds if lv < entry]
        tp = min(ups) if ups else entry + tp_atr * atr
        sl = (max(downs) - sl_buffer_atr * atr) if downs else entry - sl_atr * atr
        sl = min(sl, entry - min_sl)  # håndhev minste SL-avstand
        risk, reward = entry - sl, tp - entry
    else:
        downs = [lv for lv in sl_levels + rounds if lv < entry - 0.3 * atr]
        ups = [lv for lv in sh + rounds if lv > entry]
        tp = max(downs) if downs else entry - tp_atr * atr
        sl = (min(ups) + sl_buffer_atr * atr) if ups else entry + sl_atr * atr
        sl = max(sl, entry + min_sl)  # håndhev minste SL-avstand
        risk, reward = sl - entry, entry - tp

    rr = reward / risk if risk > 0 else 0.0

    # Base-rate: materialiser utfall med setup-ens FAKTISKE SL/TP-avstander (i ATR), så
    # gaten validerer nettopp denne traden — ikke en fast 1×/2×ATR-proxy. Den dyre scoringen
    # gjenbrukes fra et forhåndsbygd ScoredPanel når det sendes inn (run.py bygger det én gang).
    sl_atr_eff = risk / atr if atr else sl_atr
    tp_atr_eff = reward / atr if atr else tp_atr
    if isinstance(panel, ScoredPanel):
        scored = panel
    else:
        scored = build_scored_panel(conn, fingerprint, horizon=horizon,
                                    oos_start=br_cfg.get("oos_start"))
    outcomes_panel = scored.outcomes(sl_atr_eff, tp_atr_eff)
    # #7: sammensetnings-bevisst matching (opt-in) — kun analoger med samme tilgjengelige
    # drivere, så renormalisert score er sammenlignbar. Av som standard (låste terskler).
    coverage = (frozenset(d.name for d in res.drivers if d.ok)
                if br_cfg.get("match_coverage") else None)
    base_rate = gate.evaluate(
        outcomes_panel.train(),
        res.score, direction,
        band=br_cfg.get("band", 0.1),
        min_effective_n=br_cfg.get("min_effective_n", 30),
        min_hit_rate_pct=br_cfg.get("min_hit_rate_pct", 55.0),
        min_expectancy_r=br_cfg.get("min_expectancy_r", 0.3),
        coverage=coverage,
        horizon_days=horizon,
    )

    # Forward, kalibrert base-rate fra scenario-fordelingen — alltid vist, gater kun ved opt-in.
    scenario = _scenario_rate(bars.closes[:hi_idx], direction, entry, risk, reward, horizon,
                              swap=fingerprint.get("swap"))

    reasons = []
    if res.grade.grade == "NONE":
        reasons.append("ingen grade (for svakt signal)")
    if rr < rr_floor:
        reasons.append(f"R:R {rr:.2f} < {rr_floor}")
    # Hvilken motor gater publiseringen: historiske analoger (standard) eller scenario-baner.
    engine = br_cfg.get("engine", "analog")
    if engine == "scenario":
        min_prob = br_cfg.get("min_prob_tp", 0.5)
        min_exp = br_cfg.get("min_expectancy_r", 0.3)
        if scenario is None:
            reasons.append("scenario: utilstrekkelig historikk")
        else:
            if scenario["prob_tp"] < min_prob:
                reasons.append(f"scenario: P(TP)={scenario['prob_tp']:.0%} < {min_prob:.0%}")
            if scenario["expectancy_r"] < min_exp:
                reasons.append(
                    f"scenario: expectancy {scenario['expectancy_r']:+.2f}R < {min_exp:.2f}R")
            if scenario["expectancy_ci"][0] <= 0:
                reasons.append(
                    f"scenario: expectancy CI inkluderer ≤0 ({scenario['expectancy_ci'][0]:+.2f}R)")
    elif not base_rate.passes:
        reasons.append(f"base-rate: {base_rate.reason}")
    published = not reasons

    return Setup(
        instrument=fingerprint.get("id", ticker), ticker=ticker, as_of=as_of,
        direction=direction, grade=res.grade.grade, score=res.score,
        entry=round(entry, 6), sl=round(sl, 6), tp=round(tp, 6), rr=round(rr, 3),
        atr=round(atr, 6), base_rate=base_rate, published=published,
        reject_reason="; ".join(reasons), drivers=drivers, scenario=scenario,
    )
