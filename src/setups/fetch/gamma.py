"""Dealer-gamma-fetcher (DATA_KARTLEGGING §3b) — Deribit BTC/ETH, gratis, ingen auth.

Ett kall (`get_book_summary_by_currency`) gir OI + mark_iv + spot pr opsjonskontrakt. Vi regner
naiv Black-Scholes-gamma selv, summerer til netto-GEX (SqueezeMetrics-konvensjon: dealere long
calls / short puts ⇒ GEX = Σ_call γ·OI − Σ_put γ·OI, positiv = vol-dempende), og en gamma-vektet
«magnet»-strike (pin). EOD-snapshot lagres pr dag — INGEN gratis OI-historikk, så serien
akkumuleres framover og kan ikke backfylles/valideres historisk ennå.

Bruk:  python -m setups.fetch.gamma [--db data/regnbue.db]
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from math import exp, log, pi, sqrt

from setups import store

API = "https://www.deribit.com/api/v2/public"
CURRENCIES = {"BTC": "btc", "ETH": "eth"}   # Deribit-valuta → driver-instrument


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2 * pi)


def bs_gamma(spot: float, strike: float, t_years: float, sigma: float, r: float = 0.0) -> float:
    """Black-Scholes-gamma (lik for call og put). 0 ved degenererte input."""
    if spot <= 0 or strike <= 0 or t_years <= 0 or sigma <= 0:
        return 0.0
    d1 = (log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt(t_years))
    return _norm_pdf(d1) / (spot * sigma * sqrt(t_years))


def _parse_instrument(name: str) -> tuple[date, float, str] | None:
    """'BTC-26MAR27-105000-C' → (utløpsdato, strike, 'C'|'P'). None hvis uventet format."""
    try:
        _cur, expiry, strike, kind = name.split("-")
        return datetime.strptime(expiry, "%d%b%y").date(), float(strike), kind.upper()
    except (ValueError, KeyError):
        return None


def compute_snapshot(contracts: list[dict], spot: float, now: datetime) -> dict | None:
    """Ren beregning (testbar uten nett): netto-GEX + gamma-vektet pin fra kontraktlista."""
    if spot <= 0:
        return None
    net_gex = 0.0
    wsum = 0.0          # Σ |γ·OI|  (vekter for magnet)
    wstrike = 0.0       # Σ |γ·OI|·strike
    today = now.date()
    for c in contracts:
        parsed = _parse_instrument(c.get("instrument_name", ""))
        oi = c.get("open_interest") or 0.0
        iv = c.get("mark_iv")
        if parsed is None or oi <= 0 or not iv:
            continue
        expiry, strike, kind = parsed
        t = (expiry - today).days / 365.0
        g = bs_gamma(spot, strike, t, iv / 100.0, c.get("interest_rate") or 0.0)
        if g <= 0:
            continue
        w = g * oi
        net_gex += w if kind == "C" else -w     # calls + / puts − (SqueezeMetrics)
        wsum += w
        wstrike += w * strike
    if wsum <= 0:
        return None
    return {"spot": round(spot, 2), "net_gex": round(net_gex, 4),
            "gamma_center": round(wstrike / wsum, 2)}


def fetch_deribit(currency: str, session=None) -> dict | None:
    """Hent + beregn gamma-snapshot for én valuta fra Deribit (live nett)."""
    import requests
    s = session or requests.Session()
    spot = s.get(f"{API}/get_index_price",
                 params={"index_name": f"{currency.lower()}_usd"}, timeout=20
                 ).json()["result"]["index_price"]
    contracts = s.get(f"{API}/get_book_summary_by_currency",
                      params={"currency": currency, "kind": "option"}, timeout=30
                      ).json()["result"]
    return compute_snapshot(contracts, spot, datetime.now(tz=UTC))


def update_gamma(conn, currencies: dict | None = None, as_of: str | None = None) -> int:
    """Hent og lagre EOD-gamma-snapshot pr instrument. Returnerer antall lagret."""
    store.init_db(conn)
    day = as_of or datetime.now(tz=UTC).date().isoformat()
    n = 0
    for cur, inst in (currencies or CURRENCIES).items():
        snap = fetch_deribit(cur)
        if snap is None:
            print(f"  {cur}: ingen gyldig snapshot")
            continue
        conn.execute(
            "INSERT OR REPLACE INTO gamma(instrument,date,spot,net_gex,gamma_center) "
            "VALUES (?,?,?,?,?)",
            (inst, day, snap["spot"], snap["net_gex"], snap["gamma_center"]),
        )
        n += 1
        regime = "long-gamma (dempende)" if snap["net_gex"] > 0 else "short-gamma (forsterkende)"
        print(f"  {inst} {day}: spot {snap['spot']} · pin {snap['gamma_center']} · {regime}")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent dealer-gamma (Deribit BTC/ETH) → gamma-tabell.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()
    with store.connect(args.db) as conn:
        n = update_gamma(conn)
    print(f"Lagret {n} gamma-snapshot.")


if __name__ == "__main__":
    main()
