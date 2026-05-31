"""ScoreContext — as-of datatilgang mot datastoren.

ALT som leses er filtrert til ``dato <= as_of``. Dette er look-ahead-vernet som
base-rate-gaten (fase 4) hviler på: scoringen på en historisk dato ser kun data som
faktisk var tilgjengelig da. Datoer er ISO-strenger; leksikografisk sammenligning på
ISO-format = kronologisk.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from dataclasses import dataclass


@dataclass
class ScoreContext:
    conn: sqlite3.Connection
    as_of: str  # 'YYYY-MM-DD'

    # --- makro-serier ---
    def series(self, series_id: str) -> list[tuple[str, float]]:
        """(dato, verdi) stigende, kun t.o.m. as_of."""
        rows = self.conn.execute(
            "SELECT date, value FROM macro_series "
            "WHERE series_id=? AND date<=? AND value IS NOT NULL ORDER BY date",
            (series_id, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def spread_series(self, minuend: str, subtrahend: str) -> list[tuple[str, float]]:
        """minuend − subtrahend, der subtrahend forward-fylles på minuend-datoer.

        Håndterer ulik kadens (f.eks. daglig DGS10 mot månedlig OECD-rente).
        """
        a = self.series(minuend)
        b = self.series(subtrahend)
        if not a or not b:
            return []
        b_dates = [d for d, _ in b]
        b_vals = [v for _, v in b]
        out: list[tuple[str, float]] = []
        for d, av in a:
            i = bisect_right(b_dates, d) - 1  # siste subtrahend-obs på/ før d
            if i >= 0:
                out.append((d, av - b_vals[i]))
        return out

    # --- priser (NIVÅ-feed) ---
    def closes(self, symbol: str, tf: str = "D1") -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT ts, close FROM prices WHERE symbol=? AND tf=? AND substr(ts,1,10)<=? "
            "ORDER BY ts",
            (symbol, tf, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- ETF-beholdning (fysisk investerings-flyt) ---
    def etf_holdings(self, ticker: str) -> list[tuple[str, float]]:
        """(dato, tonnes_in_trust) stigende, kun t.o.m. as_of."""
        rows = self.conn.execute(
            "SELECT date, tonnes_in_trust FROM etf_holdings "
            "WHERE ticker=? AND date<=? AND tonnes_in_trust IS NOT NULL ORDER BY date",
            (ticker, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- vær (nedbør) ---
    def weather_precip(self, region: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT date, precip FROM weather WHERE region=? AND date<=? AND precip IS NOT NULL "
            "ORDER BY date",
            (region, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- COT-posisjonering ---
    def cot(self, market: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT report_date, long_spec, short_spec, long_comm, short_comm, open_interest "
            "FROM cot_positions WHERE market=? AND report_date<=? ORDER BY report_date",
            (market, self.as_of),
        ).fetchall()
