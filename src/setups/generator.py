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
from setups.outcomes import atr_series, build_panel, load_bars
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
                panel: object | None = None) -> Setup | None:
    """Bygg setup for `as_of`. Returnerer None hvis ingen prisdata/ATR."""
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

    if direction == "LONG":
        ups = [lv for lv in sh + rounds if lv > entry + 0.3 * atr]
        downs = [lv for lv in sl_levels + rounds if lv < entry]
        tp = min(ups) if ups else entry + tp_atr * atr
        sl = (max(downs) - sl_buffer_atr * atr) if downs else entry - sl_atr * atr
        risk, reward = entry - sl, tp - entry
    else:
        downs = [lv for lv in sl_levels + rounds if lv < entry - 0.3 * atr]
        ups = [lv for lv in sh + rounds if lv > entry]
        tp = max(downs) if downs else entry - tp_atr * atr
        sl = (min(ups) + sl_buffer_atr * atr) if ups else entry + sl_atr * atr
        risk, reward = sl - entry, entry - tp

    rr = reward / risk if risk > 0 else 0.0

    # Base-rate: bygg panel (kan gjenbrukes/caches utenfra) med nominell R:R.
    if panel is None:
        panel = build_panel(conn, fingerprint, sl_atr=sl_atr, tp_atr=tp_atr,
                            horizon=horizon, oos_start=br_cfg.get("oos_start"))
    current_vector = {d.name: d.score for d in res.drivers if d.ok}
    base_rate = gate.evaluate(
        panel.train() if hasattr(panel, "train") else panel,
        current_vector, direction,
        similarity=br_cfg.get("similarity", 0.15),
        min_effective_n=br_cfg.get("min_effective_n", 30),
        min_hit_rate_pct=br_cfg.get("min_hit_rate_pct", 55.0),
        min_expectancy_r=br_cfg.get("min_expectancy_r", 0.3),
    )

    reasons = []
    if res.grade.grade == "NONE":
        reasons.append("ingen grade (for svakt signal)")
    if rr < rr_floor:
        reasons.append(f"R:R {rr:.2f} < {rr_floor}")
    if not base_rate.passes:
        reasons.append(f"base-rate: {base_rate.reason}")
    published = not reasons

    return Setup(
        instrument=fingerprint.get("id", ticker), ticker=ticker, as_of=as_of,
        direction=direction, grade=res.grade.grade, score=res.score,
        entry=round(entry, 6), sl=round(sl, 6), tp=round(tp, 6), rr=round(rr, 3),
        atr=round(atr, 6), base_rate=base_rate, published=published,
        reject_reason="; ".join(reasons), drivers=drivers,
    )
