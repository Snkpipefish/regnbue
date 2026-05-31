"""Engangs-seed av bias-historikk fra ``~/bedrock/bedrock.db`` (LESE-ONLY).

Gjenbruk av *data* (tillatt), ikke kode. Kopierer kun det de 3 MVP-instrumentene
(Gull, EURUSD, Kaffe) trenger av bias/regime-historikk inn i Regnbues egen datastore.
Nivå-priser seedes IKKE herfra (de hentes fra Skilling/cTrader, fase 2).

Idempotent: kjør på nytt uten å duplisere (INSERT OR REPLACE + seed_log).

Bruk:
    python -m setups.seed --inspect          # vis tilgjengelige nøkler i bedrock.db
    python -m setups.seed                     # seed MVP-instrumentene
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from setups import store

BEDROCK_DB = Path("~/bedrock/bedrock.db").expanduser()

# Hvilke bedrock-COT-kolonner som blir Regnbues normaliserte spec/comm-felt.
# (Ulike rapporttyper har ulike rå-felt; vi normaliserer til ett spekulant-/kommersiell-bilde.)
COT_COLMAP: dict[str, dict[str, str | None]] = {
    "disaggregated": {
        "src_table": "cot_disaggregated",
        "long_spec": "mm_long", "short_spec": "mm_short",
        "long_comm": "comm_long", "short_comm": "comm_short",
    },
    "ice": {
        "src_table": "cot_ice",
        "long_spec": "mm_long", "short_spec": "mm_short",
        "long_comm": "comm_long", "short_comm": "comm_short",
    },
    "tff": {
        "src_table": "cot_tff",
        "long_spec": "lev_funds_long", "short_spec": "lev_funds_short",
        "long_comm": "dealer_long", "short_comm": "dealer_short",
    },
    "legacy": {
        "src_table": "cot_legacy",
        "long_spec": "noncomm_long", "short_spec": "noncomm_short",
        "long_comm": "comm_long", "short_comm": "comm_short",
    },
}

# Per MVP-instrument: hvilke bias-kilder + nøkkel-kandidater. COT prøver report-typer i
# rekkefølge og matcher kontrakt på substring (robust mot eksakt navngiving, jf. spike-mønsteret).
SEED_MAP: dict[str, dict] = {
    "Gold": {
        # "GOLD" treffer "GOLD - COMMODITY EXCHANGE INC." (disagg). Realrente avledes
        # senere som DGS10 - T10YIE (DFII10 finnes ikke i bedrock). DX-Y.NYB = DXY.
        "cot": {"types": ["disaggregated"], "contracts": ["GOLD"]},
        "macro_series": ["DGS10", "T10YIE", "DX-Y.NYB", "DTWEXBGS", "GVZ"],
        "comex_metals": ["gold"],
        "etf_tickers": ["gld"],
    },
    "EURUSD": {
        # "EURO FX" treffer CME-kontrakten (tff). DGS2 = front-end rente (Fed-forventninger),
        # IRLTLT01DEM156N = tysk lang rente (US−DE rentespread), VIXCLS = risk-sentiment.
        "cot": {"types": ["tff", "legacy"], "contracts": ["EURO FX"]},
        "macro_series": ["DEXUSEU", "DX-Y.NYB", "DGS2", "DGS10", "IRLTLT01DEM156N", "VIXCLS"],
    },
    "Coffee": {
        # "COFFEE" treffer "COFFEE C - ICE FUTURES U.S." (disagg). DEXBZUS = USD/BRL,
        # ONI/ENSO = klima-driver for brasiliansk kaffe.
        "cot": {"types": ["disaggregated", "ice"], "contracts": ["COFFEE"]},
        "macro_series": ["DEXBZUS", "NOAA_ONI", "IRI_ENSO_FCST_3MO"],
        "weather_regions": ["brazil_coffee", "brazil_centro_sul"],
    },
    # --- utvidet univers (skreddersydde fingerprints, jf. config/instruments/) ---
    # Metaller
    "Silver": {"cot": {"types": ["disaggregated"], "contracts": ["SILVER"]},
               "macro_series": ["DGS10", "T10YIE", "DTWEXBGS"],
               "etf_tickers": ["slv"]},  # SLV-flyt = investerings-etterspørsel (etf_flow)
    "Platinum": {"cot": {"types": ["disaggregated"], "contracts": ["PLATINUM"]},
                 "macro_series": ["DGS10", "T10YIE", "DTWEXBGS"]},
    "Copper": {"cot": {"types": ["disaggregated"], "contracts": ["COPPER"]},
               "macro_series": ["BAMLH0A0HYM2", "DTWEXBGS", "VIXCLS"]},
    # Energi
    "WTI": {"cot": {"types": ["disaggregated"], "contracts": ["WTI-PHYSICAL"]},
            "macro_series": ["OVX", "DTWEXBGS"]},
    "Brent": {"cot": {"types": ["disaggregated"], "contracts": ["BRENT"]},
              "macro_series": ["OVX", "DTWEXBGS"]},
    "NatGas": {"cot": {"types": ["disaggregated"], "contracts": ["NAT GAS"]},
               "macro_series": ["DTWEXBGS"]},
    # Korn/softs
    "Corn": {"cot": {"types": ["disaggregated"], "contracts": ["CORN"]},
             "macro_series": ["DTWEXBGS", "NOAA_ONI", "DCOILWTICO"]},  # WTI = etanol-incentiv
    "Soybean": {"cot": {"types": ["disaggregated"], "contracts": ["SOYBEANS"]},
                "macro_series": ["DTWEXBGS", "NOAA_ONI"]},
    "Wheat": {"cot": {"types": ["disaggregated"], "contracts": ["WHEAT-SRW"]},
              "macro_series": ["DTWEXBGS", "NOAA_ONI"]},
    "Sugar": {"cot": {"types": ["disaggregated"], "contracts": ["SUGAR"]},
              "macro_series": ["DEXBZUS", "NOAA_ONI",
                               "ANP_ETANOL_HIDR_CS_BRL_LITER",      # etanol-paritet-input
                               "USDA_PSD_INDIA_SUGAR_ENDSTOCKS_KMT"]},  # India-balanse
    "Cocoa": {"cot": {"types": ["disaggregated"], "contracts": ["COCOA"]},
              "macro_series": ["DTWEXBGS", "NOAA_ONI"]},
    "Cotton": {"cot": {"types": ["disaggregated"], "contracts": ["COTTON"]},
               "macro_series": ["DTWEXBGS", "NOAA_ONI"]},
    # FX (COT-kontrakt = utenlandsk valuta vs USD; retning håndteres i fingerprintet)
    "GBPUSD": {"cot": {"types": ["tff", "legacy"], "contracts": ["BRITISH POUND"]},
               "macro_series": ["DGS10", "DGS2", "IRLTLT01GBM156N", "VIXCLS"]},
    "USDJPY": {"cot": {"types": ["tff", "legacy"], "contracts": ["JAPANESE YEN"]},
               "macro_series": ["DGS10", "DGS2", "IRLTLT01JPM156N", "VIXCLS"]},
    "AUDUSD": {"cot": {"types": ["tff", "legacy"], "contracts": ["AUSTRALIAN DOLLAR"]},
               "macro_series": ["DGS10", "IRLTLT01AUM156N", "DTWEXBGS", "VIXCLS"]},
    # Indeks
    "SP500": {"cot": {"types": ["tff", "legacy"], "contracts": ["E-MINI S&P 500"]},
              "macro_series": ["BAMLH0A0HYM2", "DGS10", "DGS2"]},
    "Nasdaq": {"cot": {"types": ["tff", "legacy"], "contracts": ["NASDAQ-100"]},
               "macro_series": ["BAMLH0A0HYM2", "DGS10", "DGS2"]},
    # Krypto (CME COT; høy-beta risk → dollar-likviditet + risk-sentiment + posisjonering)
    "BTCUSD": {"cot": {"types": ["tff", "legacy"], "contracts": ["BITCOIN"]},
               "macro_series": ["DTWEXBGS", "VIXCLS"]},
    "ETHUSD": {"cot": {"types": ["tff", "legacy"], "contracts": ["ETHER"]},
               "macro_series": ["DTWEXBGS", "VIXCLS"]},
}


def _ro_connect(path: Path = BEDROCK_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _distinct(conn: sqlite3.Connection, table: str, col: str) -> list[str]:
    rows = conn.execute(f"SELECT DISTINCT {col} FROM {table} ORDER BY {col}").fetchall()
    return [r[0] for r in rows if r[0] is not None]


def _resolve(values: list[str], candidates: list[str]) -> list[str]:
    """Finn faktiske verdier som matcher kandidat-substrings (case-insensitivt)."""
    low = {v.lower(): v for v in values}
    hits: list[str] = []
    for cand in candidates:
        cl = cand.lower()
        for vl, orig in low.items():
            if cl in vl and orig not in hits:
                hits.append(orig)
    return hits


def inspect(src: sqlite3.Connection) -> None:
    """Skriv ut tilgjengelige nøkler relevante for MVP — for å validere SEED_MAP."""
    print("== COT-kontrakter pr rapporttype ==")
    for rtype, m in COT_COLMAP.items():
        try:
            vals = _distinct(src, m["src_table"], "contract")
        except sqlite3.OperationalError:
            vals = ["<mangler>"]
        print(f"  {rtype} ({m['src_table']}): {vals}")
    print("\n== COMEX metals ==", _distinct(src, "comex_inventory", "metal"))
    print("== ETF tickers ==", _distinct(src, "etf_holdings", "ticker"))
    print("== Weather regions ==", _distinct(src, "weather", "region"))
    fmap = _distinct(src, "fundamentals", "series_id")
    wanted = {s for spec in SEED_MAP.values() for s in spec.get("macro_series", [])}
    print(f"\n== fundamentals: {len(fmap)} serier; ønskede til stede: "
          f"{sorted(wanted & set(fmap))}; mangler: {sorted(wanted - set(fmap))}")


def _log_seed(dst: sqlite3.Connection, src_tbl: str, dst_tbl: str, market: str | None,
              n: int) -> None:
    dst.execute(
        "INSERT OR REPLACE INTO seed_log(source_table,target_table,market,rows_seeded,seeded_at)"
        " VALUES (?,?,?,?,datetime('now'))",
        (src_tbl, dst_tbl, market, n),
    )


def _seed_cot(src: sqlite3.Connection, dst: sqlite3.Connection, market: str, spec: dict) -> int:
    total = 0
    for rtype in spec["types"]:
        cm = COT_COLMAP[rtype]
        try:
            contracts = _distinct(src, cm["src_table"], "contract")
        except sqlite3.OperationalError:
            continue
        matched = _resolve(contracts, spec["contracts"])
        if not matched:
            continue
        placeholders = ",".join("?" * len(matched))
        q = (
            f"SELECT report_date, {cm['long_spec']} AS ls, {cm['short_spec']} AS ss, "
            f"{cm['long_comm']} AS lc, {cm['short_comm']} AS sc, open_interest "
            f"FROM {cm['src_table']} WHERE contract IN ({placeholders})"
        )
        rows = src.execute(q, matched).fetchall()
        dst.executemany(
            "INSERT OR REPLACE INTO cot_positions"
            "(market,report_date,report_type,long_spec,short_spec,long_comm,short_comm,open_interest)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(market, r["report_date"], rtype, r["ls"], r["ss"], r["lc"], r["sc"],
              r["open_interest"]) for r in rows],
        )
        _log_seed(dst, cm["src_table"], "cot_positions", market, len(rows))
        total += len(rows)
        break  # første rapporttype med treff vinner (unngå dobbel-telling pr marked)
    return total


def _seed_macro(src: sqlite3.Connection, dst: sqlite3.Connection, series: list[str]) -> int:
    if not series:
        return 0
    placeholders = ",".join("?" * len(series))
    rows = src.execute(
        f"SELECT series_id, date, value FROM fundamentals WHERE series_id IN ({placeholders})",
        series,
    ).fetchall()
    dst.executemany(
        "INSERT OR REPLACE INTO macro_series(series_id,date,value) VALUES (?,?,?)",
        [(r["series_id"], r["date"], r["value"]) for r in rows],
    )
    _log_seed(dst, "fundamentals", "macro_series", None, len(rows))
    return len(rows)


def _seed_comex(src: sqlite3.Connection, dst: sqlite3.Connection, metals: list[str]) -> int:
    if not metals:
        return 0
    n = 0
    for metal in metals:
        rows = src.execute(
            "SELECT metal,date,registered,eligible,total,units FROM comex_inventory WHERE metal=?",
            (metal,),
        ).fetchall()
        dst.executemany(
            "INSERT OR REPLACE INTO comex_inventory(metal,date,registered,eligible,total,units)"
            " VALUES (?,?,?,?,?,?)",
            [(r["metal"], r["date"], r["registered"], r["eligible"], r["total"], r["units"])
             for r in rows],
        )
        n += len(rows)
    _log_seed(dst, "comex_inventory", "comex_inventory", None, n)
    return n


def _seed_weather(src: sqlite3.Connection, dst: sqlite3.Connection, candidates: list[str]) -> int:
    if not candidates:
        return 0
    regions = _resolve(_distinct(src, "weather", "region"), candidates)
    if not regions:
        return 0
    placeholders = ",".join("?" * len(regions))
    rows = src.execute(
        f"SELECT region,date,tmax,tmin,precip,gdd FROM weather WHERE region IN ({placeholders})",
        regions,
    ).fetchall()
    dst.executemany(
        "INSERT OR REPLACE INTO weather(region,date,tmax,tmin,precip,gdd) VALUES (?,?,?,?,?,?)",
        [(r["region"], r["date"], r["tmax"], r["tmin"], r["precip"], r["gdd"]) for r in rows],
    )
    _log_seed(dst, "weather", "weather", None, len(rows))
    return len(rows)


def _seed_etf(src: sqlite3.Connection, dst: sqlite3.Connection, candidates: list[str]) -> int:
    if not candidates:
        return 0
    tickers = _resolve(_distinct(src, "etf_holdings", "ticker"), candidates)
    if not tickers:
        return 0
    placeholders = ",".join("?" * len(tickers))
    rows = src.execute(
        f"SELECT ticker,date,tonnes_in_trust,shares_outstanding FROM etf_holdings "
        f"WHERE ticker IN ({placeholders})",
        tickers,
    ).fetchall()
    dst.executemany(
        "INSERT OR REPLACE INTO etf_holdings(ticker,date,tonnes_in_trust,shares_outstanding)"
        " VALUES (?,?,?,?)",
        [(r["ticker"], r["date"], r["tonnes_in_trust"], r["shares_outstanding"]) for r in rows],
    )
    _log_seed(dst, "etf_holdings", "etf_holdings", None, len(rows))
    return len(rows)


def _seed_unica_mix(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    """UNICA Brasil C-S sukker-mix % → macro_series (sukker-spesifikk tilbudsdriver)."""
    try:
        rows = src.execute(
            "SELECT report_date, mix_sugar_pct FROM unica_reports "
            "WHERE mix_sugar_pct IS NOT NULL ORDER BY report_date"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    dst.executemany(
        "INSERT OR REPLACE INTO macro_series(series_id,date,value) "
        "VALUES ('UNICA_MIX_SUGAR_PCT',?,?)",
        [(r["report_date"], r["mix_sugar_pct"]) for r in rows],
    )
    _log_seed(dst, "unica_reports", "macro_series", "Sugar", len(rows))
    return len(rows)


def seed(db_path: Path | str = store.DEFAULT_DB_PATH,
         bedrock_db: Path = BEDROCK_DB) -> dict[str, int]:
    """Seed alle MVP-instrumenter. Returnerer total radtelling pr måltabell."""
    counts = {"cot_positions": 0, "macro_series": 0, "comex_inventory": 0,
              "weather": 0, "etf_holdings": 0}
    src = _ro_connect(bedrock_db)
    try:
        with store.connect(db_path) as dst:
            store.init_db(dst)
            for market, spec in SEED_MAP.items():
                if "cot" in spec:
                    counts["cot_positions"] += _seed_cot(src, dst, market, spec["cot"])
                counts["macro_series"] += _seed_macro(src, dst, spec.get("macro_series", []))
                counts["comex_inventory"] += _seed_comex(src, dst, spec.get("comex_metals", []))
                counts["weather"] += _seed_weather(src, dst, spec.get("weather_regions", []))
                counts["etf_holdings"] += _seed_etf(src, dst, spec.get("etf_tickers", []))
            # Sukker-spesifikk Brasil-mix (egen tabell i bedrock → macro_series).
            counts["macro_series"] += _seed_unica_mix(src, dst)
    finally:
        src.close()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed Regnbue-bias fra bedrock.db (lese-only).")
    ap.add_argument("--inspect", action="store_true", help="Vis tilgjengelige nøkler, ikke seed.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH), help="Mål-datastore.")
    args = ap.parse_args()

    if args.inspect:
        src = _ro_connect()
        try:
            inspect(src)
        finally:
            src.close()
        return

    counts = seed(args.db)
    print("Seed ferdig:")
    for tbl, n in counts.items():
        print(f"  {tbl}: {n}")


if __name__ == "__main__":
    main()
