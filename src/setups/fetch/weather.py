"""Open-Meteo vær-henter (gratis, ingen nøkkel) → `weather`-tabellen.

ERA5-arkiv (dyp historikk fra 1940). Henter daglig nedbør + temp for en region og lagrer
i datastoren. Brukt av `rainfall_anomaly`-driveren. Egen, frisk implementasjon.

Bruk:  python -m setups.fetch.weather            # standard-regioner
"""

from __future__ import annotations

import argparse

import requests

from setups import store

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Representative punkter pr region. Brasil Center-South cane: Ribeirão Preto (SP).
# Sul de Minas (Varginha): arabica-hjertet, frost-utsatt (austral vinter jun–aug → geada).
# us_gas_demand: Chicago (Midwest) som oppvarmings-tung proxy for US gass-etterspørsel.
REGIONS: dict[str, tuple[float, float]] = {
    "brazil_cs_cane": (-21.17, -47.81),
    "brazil_sul_minas": (-21.55, -45.43),
    "us_gas_demand": (41.85, -87.65),
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
    resp = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
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
        for region, (lat, lon) in regions.items():
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
