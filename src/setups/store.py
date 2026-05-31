"""Regnbue-datastore (SQLite).

Egen, frisk datastore — ingen kodekopiering fra bedrock. Holder **bias/kontekst**-data
(COT-posisjonering, makro-serier, COMEX-lager, vær, ETF-beholdning) som brukes til
retning/regime/scoring. **Nivå-koordinater** (entry/SL/TP) kommer IKKE herfra — de regnes
på Skillings prisfeed via cTrader (fase 2), jf. K3/§5b.

Lagringsformat låst til SQLite (DECISIONS 2026-05-30). Schemaet er normalisert til det de
3 MVP-instrumentene (Gull, EURUSD, Kaffe) faktisk trenger; utvides når flere fingerprint kommer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path("data/regnbue.db")

# Ett normalisert spekulant/kommersiell-bilde på tvers av COT-rapporttyper
# (disaggregated/tff/legacy) — drivere trenger "spec net" konsistent, ikke alle råfelt.
SCHEMA = """
CREATE TABLE IF NOT EXISTS cot_positions (
    market       TEXT NOT NULL,   -- Regnbue-instrument-id (Gold/EURUSD/Coffee)
    report_date  TEXT NOT NULL,
    report_type  TEXT NOT NULL,   -- disaggregated | tff | legacy
    long_spec    INTEGER,
    short_spec   INTEGER,
    long_comm    INTEGER,
    short_comm   INTEGER,
    open_interest INTEGER,
    PRIMARY KEY (market, report_date)
);

-- NIVÅ-feed: OHLC fra Skillings egen prisfeed (cTrader). Dette er ENESTE kilde for
-- entry/SL/TP-koordinater (K3/§5b). symbol = Skilling-ticker (GOLD, EURUSD, COFFEE ...).
CREATE TABLE IF NOT EXISTS prices (
    symbol  TEXT NOT NULL,
    tf      TEXT NOT NULL,     -- D1 i MVP
    ts      TEXT NOT NULL,     -- ISO UTC (bar-åpning)
    open    REAL NOT NULL,
    high    REAL NOT NULL,
    low     REAL NOT NULL,
    close   REAL NOT NULL,
    volume  REAL,
    PRIMARY KEY (symbol, tf, ts)
);

CREATE TABLE IF NOT EXISTS macro_series (
    series_id  TEXT NOT NULL,     -- FRED-id (DGS10, DFII10, DTWEXBGS, GVZCLS, ...)
    date       TEXT NOT NULL,
    value      REAL,
    PRIMARY KEY (series_id, date)
);

CREATE TABLE IF NOT EXISTS comex_inventory (
    metal       TEXT NOT NULL,
    date        TEXT NOT NULL,
    registered  REAL,
    eligible    REAL,
    total       REAL,
    units       TEXT,
    PRIMARY KEY (metal, date)
);

CREATE TABLE IF NOT EXISTS weather (
    region  TEXT NOT NULL,
    date    TEXT NOT NULL,
    tmax    REAL,
    tmin    REAL,
    precip  REAL,
    gdd     REAL,
    PRIMARY KEY (region, date)
);

CREATE TABLE IF NOT EXISTS etf_holdings (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    tonnes_in_trust REAL,
    shares_outstanding REAL,   -- flyt-proxy når tonnes mangler (f.eks. SLV)
    PRIMARY KEY (ticker, date)
);

-- Sporing av engangs-seed (idempotens + revisjon).
CREATE TABLE IF NOT EXISTS seed_log (
    source_table  TEXT NOT NULL,
    target_table  TEXT NOT NULL,
    market        TEXT,
    rows_seeded   INTEGER NOT NULL,
    seeded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_table, target_table, market)
);
"""


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Åpne datastoren (oppretter mappe + fil ved behov). Foreign keys på."""
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Opprett alle tabeller (idempotent)."""
    conn.executescript(SCHEMA)
    # Idempotent kolonne-migrasjon for eldre datastore-filer.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(etf_holdings)")}
    if "shares_outstanding" not in cols:
        conn.execute("ALTER TABLE etf_holdings ADD COLUMN shares_outstanding REAL")


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def row_count(conn: sqlite3.Connection, table: str) -> int:
    if table not in table_names(conn):
        raise ValueError(f"Ukjent tabell: {table}")
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
