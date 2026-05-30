# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-05-30
**Nåværende fase:** **Fase 0–4 ferdig** (stillas, data, nivå-feed, scoring, base-rate-gate). Neste: fase 5 (publish).

## K1-resultat (2026-05-30) — løst positivt
cTrader-spike (`scripts/ctrader_depth_spike.py`, read-only, demo) viste **dyp D1-historikk** på Skilling:
Gull (GOLD) ~28 år, Olje (OIL WTI) ~20 år, Indeks (SPX500) ~14 år. Token gyldig, demo-konto 32290195,
1344 symboler. **→ K3 løst:** regn både nivåer OG base-rate på Skilling-feed (ett koordinatsystem).
Skilling-tickere: `GOLD`(41), `OIL WTI`(99), `OIL BRENT`, `SPX500`(203).

## Neste konkrete steg
**Fase 5:** `publish.py` → `web/data/setups.json` (schema_version + generated + signals[] med entry/SL/TP/R:R,
grade, base-rate-badge n+CI, forkastede m/grunn, driver-trace). Bygg en `run.py` som binder
fetch→score→generator→gate→publish. NB: panel-bygg er tregt (~55s/instr) — vurder caching av panel i run.

### Status (2026-05-30)
- **Fase 0:** git (branch `main`), `.gitignore`, `pyproject.toml` (src-layout), `secrets.py` (env overstyrer fil),
  `.venv` med `-e .[dev]`. Lagringsformat låst = SQLite.
- **Fase 1:** `store.py` (SQLite, normalisert bias-schema), `seed.py` (lese-only fra `bedrock.db`).
  Seedet `data/regnbue.db`: COT Gull/Kaffe 856 + EURUSD 542, makro 37k, ETF gld 5593, COMEX gold 17, vær 63.
  - **Merk:** bedrock `weather` (siste ~måned) og `comex_inventory` (17 rader) er grunne → fase 2 fetch holder ferskt.
  - Realrente for gull avledes senere som DGS10 − T10YIE (DFII10 finnes ikke i bedrock).
- **Fase 2:** `ctrader_prices.py` (NIVÅ-feed, read-only D1-OHLC via cTrader, token-refresh innebygd) +
  `fetch/fred.py` (makro). Skilling-tickere MVP: **GOLD, EURUSD, Coffee**. Hent priser:
  `python -m setups.ctrader_prices GOLD EURUSD Coffee --years 15`; makro: `python -m setups.fetch.fred`.
- **Fase 3:** `score/` (context as-of, drivers @register, engine, grade). Fingerprints i `config/instruments/`.
  Drivere bygd på seedet data; realrente = DGS10−T10YIE, EURUSD rentediff = DGS10−IRLTLT01DEM156N, kaffe = ENSO(NOAA_ONI)+DEXBZUS.
  Kjør: `python -m setups.score`... (via engine.load_fingerprint('gold'|'eurusd'|'coffee')).
- **Fase 4:** `outcomes.py` (triple-barrier i R, ATR, look-ahead-trygt panel, OOS-merking),
  `gate.py` (likhetsnaboer + effektiv n + Wilson nedre-CI + expectancy-CI), `generator.py` (fraktal-swing +
  runde nivåer, entry/SL/TP, R:R-floor). Dyp historikk hentet: GOLD 3783 / EURUSD 4016 / **Coffee 1230 (~5 år)**.
  Ende-til-ende på 2026-05-28: alle 3 korrekt IKKE publisert (svakt signal + for få analoger) — gate fungerer.
- `ruff` rent, `pytest` **26 grønne** + 1 skip (live FRED). `data/regnbue.db` git-ignorert.
- Terskler LÅST (audit V3): similarity 0.15, effektiv n≥30, hit-rate≥55% (nedre CI), expectancy≥0.3R. Tunes IKKE for å tvinge publisering.

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
