#!/usr/bin/env python3
"""Generer skreddersydde fingerprint-YAML for hele universet fra én kompakt spec.

Domeneriktige drivere pr instrument (COT-retning korrekt pr symbol — f.eks. JPY-futures
er invertert mot USDJPY). Låste base-rate-terskler.
Kjør:  python scripts/gen_universe_fingerprints.py
Gull/EURUSD/Kaffe/Sugar røres ikke (håndtilpasset med instrument-spesifikke drivere).
"""
from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "config" / "instruments"
GRADE = {"A_plus": 0.55, "A": 0.40, "B": 0.25}
BASE_RATE = {"horizon_days": 30, "band": 0.10, "min_effective_n": 30,
             "min_hit_rate_pct": 55, "min_expectancy_r": 0.3}


def D(name, weight, **params):
    return {"name": name, "weight": weight, "params": params}


def cot(market, weight, bull="high"):
    return D("cot_spec_net_percentile", weight, market=market, lookback_weeks=156, bull_when=bull)


def trend(sym, weight):
    return D("price_vs_sma", weight, symbol=sym, window=200, tf="D1")


def mom(sym, weight):
    return D("price_momentum", weight, symbol=sym, horizon_days=20)


def macro_mom(series, weight, bull="low"):
    return D("momentum", weight, series=series, horizon_days=21, bull_when=bull)


def macro_lvl(series, weight, bull="low"):
    return D("level_percentile", weight, series=series, lookback_days=504, bull_when=bull)


def spread(minu, sub, weight, bull="low"):
    return D("series_spread_percentile", weight, minuend=minu, subtrahend=sub,
             lookback_days=504, bull_when=bull)


# id, ticker (Skilling), asset_class, drivere
SPEC = [
    # Metaller — realrente (gull/sølv), DXY/industriell
    # (Silver håndtilpasset i config/instruments/silver.yaml — fjernet herfra.)
    # (Platinum håndtilpasset i config/instruments/platinum.yaml — fjernet herfra.)
    # (Copper håndtilpasset i config/instruments/copper.yaml — fjernet herfra.)
    # Energi (WTI/Brent/NatGas håndtilpasset i config/instruments/ — fjernet herfra.)
    # Korn/softs (Corn/Soybean/Wheat/Cocoa/Cotton håndtilpasset i config/instruments/ — fjernet herfra.)
    # FX — rentediff + DXY. NB COT-retning og diff-fortegn avhenger av base-valuta:
    #   *USD-par (EUR/GBP/AUD): sterk USD = par NED → bull_when low; COT long utenl. = bull par.
    #   USDJPY (USD-base): sterk USD = par OPP → bull_when high; COT long JPY = bear par → low.
    # (GBPUSD/USDJPY/AUDUSD håndtilpasset i config/instruments/ — fjernet herfra.)
    # Indeks — kredittspread-regime (lav = risk-on)
    ("SP500", "SPX500", "index",
     [macro_lvl("BAMLH0A0HYM2", 0.30, "low"), cot("SP500", 0.20, "high"), trend("SPX500", 0.30),
      mom("SPX500", 0.20)]),
    ("Nasdaq", "US100", "index",
     [macro_lvl("BAMLH0A0HYM2", 0.30, "low"), cot("Nasdaq", 0.20, "high"), trend("US100", 0.30),
      mom("US100", 0.20)]),
    # Krypto — pris + posisjonering
    ("BTCUSD", "Bitcoin", "crypto",
     [cot("BTCUSD", 0.25, "high"), trend("Bitcoin", 0.40), mom("Bitcoin", 0.35)]),
    ("ETHUSD", "Ethereum", "crypto",
     [cot("ETHUSD", 0.25, "high"), trend("Ethereum", 0.40), mom("Ethereum", 0.35)]),
]


def main() -> None:
    for id_, ticker, asset, drivers in SPEC:
        fp = {"id": id_, "ticker": ticker, "asset_class": asset,
              "drivers": drivers, "grade_thresholds": GRADE, "base_rate": BASE_RATE}
        path = OUT / f"{id_.lower()}.yaml"
        path.write_text(yaml.safe_dump(fp, sort_keys=False, allow_unicode=True))
        print(f"skrev {path.name}")


if __name__ == "__main__":
    main()
