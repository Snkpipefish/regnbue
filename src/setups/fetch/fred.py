"""FRED-henter → `macro_series`.

Arbeidshesten for makrodrivere (realrente, DXY, rente-differanser, gull-vol, ENSO osv.)
på tvers av MVP-instrumentene. Én ren API, én nøkkel (`FRED_API_KEY`). Idempotent upsert.

Bruk:
    python -m setups.fetch.fred DGS10 T10YIE DX-Y.NYB --start 2020-01-01
"""

from __future__ import annotations

import argparse

import requests

from setups import store
from setups.secrets import require_secret

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# Standard MVP-serier — kun ekte FRED-id-er (matcher seed-id-ene 1:1).
# DX-Y.NYB (DXY), GVZ (gull-vol), NOAA_ONI/IRI_ENSO (klima) er IKKE FRED i bedrock og
# hentes av egne fetchere senere; her holder vi oss til FRED-arbeidshestene.
MVP_SERIES = [
    "DGS10", "DGS2", "T10YIE", "DTWEXBGS",
    "DEXUSEU", "DEXBZUS", "IRLTLT01DEM156N",
]


def fetch_series(series_id: str, start: str | None = None,
                 timeout: int = 30) -> list[tuple[str, float]]:
    """Hent observasjoner for én FRED-serie. Hopper over manglende (".")."""
    params = {
        "series_id": series_id,
        "api_key": require_secret("FRED_API_KEY"),
        "file_type": "json",
    }
    if start:
        params["observation_start"] = start
    resp = requests.get(FRED_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    out: list[tuple[str, float]] = []
    for obs in resp.json().get("observations", []):
        val = obs.get("value", ".")
        if val in (".", "", None):
            continue
        try:
            out.append((obs["date"], float(val)))
        except (ValueError, KeyError):
            continue
    return out


def update_macro_series(series_ids: list[str] | None = None, start: str | None = None,
                        db_path=store.DEFAULT_DB_PATH) -> dict[str, int]:
    """Hent og upsert serier i `macro_series`. Returnerer radtelling pr serie."""
    series_ids = series_ids or MVP_SERIES
    counts: dict[str, int] = {}
    with store.connect(db_path) as conn:
        store.init_db(conn)
        for sid in series_ids:
            obs = fetch_series(sid, start=start)
            conn.executemany(
                "INSERT OR REPLACE INTO macro_series(series_id,date,value) VALUES (?,?,?)",
                [(sid, d, v) for d, v in obs],
            )
            counts[sid] = len(obs)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent FRED-serier til macro_series.")
    ap.add_argument("series", nargs="*", help="FRED series_id(er); standard = MVP-settet.")
    ap.add_argument("--start", default=None, help="observation_start YYYY-MM-DD")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()

    counts = update_macro_series(args.series or None, start=args.start, db_path=args.db)
    print("FRED-oppdatering:")
    for sid, n in counts.items():
        print(f"  {sid}: {n} obs")


if __name__ == "__main__":
    main()
