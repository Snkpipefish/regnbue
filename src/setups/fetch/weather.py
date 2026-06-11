"""Open-Meteo vær-henter (gratis, ingen nøkkel) → `weather`-tabellen.

ERA5-arkiv (dyp historikk fra 1940). Henter daglig nedbør + temp for en region og lagrer
i datastoren. Brukt av `rainfall_anomaly`-driveren. Egen, frisk implementasjon.

Bruk:  python -m setups.fetch.weather            # standard-regioner
"""

from __future__ import annotations

import argparse
import time

import requests

from setups import store

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# God nabo: Open-Meteos gratis arkiv-API rate-limiter pr IP (ikke pr nøkkel som FRED).
# Vi sprer kallene mellom regioner og backer av på 429/5xx i stedet for å dø på første
# 429 (jf. update.sh: vær-steget er best-effort). Beskjedne tall holder — vi henter
# bare ~7 regioner.
REQUEST_SPACING_S = 1.0        # pause mellom regioner
MAX_RETRIES = 4               # forsøk pr region ved 429/5xx
BACKOFF_BASE_S = 5.0          # eksponentiell: 5, 10, 20, 40 s (om Retry-After mangler)


def _get_with_backoff(params: dict, timeout: int) -> requests.Response:
    """GET med eksponentiell backoff på 429/5xx. Respekterer `Retry-After` når satt.

    Open-Meteo rate-limiter pr IP; ved 429 venter vi og prøver igjen i stedet for å
    feile hele kjøringen.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        resp = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
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
            f"{resp.status_code} fra Open-Meteo, "
            f"forsøk {attempt + 1}/{MAX_RETRIES}, venter {wait_s:.0f}s")
        if attempt < MAX_RETRIES - 1:
            time.sleep(wait_s)
    # Brukte opp forsøkene — la kallet feile slik at update.sh logger og fortsetter.
    if last_exc:
        raise last_exc
    raise requests.HTTPError("Open-Meteo-kall feilet uten respons")

# Representative punkter pr region. Brasil Center-South cane: Ribeirão Preto (SP).
# Sul de Minas (Varginha): arabica-hjertet, frost-utsatt (austral vinter jun–aug → geada).
# us_gas_demand: Chicago (Midwest) som oppvarmings-tung proxy for US gass-etterspørsel.
# Avlings-regioner: kornbelte (Des Moines IA), hvete-sletter (Wichita KS),
# Vest-Afrika kakao (Daloa, Elfenbenskysten), US bomull (Lubbock TX).
REGIONS: dict[str, tuple[float, float]] = {
    "brazil_cs_cane": (-21.17, -47.81),
    "brazil_sul_minas": (-21.55, -45.43),
    "us_gas_demand": (41.85, -87.65),
    "us_cornbelt": (41.59, -93.62),
    "us_wheat_plains": (37.69, -97.34),
    "west_africa_cocoa": (6.88, -6.45),
    "us_cotton": (33.58, -101.86),
}


def fetch_region(region: str, lat: float, lon: float, start: str = "2000-01-01",
                 timeout: int = 60) -> list[tuple[str, float | None, float | None, float | None]]:
    """Hent daglig (dato, tmax, tmin, precip) for ett punkt fra Open-Meteo-arkivet."""
    import datetime as _dt
    end = _dt.date.today().isoformat()
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "UTC",
    }
    resp = _get_with_backoff(params, timeout)
    d = resp.json().get("daily", {})
    dates = d.get("time", [])
    precip = d.get("precipitation_sum", [])
    tmax = d.get("temperature_2m_max", [])
    tmin = d.get("temperature_2m_min", [])
    out = []
    for i, day in enumerate(dates):
        out.append((day, tmax[i] if i < len(tmax) else None,
                    tmin[i] if i < len(tmin) else None,
                    precip[i] if i < len(precip) else None))
    return out


def update_weather(regions: dict[str, tuple[float, float]] | None = None,
                   start: str = "2000-01-01", db_path=store.DEFAULT_DB_PATH) -> dict[str, int]:
    """Hent og upsert vær for regionene. Returnerer radtelling pr region."""
    regions = regions or REGIONS
    counts: dict[str, int] = {}
    with store.connect(db_path) as conn:
        store.init_db(conn)
        for i, (region, (lat, lon)) in enumerate(regions.items()):
            if i:  # spre kallene — ikke før første region
                time.sleep(REQUEST_SPACING_S)
            rows = fetch_region(region, lat, lon, start=start)
            conn.executemany(
                "INSERT OR REPLACE INTO weather(region,date,tmax,tmin,precip) "
                "VALUES (?,?,?,?,?)",
                [(region, day, tmax, tmin, precip) for day, tmax, tmin, precip in rows],
            )
            counts[region] = len(rows)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent Open-Meteo-vær til weather-tabellen.")
    ap.add_argument("--start", default="2000-01-01")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()
    counts = update_weather(start=args.start, db_path=args.db)
    print("Vær-oppdatering:")
    for region, n in counts.items():
        print(f"  {region}: {n} dager")


if __name__ == "__main__":
    main()
