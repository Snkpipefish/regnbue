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
from datetime import date, timedelta

# --- cache for FULL serier (panel-bygging re-scorer pr dato; uten cache gjør hver driver en
#     full SQL-henting + ev. spread-/ratio-merge pr kall). Vi henter HELE serien én gang og
#     skjærer ≤as_of med bisect → IDENTISKE resultater (samme rader returneres) og look-ahead
#     bevares (framtidige rader returneres aldri). Nøkkelen har en innholds-signatur
#     (count,min,max) — indeks-støttet via PK — så ulike datasett/conns aldri kolliderer og
#     endret data re-nøkles automatisk.
_FULL_CACHE: dict = {}


def _cached(key, builder):
    hit = _FULL_CACHE.get(key)
    if hit is not None:
        return hit
    out = builder()
    _FULL_CACHE[key] = out
    return out


def _macro_sig(conn: sqlite3.Connection, series_id: str):
    # SUM(value) i signaturen så ulike verdisett med samme antall/datospenn ikke kolliderer.
    return tuple(conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date), SUM(value) FROM macro_series "
        "WHERE series_id=? AND value IS NOT NULL", (series_id,)).fetchone())


def _full_macro(conn: sqlite3.Connection, series_id: str):
    """(datoer, (dato,verdi)-par) for HELE makro-serien, value not null, stigende."""
    def build():
        rows = conn.execute(
            "SELECT date, value FROM macro_series "
            "WHERE series_id=? AND value IS NOT NULL ORDER BY date", (series_id,)).fetchall()
        return [r[0] for r in rows], [(r[0], r[1]) for r in rows]

    return _cached(("macro", series_id, _macro_sig(conn, series_id)), build)


def _full_spread(conn: sqlite3.Connection, minuend: str, subtrahend: str):
    """(datoer, (dato,spread)-par) for HELE spread-serien (subtrahend forward-fylt)."""
    a_dates, a_pairs = _full_macro(conn, minuend)
    b_dates, b_pairs = _full_macro(conn, subtrahend)
    b_vals = [v for _, v in b_pairs]
    # Signaturen arver begge makro-signaturene → endrer seg hvis enten serie endrer verdier.
    sig = (_macro_sig(conn, minuend), _macro_sig(conn, subtrahend))

    def build():
        out_d: list[str] = []
        out_pairs: list[tuple[str, float]] = []
        for d, av in a_pairs:
            i = bisect_right(b_dates, d) - 1  # siste subtrahend-obs på/ før d
            if i >= 0:
                out_d.append(d)
                out_pairs.append((d, av - b_vals[i]))
        return out_d, out_pairs

    return _cached(("spread", minuend, subtrahend, sig), build)


def _full_closes(conn: sqlite3.Connection, symbol: str, tf: str):
    """(dato-deler, (ts,close)-par) for HELE pris-serien, stigende på ts."""
    sig = conn.execute(
        "SELECT COUNT(*), MIN(ts), MAX(ts), SUM(close) FROM prices WHERE symbol=? AND tf=?",
        (symbol, tf)).fetchone()

    def build():
        rows = conn.execute(
            "SELECT ts, close FROM prices WHERE symbol=? AND tf=? ORDER BY ts",
            (symbol, tf)).fetchall()
        return [r[0][:10] for r in rows], [(r[0], r[1]) for r in rows]

    return _cached(("closes", symbol, tf, tuple(sig)), build)


def _full_etf(conn: sqlite3.Connection, ticker: str):
    """(datoer, (dato,enheter)-par) for HELE ETF-beholdningen, ikke-null, stigende."""
    sig = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date), SUM(COALESCE(tonnes_in_trust, shares_outstanding)) "
        "FROM etf_holdings WHERE ticker=? "
        "AND COALESCE(tonnes_in_trust, shares_outstanding) IS NOT NULL", (ticker,)).fetchone()

    def build():
        rows = conn.execute(
            "SELECT date, COALESCE(tonnes_in_trust, shares_outstanding) FROM etf_holdings "
            "WHERE ticker=? AND COALESCE(tonnes_in_trust, shares_outstanding) IS NOT NULL "
            "ORDER BY date", (ticker,)).fetchall()
        return [r[0] for r in rows], [(r[0], r[1]) for r in rows]

    return _cached(("etf", ticker, tuple(sig)), build)


def _full_cot(conn: sqlite3.Connection, market: str):
    """(rapport-datoer, rader) for HELE COT-historikken, stigende."""
    sig = conn.execute(
        "SELECT COUNT(*), MIN(report_date), MAX(report_date), SUM(long_spec), SUM(short_spec) "
        "FROM cot_positions WHERE market=?", (market,)).fetchone()

    def build():
        rows = conn.execute(
            "SELECT report_date, long_spec, short_spec, long_comm, short_comm, open_interest "
            "FROM cot_positions WHERE market=? ORDER BY report_date", (market,)).fetchall()
        return [r[0] for r in rows], rows

    return _cached(("cot", market, tuple(sig)), build)


@dataclass
class ScoreContext:
    conn: sqlite3.Connection
    as_of: str  # 'YYYY-MM-DD'

    # --- makro-serier ---
    def series(self, series_id: str) -> list[tuple[str, float]]:
        """(dato, verdi) stigende, kun t.o.m. as_of."""
        dates, pairs = _full_macro(self.conn, series_id)
        return pairs[:bisect_right(dates, self.as_of)]

    def spread_series(self, minuend: str, subtrahend: str) -> list[tuple[str, float]]:
        """minuend − subtrahend, der subtrahend forward-fylles på minuend-datoer.

        Håndterer ulik kadens (f.eks. daglig DGS10 mot månedlig OECD-rente).
        """
        dates, pairs = _full_spread(self.conn, minuend, subtrahend)
        return pairs[:bisect_right(dates, self.as_of)]

    # --- priser (NIVÅ-feed) ---
    def closes(self, symbol: str, tf: str = "D1") -> list[tuple[str, float]]:
        dparts, pairs = _full_closes(self.conn, symbol, tf)
        return pairs[:bisect_right(dparts, self.as_of)]

    # --- ETF-beholdning (fysisk investerings-flyt) ---
    def etf_holdings(self, ticker: str) -> list[tuple[str, float]]:
        """(dato, beholdnings-enheter) stigende, kun t.o.m. as_of.

        Bruker tonnes_in_trust der det finnes (f.eks. GLD), ellers shares_outstanding
        (f.eks. SLV som ikke har tonn i kilden). etf_flow er skala-invariant (% endring),
        så enheten er irrelevant — bare flyt-retningen teller.
        """
        dates, pairs = _full_etf(self.conn, ticker)
        return pairs[:bisect_right(dates, self.as_of)]

    # --- vær (nedbør) ---
    def weather_precip(self, region: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT date, precip FROM weather WHERE region=? AND date<=? AND precip IS NOT NULL "
            "ORDER BY date",
            (region, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- vær (minimumstemperatur, for frost-risiko) ---
    def weather_tmin(self, region: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT date, tmin FROM weather WHERE region=? AND date<=? AND tmin IS NOT NULL "
            "ORDER BY date",
            (region, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- vær (døgnmiddel ≈ (tmax+tmin)/2, for energi-etterspørsel/degree-days) ---
    def weather_tmean(self, region: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT date, (tmax+tmin)/2.0 FROM weather WHERE region=? AND date<=? "
            "AND tmax IS NOT NULL AND tmin IS NOT NULL ORDER BY date",
            (region, self.as_of),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # --- COT-posisjonering ---
    # CFTC måler posisjoner pr tirsdag (`report_date`) men PUBLISERER dem først påfølgende
    # fredag (~3 dager). På en historisk beslutningsdato tirsdag–torsdag var siste tirsdags
    # rapport altså ikke offentlig ennå; å bruke den ville være look-ahead. Vi krever derfor
    # report_date + lag <= as_of.
    COT_RELEASE_LAG_DAYS = 3

    def cot(self, market: str) -> list[sqlite3.Row]:
        rdates, rows = _full_cot(self.conn, market)
        cutoff = (date.fromisoformat(self.as_of)
                  - timedelta(days=self.COT_RELEASE_LAG_DAYS)).isoformat()
        return rows[:bisect_right(rdates, cutoff)]
