"""EIA-henter (US Energy Information Administration) → `macro_series`.

Petroleums-/gass-fundamentaler (lager) som dype, sesong-vurderbare drivere. EIA API v2
`data`-rute med serie-facet (rute varierer pr datasett). Én nøkkel (`BEDROCK_EIA_API_KEY`).
Idempotent upsert. Egen, frisk implementasjon (ingen kopiering fra bedrock).

Bruk:
    python -m setups.fetch.eia                       # standard energi-lager-settet
    python -m setups.fetch.eia WCESTUS1 NG_STOR_L48  # utvalgte (nøkler i SERIES)
"""

from __future__ import annotations

import argparse

import requests

from setups import store
from setups.secrets import require_secret

EIA_BASE = "https://api.eia.gov/v2/"

# Vennlig nøkkel → (data-rute, EIA serie-facet). Lagres i macro_series under nøkkelen.
#   WCESTUS1    = US råolje-lager eks. SPR (ukentlig, tusen fat) — olje-tilbuds-driver.
#   NG_STOR_L48 = US naturgass i lager, Lower 48 (ukentlig, Bcf) — gass-tilbuds-driver.
SERIES: dict[str, tuple[str, str]] = {
    "WCESTUS1": ("petroleum/stoc/wstk", "WCESTUS1"),
    "NG_STOR_L48": ("natural-gas/stor/wkly", "NW2_EPG0_SWO_R48_BCF"),
}


def fetch_series(key: str, start: str | None = None, timeout: int = 30) -> list[tuple[str, float]]:
    """Hent (dato, verdi) for én registrert EIA-serie, stigende på dato."""
    if key not in SERIES:
        raise KeyError(f"ukjent EIA-serie: {key} (registrert: {sorted(SERIES)})")
    route, facet = SERIES[key]
    params = {
        "api_key": require_secret("BEDROCK_EIA_API_KEY"),
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": facet,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    if start:
        params["start"] = start
    resp = requests.get(f"{EIA_BASE}{route}/data/", params=params, timeout=timeout)
    resp.raise_for_status()
    rows = resp.json().get("response", {}).get("data", [])
    out: list[tuple[str, float]] = []
    for r in rows:
        period, val = r.get("period"), r.get("value")
        if period is None or val is None:
            continue
        try:
            out.append((period[:10], float(val)))
        except (ValueError, TypeError):
            continue
    return out


def update_eia_series(keys: list[str] | None = None, start: str | None = None,
                      db_path=store.DEFAULT_DB_PATH) -> dict[str, int]:
    """Hent og upsert EIA-serier i `macro_series` (lagret under vennlig nøkkel)."""
    keys = keys or list(SERIES)
    counts: dict[str, int] = {}
    with store.connect(db_path) as conn:
        store.init_db(conn)
        for key in keys:
            obs = fetch_series(key, start=start)
            conn.executemany(
                "INSERT OR REPLACE INTO macro_series(series_id,date,value) VALUES (?,?,?)",
                [(key, d, v) for d, v in obs],
            )
            counts[key] = len(obs)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent EIA-serier til macro_series.")
    ap.add_argument("series", nargs="*", help="Vennlige nøkler (se SERIES); standard = alle.")
    ap.add_argument("--start", default=None, help="start YYYY-MM-DD")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()
    counts = update_eia_series(args.series or None, start=args.start, db_path=args.db)
    print("EIA-oppdatering:")
    for key, n in counts.items():
        print(f"  {key}: {n} obs")


if __name__ == "__main__":
    main()
