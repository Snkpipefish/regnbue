# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-05-30
**Nåværende fase:** **Fase 0–1 ferdig** (stillas + datastore + seed). Kjører videre mot fase 2 sammenhengende.

## K1-resultat (2026-05-30) — løst positivt
cTrader-spike (`scripts/ctrader_depth_spike.py`, read-only, demo) viste **dyp D1-historikk** på Skilling:
Gull (GOLD) ~28 år, Olje (OIL WTI) ~20 år, Indeks (SPX500) ~14 år. Token gyldig, demo-konto 32290195,
1344 symboler. **→ K3 løst:** regn både nivåer OG base-rate på Skilling-feed (ett koordinatsystem).
Skilling-tickere: `GOLD`(41), `OIL WTI`(99), `OIL BRENT`, `SPX500`(203).

## Neste konkrete steg
**Fase 2:** `ctrader_prices.py` — read-only OHLC fra Skilling (NIVÅ-feed), test token live (mønster fra
`scripts/ctrader_depth_spike.py`). Deretter `fetch/` lean bias-data via gjenbrukte API-nøkler (kun høyverdi).

### Status (2026-05-30)
- **Fase 0:** git (branch `main`), `.gitignore`, `pyproject.toml` (src-layout), `secrets.py` (env overstyrer fil),
  `.venv` med `-e .[dev]`. Lagringsformat låst = SQLite.
- **Fase 1:** `store.py` (SQLite, normalisert bias-schema), `seed.py` (lese-only fra `bedrock.db`).
  Seedet `data/regnbue.db`: COT Gull/Kaffe 856 + EURUSD 542, makro 37k, ETF gld 5593, COMEX gold 17, vær 63.
  - **Merk:** bedrock `weather` (siste ~måned) og `comex_inventory` (17 rader) er grunne → fase 2 fetch holder ferskt.
  - Realrente for gull avledes senere som DGS10 − T10YIE (DFII10 finnes ikke i bedrock).
- `ruff` rent, `pytest` 6 grønne. `data/regnbue.db` er git-ignorert (regenereres via `python -m setups.seed`).

## Hva er gjort
- Kartlagt #1/#2, skrevet alle plan-/datadokumenter.
- Datakartlegging (D0) ferdig; verifisert API-nøkler (EIA 14 datasett, FAS PSD+ESR, api.data.gov).
- **Audit #1 ferdig** (`AUDIT.md`) — avdekket K1–K4 (kritisk). Beslutninger oppdatert i `DECISIONS.md`.

## Beslutninger fra audit (2026-05-30)
- **No-copy beholdes, men MVP = 3 instrumenter:** Gull, EURUSD, Kaffe (bevis tesen før alle 22).
- Gate-statistikk skjerpes: likhetsterskel + effektiv n (~30+) + konfidensintervall (ikke 5-nabo-punktestimat).
- Out-of-sample holdout (siste 2–3 år) tunes aldri på. Look-ahead-test før base-rate brukes.
- Koordinat-konsistens (K3) avgjøres av K1: én feed for både nivå og base-rate, ELLER futures-relative nivåer.
- Gamma kun BTC/ETH (Deribit) i/etter MVP; indeks/GLD/SLV/USO-gamma utsatt.
- Outcomes regnes ferskt (unntak fra seed-engangs) — 5 instrumenter mangler uansett i `analog_outcomes`.

## Åpne spørsmål
- K1-svar: hvor mange år D1 gir Skilling/cTrader? (avgjør K3 + om "base-rate på broker-feed" holder)
- Base-rate-terskler: settes og LÅSES før resultater ses (mot OOS).
- Lagringsformat: SQLite (foreslått) vs parquet.
