#!/usr/bin/env python3
"""Generer skreddersydde fingerprint-YAML for hele universet fra én kompakt spec.

Domeneriktige drivere pr instrument (COT-retning korrekt pr symbol — f.eks. JPY-futures
er invertert mot USDJPY). Låste base-rate-terskler.
Kjør:  python scripts/gen_universe_fingerprints.py
Gull/EURUSD/Kaffe røres ikke (allerede skrevet for hånd).
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
    ("Silver", "SILVER", "metals",
     [spread("DGS10", "T10YIE", 0.30, "low"), cot("Silver", 0.25), trend("SILVER", 0.25),
      mom("SILVER", 0.20)]),
    ("Platinum", "PLATINUM", "metals",
     [macro_mom("DTWEXBGS", 0.20, "low"), cot("Platinum", 0.25), trend("PLATINUM", 0.30),
      mom("PLATINUM", 0.25)]),
    ("Copper", "COPPER", "metals",
     [macro_lvl("BAMLH0A0HYM2", 0.20, "low"), cot("Copper", 0.25), trend("COPPER", 0.30),
      mom("COPPER", 0.25)]),
    # Energi
    ("WTI", "OIL WTI", "energy",
     [macro_lvl("OVX", 0.20, "low"), cot("WTI", 0.30), trend("OIL WTI", 0.25),
      mom("OIL WTI", 0.25)]),
    ("Brent", "OIL BRENT", "energy",
     [macro_lvl("OVX", 0.20, "low"), cot("Brent", 0.30), trend("OIL BRENT", 0.25),
      mom("OIL BRENT", 0.25)]),
    ("NatGas", "Natural Gas", "energy",
     [cot("NatGas", 0.30), trend("Natural Gas", 0.35), mom("Natural Gas", 0.35)]),
    # Korn/softs
    ("Corn", "Corn", "grains",
     [macro_mom("DTWEXBGS", 0.20, "low"), cot("Corn", 0.30), trend("Corn", 0.30),
      mom("Corn", 0.20)]),
    ("Soybean", "Soybean", "grains",
     [macro_mom("DTWEXBGS", 0.20, "low"), cot("Soybean", 0.30), trend("Soybean", 0.30),
      mom("Soybean", 0.20)]),
    ("Wheat", "Wheat", "grains",
     [macro_mom("DTWEXBGS", 0.20, "low"), cot("Wheat", 0.30), trend("Wheat", 0.30),
      mom("Wheat", 0.20)]),
    ("Sugar", "Sugar", "softs",
     [macro_mom("DEXBZUS", 0.25, "low"), cot("Sugar", 0.30), trend("Sugar", 0.25),
      mom("Sugar", 0.20)]),
    ("Cocoa", "Cocoa", "softs",
     [cot("Cocoa", 0.35), trend("Cocoa", 0.35), mom("Cocoa", 0.30)]),
    ("Cotton", "Cotton", "softs",
     [macro_mom("DTWEXBGS", 0.20, "low"), cot("Cotton", 0.30), trend("Cotton", 0.30),
      mom("Cotton", 0.20)]),
    # FX — rentediff + DXY. NB COT-retning og diff-fortegn avhenger av base-valuta:
    #   *USD-par (EUR/GBP/AUD): sterk USD = par NED → bull_when low; COT long utenl. = bull par.
    #   USDJPY (USD-base): sterk USD = par OPP → bull_when high; COT long JPY = bear par → low.
    ("GBPUSD", "GBPUSD", "fx",
     [spread("DGS10", "IRLTLT01GBM156N", 0.30, "low"), macro_mom("DTWEXBGS", 0.25, "low"),
      cot("GBPUSD", 0.20, "high"), trend("GBPUSD", 0.25)]),
    ("USDJPY", "USDJPY", "fx",
     [spread("DGS10", "IRLTLT01JPM156N", 0.30, "high"), macro_mom("DTWEXBGS", 0.25, "high"),
      cot("USDJPY", 0.20, "low"), trend("USDJPY", 0.25)]),
    ("AUDUSD", "AUDUSD", "fx",
     [spread("DGS10", "IRLTLT01AUM156N", 0.30, "low"), macro_mom("DTWEXBGS", 0.25, "low"),
      cot("AUDUSD", 0.20, "high"), trend("AUDUSD", 0.25)]),
    # Indeks — kredittspread-regime (lav = risk-on)
    ("SP500", "SPX500", "index",
     [macro_lvl("BAMLH0A0HYM2", 0.30, "low"), cot("SP500", 0.20, "high"), trend("SPX500", 0.30),
      mom("SPX500", 0.20)]),
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
