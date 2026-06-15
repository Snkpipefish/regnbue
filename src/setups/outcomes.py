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
    score: float = 0.0    # aggregert fingerprint-score (base-rate matcher på denne)
    oos: bool = False     # i out-of-sample-holdout


@dataclass
class Panel:
    instrument: str
    rows: list[PanelRow] = field(default_factory=list)

    def train(self) -> list[PanelRow]:
        return [r for r in self.rows if not r.oos]

    def oos(self) -> list[PanelRow]:
        return [r for r in self.rows if r.oos]


@dataclass
class ScoredRow:
    """RR-uavhengig del av en paneldato: score-vektor + ATR ved beslutnings-baren."""
    date: str
    bar_index: int
    score: float
    direction: str
    vector: dict[str, float]
    atr: float
    oos: bool = False


@dataclass
class ScoredPanel:
    """Scoringen (dyr, RR-uavhengig) skilt fra utfalls-barrieren (billig, RR-avhengig).

    Slik kan vi score historikken ÉN gang pr instrument og så materialisere base-rate-
    utfall med NØYAKTIG de SL/TP-avstandene den publiserte setup-en bruker (audit-fiks:
    før brukte panelet faste 1×/2×ATR mens setup-en hadde nivåbasert R:R → gaten validerte
    en annen trade enn den som ble publisert).
    """
    instrument: str
    bars: Bars
    horizon: int
    rows: list[ScoredRow] = field(default_factory=list)
    swap: dict | None = None   # {long_cost_pct_per_day, short_cost_pct_per_day} (#10)

    def outcomes(self, sl_atr: float, tp_atr: float) -> Panel:
        """Materialiser et Panel med triple-barrier-utfall for gitte ATR-multipler.

        Trekker carry/swap fra utfallet pr faktisk holdetid når `swap` er satt (#10).
        """
        rr = tp_atr / sl_atr if sl_atr else 0.0
        panel = Panel(instrument=self.instrument)
        for r in self.rows:
            sl_dist = sl_atr * r.atr
            label, outcome_r, held = triple_barrier(
                self.bars, r.bar_index, r.direction,
                sl_dist, tp_atr * r.atr, self.horizon, rr, return_held=True)
            outcome_r -= swap_cost_r(self.swap, r.direction, held,
                                     self.bars.closes[r.bar_index], sl_dist)
            panel.rows.append(PanelRow(
                date=r.date, vector=r.vector, direction=r.direction,
                outcome_r=outcome_r, hit=(label == "TP"), score=r.score, oos=r.oos))
        return panel


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
                   horizon: int, rr: float, *, return_held: bool = False):
    """Utfall fra inngang ved bar `i` (close) over de neste `horizon` barene.

    Konservativ ved tvetydig bar: sjekker SL før TP, så et 'både og'-treff teller som SL.
    Returnerer (label, R). Med `return_held=True`: (label, R, antall_barer_holdt) — brukt til
    å trekke inn carry/swap pr faktisk holdetid (#10). label ∈ {TP, SL, TIME}.
    """
    entry = bars.closes[i]
    last = min(i + horizon, len(bars.closes) - 1)
    for j in range(i + 1, last + 1):
        hi, lo = bars.highs[j], bars.lows[j]
        if direction == "LONG":
            if lo <= entry - sl_dist:
                return ("SL", -1.0, j - i) if return_held else ("SL", -1.0)
            if hi >= entry + tp_dist:
                return ("TP", rr, j - i) if return_held else ("TP", rr)
        else:  # SHORT
            if hi >= entry + sl_dist:
                return ("SL", -1.0, j - i) if return_held else ("SL", -1.0)
            if lo <= entry - tp_dist:
                return ("TP", rr, j - i) if return_held else ("TP", rr)
    # Tidsutløp: delvis resultat i R. close[last] ligger pr definisjon mellom barrierene
    # (begge ble sjekket t.o.m. `last`), så move/sl_dist er allerede innenfor (-1, +rr).
    close = bars.closes[last]
    move = (close - entry) if direction == "LONG" else (entry - close)
    r = move / sl_dist if sl_dist else 0.0
    return ("TIME", r, last - i) if return_held else ("TIME", r)


def swap_cost_r(swap: dict | None, direction: str, days_held: int,
                entry: float, sl_dist: float) -> float:
    """Carry/swap-kostnad over holdetiden, uttrykt i R (risiko-enheter).

    `swap`: {long_cost_pct_per_day, short_cost_pct_per_day} der POSITIV = daglig debet
    (du betaler) som andel av notional, NEGATIV = kreditt. Kostnaden i pris = cpd·entry·dager;
    i R deles på sl_dist. Skilling belaster swap daglig (§5b), så dette gjør expectancy ærlig.
    """
    if not swap or sl_dist <= 0 or entry <= 0 or days_held <= 0:
        return 0.0
    key = "long_cost_pct_per_day" if direction == "LONG" else "short_cost_pct_per_day"
    cpd = swap.get(key, 0.0)
    return cpd * entry * days_held / sl_dist


def build_scored_panel(conn: sqlite3.Connection, fingerprint: dict, *,
                       horizon: int = 30, atr_window: int = 14, oos_start: str | None = None,
                       step: int = 1, min_history: int = 220) -> ScoredPanel:
    """Score historikken look-ahead-trygt (RR-uavhengig). Den dyre delen — caches/gjenbrukes."""
    symbol = fingerprint["ticker"]
    bars = load_bars(conn, symbol)
    atr = atr_series(bars, atr_window)
    sp = ScoredPanel(instrument=fingerprint.get("id", symbol), bars=bars, horizon=horizon,
                     swap=fingerprint.get("swap"))

    last_decision = len(bars.closes) - horizon - 1
    for i in range(min_history, last_decision + 1, step):
        a = atr[i]
        if a is None or a <= 0:
            continue
        d = bars.dates[i]
        ctx = ScoreContext(conn, as_of=d)
        res = score_instrument(ctx, fingerprint)
        # Base-rate matcher på aggregert score (renormalisert over tilgjengelige drivere),
        # så vi krever bare at MINST én driver har data — ikke alle. (En grunn driver som
        # mangler historisk skal ikke utslette hele panelet.)
        if not any(dr.ok for dr in res.drivers):
            continue
        vector = {dr.name: dr.score for dr in res.drivers if dr.ok}
        sp.rows.append(ScoredRow(
            date=d, bar_index=i, score=res.score,
            direction="LONG" if res.score >= 0 else "SHORT", vector=vector, atr=a,
            oos=(oos_start is not None and d >= oos_start),
        ))
    return sp


def build_panel(conn: sqlite3.Connection, fingerprint: dict, *,
                sl_atr: float = 1.0, tp_atr: float = 2.0, horizon: int = 30,
                atr_window: int = 14, oos_start: str | None = None,
                step: int = 1, min_history: int = 220) -> Panel:
    """Bygg look-ahead-trygt panel av (score-vektor, utfall) for faste ATR-multipler.

    Tynn wrapper over `build_scored_panel(...).outcomes(...)` — beholdt for bakoverkompat
    (validate/tester). Generator-en bruker `build_scored_panel` direkte for å materialisere
    utfall med setup-ens egne SL/TP-avstander.
    """
    sp = build_scored_panel(conn, fingerprint, horizon=horizon, atr_window=atr_window,
                            oos_start=oos_start, step=step, min_history=min_history)
    return sp.outcomes(sl_atr, tp_atr)
