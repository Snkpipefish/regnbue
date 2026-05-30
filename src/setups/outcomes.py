"""Outcomes + historisk panel for base-rate (regnes ferskt, look-ahead-trygt).

Alt regnes på Skillings NIVÅ-feed (`prices`). For hver historisk beslutningsdato `d`:
  * driver-score-vektor beregnes med as-of=`d` (ser kun data t.o.m. `d`),
  * forward-utfallet (triple-barrier) regnes KUN på barer i (d, d+horizon].

Disse to vinduene overlapper aldri framtid forbi `d+horizon` — det er look-ahead-vernet
som `tests/test_gate.py` beviser (audit V4). OOS-holdout (siste år) merkes pr rad.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from setups.score.context import ScoreContext
from setups.score.engine import score_instrument


@dataclass
class Bars:
    dates: list[str]
    highs: list[float]
    lows: list[float]
    closes: list[float]


@dataclass
class PanelRow:
    date: str
    vector: dict[str, float]
    direction: str        # LONG | SHORT (implisert av score-fortegn)
    outcome_r: float      # realisert resultat i R (TP=+rr, SL=-1, ellers delvis)
    hit: bool             # nådde TP før SL innen horisont
    oos: bool = False     # i out-of-sample-holdout


@dataclass
class Panel:
    instrument: str
    rows: list[PanelRow] = field(default_factory=list)

    def train(self) -> list[PanelRow]:
        return [r for r in self.rows if not r.oos]

    def oos(self) -> list[PanelRow]:
        return [r for r in self.rows if r.oos]


def load_bars(conn: sqlite3.Connection, symbol: str, tf: str = "D1") -> Bars:
    rows = conn.execute(
        "SELECT substr(ts,1,10), high, low, close FROM prices "
        "WHERE symbol=? AND tf=? ORDER BY ts",
        (symbol, tf),
    ).fetchall()
    return Bars([r[0] for r in rows], [r[1] for r in rows],
                [r[2] for r in rows], [r[3] for r in rows])


def atr_series(bars: Bars, window: int = 14) -> list[float | None]:
    """Wilder-aktig ATR (enkelt glidende snitt av true range). None før nok historikk."""
    tr: list[float] = []
    for i in range(len(bars.closes)):
        if i == 0:
            tr.append(bars.highs[i] - bars.lows[i])
            continue
        pc = bars.closes[i - 1]
        tr.append(max(bars.highs[i] - bars.lows[i], abs(bars.highs[i] - pc),
                      abs(bars.lows[i] - pc)))
    out: list[float | None] = [None] * len(tr)
    for i in range(len(tr)):
        if i + 1 >= window:
            out[i] = sum(tr[i + 1 - window:i + 1]) / window
    return out


def triple_barrier(bars: Bars, i: int, direction: str, sl_dist: float, tp_dist: float,
                   horizon: int, rr: float) -> tuple[str, float]:
    """Utfall fra inngang ved bar `i` (close) over de neste `horizon` barene.

    Konservativ ved tvetydig bar: sjekker SL før TP, så et 'både og'-treff teller som SL.
    Returnerer (label, R). label ∈ {TP, SL, TIME}.
    """
    entry = bars.closes[i]
    last = min(i + horizon, len(bars.closes) - 1)
    for j in range(i + 1, last + 1):
        hi, lo = bars.highs[j], bars.lows[j]
        if direction == "LONG":
            if lo <= entry - sl_dist:
                return "SL", -1.0
            if hi >= entry + tp_dist:
                return "TP", rr
        else:  # SHORT
            if hi >= entry + sl_dist:
                return "SL", -1.0
            if lo <= entry - tp_dist:
                return "TP", rr
    # Tidsutløp: delvis resultat i R.
    close = bars.closes[last]
    move = (close - entry) if direction == "LONG" else (entry - close)
    return "TIME", move / sl_dist if sl_dist else 0.0


def build_panel(conn: sqlite3.Connection, fingerprint: dict, *,
                sl_atr: float = 1.0, tp_atr: float = 2.0, horizon: int = 30,
                atr_window: int = 14, oos_start: str | None = None,
                step: int = 1, min_history: int = 220) -> Panel:
    """Bygg look-ahead-trygt panel av (score-vektor, utfall) over historikken."""
    symbol = fingerprint["ticker"]
    bars = load_bars(conn, symbol)
    atr = atr_series(bars, atr_window)
    rr = tp_atr / sl_atr
    panel = Panel(instrument=fingerprint.get("id", symbol))

    last_decision = len(bars.closes) - horizon - 1
    for i in range(min_history, last_decision + 1, step):
        a = atr[i]
        if a is None or a <= 0:
            continue
        d = bars.dates[i]
        ctx = ScoreContext(conn, as_of=d)
        res = score_instrument(ctx, fingerprint)
        # Krev at alle drivere har data → konsistent vektor for likhetsmål.
        if any(not dr.ok for dr in res.drivers):
            continue
        vector = {dr.name: dr.score for dr in res.drivers}
        direction = "LONG" if res.score >= 0 else "SHORT"
        label, outcome_r = triple_barrier(bars, i, direction, sl_atr * a, tp_atr * a,
                                           horizon, rr)
        panel.rows.append(PanelRow(
            date=d, vector=vector, direction=direction, outcome_r=outcome_r,
            hit=(label == "TP"), oos=(oos_start is not None and d >= oos_start),
        ))
    return panel
