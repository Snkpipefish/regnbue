"""SqueezeMetrics-henter → `macro_series` (DATA_KARTLEGGING §3b).

Gratis daglig CSV (ingen auth) med SPX **GEX** (dealer-gamma, ferdig beregnet) + **DIX**
(Dark Index — dark-pool kjøpspress, en retnings-flytindikator). Fra 2011 → i dag, oppdateres
daglig. Lagres som makro-serier `SQZ_GEX` / `SQZ_DIX` så de gjenbruker eksisterende drivere
(`level_percentile`/`momentum`) OG kan valideres historisk (ulikt DIY-krypto-gamma).

Kilde: https://squeezemetrics.com/monitor/static/DIX.csv  (kolonner: date, price, dix, gex)

Bruk:  python -m setups.fetch.squeeze [--db data/regnbue.db]
"""
from __future__ import annotations

import argparse
import csv
import io

import requests

from setups import store

CSV_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"


def parse_dix_csv(text: str) -> list[tuple[str, float, float]]:
    """(date, dix, gex)-rader fra CSV-teksten. Hopper over ufullstendige rader (testbar)."""
    out: list[tuple[str, float, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out.append((row["date"], float(row["dix"]), float(row["gex"])))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def update_squeeze(db_path=store.DEFAULT_DB_PATH, timeout: int = 30) -> dict[str, int]:
    """Hent SqueezeMetrics-CSV og upsert SQZ_DIX + SQZ_GEX i macro_series."""
    text = requests.get(CSV_URL, timeout=timeout).text
    rows = parse_dix_csv(text)
    with store.connect(db_path) as conn:
        store.init_db(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series(series_id,date,value) VALUES ('SQZ_DIX',?,?)",
            [(d, dix) for d, dix, _ in rows],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series(series_id,date,value) VALUES ('SQZ_GEX',?,?)",
            [(d, gex) for d, _, gex in rows],
        )
    return {"SQZ_DIX": len(rows), "SQZ_GEX": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent SqueezeMetrics DIX/GEX → macro_series.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()
    counts = update_squeeze(db_path=args.db)
    print(f"SqueezeMetrics: {counts['SQZ_DIX']} dager DIX+GEX lagret.")


if __name__ == "__main__":
    main()
