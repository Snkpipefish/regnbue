"""FRED-henter → `macro_series`.

Arbeidshesten for makrodrivere (realrente, DXY, rente-differanser, gull-vol, ENSO osv.)
på tvers av MVP-instrumentene. Én ren API, én nøkkel (`FRED_API_KEY`). Idempotent upsert.

Bruk:
    python -m setups.fetch.fred DGS10 T10YIE DX-Y.NYB --start 2020-01-01
"""

from __future__ import annotations

import argparse
import time

import requests

from setups import store
from setups.secrets import require_secret

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# God nabo: FRED rate-limiter pr API-nøkkel (120 req/min), og nøkkelen deles med
# bedrock + cot-explorer. Vi sprer egne kall og backer av på 429 i stedet for å dø
# (jf. update.sh: nett-steg er best-effort). Tallene er bevisst forsiktige siden
# vi bare henter ~7 serier — koster < 10 s totalt.
REQUEST_SPACING_S = 1.0        # pause mellom serier
MAX_RETRIES = 4               # forsøk pr serie ved 429/5xx
BACKOFF_BASE_S = 5.0          # eksponentiell: 5, 10, 20, 40 s (om Retry-After mangler)

# Standard MVP-serier — kun ekte FRED-id-er (matcher seed-id-ene 1:1).
# DX-Y.NYB (DXY), GVZ (gull-vol), NOAA_ONI/IRI_ENSO (klima) er IKKE FRED i bedrock og
# hentes av egne fetchere senere; her holder vi oss til FRED-arbeidshestene.
MVP_SERIES = [
    "DGS10", "DGS2", "T10YIE", "DTWEXBGS",
    "DEXUSEU", "DEXBZUS", "IRLTLT01DEM156N",
]


def _get_with_backoff(params: dict, timeout: int) -> requests.Response:
    """GET med eksponentiell backoff på 429/5xx. Respekterer `Retry-After` når satt.

    FRED-nøkkelen deles med andre programmer (bedrock/cot-explorer); en kortvarig
    kollisjon gir 429. Vi venter og prøver igjen i stedet for å feile hele kjøringen.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        resp = requests.get(FRED_URL, params=params, timeout=timeout)
        if resp.status_code not in (429, 500, 502, 503, 504):
            resp.raise_for_status()
            return resp
        # Retryable: regn ut ventetid (Retry-After vinner om den finnes).
        retry_after = resp.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            wait_s = float(retry_after)
        else:
            wait_s = BACKOFF_BASE_S * (2 ** attempt)
        last_exc = requests.HTTPError(
            f"{resp.status_code} fra FRED ({params['series_id']}), "
            f"forsøk {attempt + 1}/{MAX_RETRIES}, venter {wait_s:.0f}s")
        if attempt < MAX_RETRIES - 1:
            time.sleep(wait_s)
    # Brukte opp forsøkene — la kallet feile slik at update.sh logger og fortsetter.
    if last_exc:
        raise last_exc
    raise requests.HTTPError("FRED-kall feilet uten respons")


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
    resp = _get_with_backoff(params, timeout)
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
        for i, sid in enumerate(series_ids):
            if i:  # spre kallene — ikke før første serie
                time.sleep(REQUEST_SPACING_S)
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
