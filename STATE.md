# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-05-30
**Nåværende fase:** **ALLE FASER (0–7) FERDIG — LIVE.** https://snkpipefish.github.io/regnbue/ · repo: github.com/Snkpipefish/regnbue

## K1-resultat (2026-05-30) — løst positivt
cTrader-spike (`scripts/ctrader_depth_spike.py`, read-only, demo) viste **dyp D1-historikk** på Skilling:
Gull (GOLD) ~28 år, Olje (OIL WTI) ~20 år, Indeks (SPX500) ~14 år. Token gyldig, demo-konto 32290195,
1344 symboler. **→ K3 løst:** regn både nivåer OG base-rate på Skilling-feed (ett koordinatsystem).
Skilling-tickere: `GOLD`(41), `OIL WTI`(99), `OIL BRENT`, `SPX500`(203).

## OOS-validering (2026-05-30) — `python -m setups.validate` — ÆRLIG FUNN
Tesen-test på data aldri tunet på. To likhetsmål prøvd (én gang hver, prinsipielt — ikke OOS-tuning):
1. **4D-nærmeste-nabo (sim 0.15):** gull «77 % fortegns-treff» — MEN kun n=31 datoer hadde ≥30 naboer.
   Småutvalg-artefakt fra glisne klynger (curse of dimensionality).
2. **Score-bånd + retning (band 0.10) [nåværende, korrekt metode]:** naboer for ~alle datoer (n≈590).
   - Gull: fortegns-treff **55 %** (nær myntkast); pred+ +0.62R vs pred− +0.33R.
   - EURUSD: **43 %** (verre enn tilfeldig). Coffee: 54 %, invertert.
   - **Gaten publiserer 0 OOS** — treffrate ~49–55 %, Wilson-nedre når aldri 55 %.

**Konklusjon: ingen påvist OOS-edge i nåværende drivere.** Gaten som publiserer 0 er KORREKT —
systemet nekter å lure oss (audit K2/V3/V4 virker etter hensikten). Den tilsynelatende gull-edgen
var støy. **IKKE pirk mer på terskler/likhet (= p-hacking på OOS).** Ekte vei videre = bedre/flere
*prediktive* drivere, så valideres på nytt. Det er et forsknings-/retningsvalg for brukeren.

## Neste konkrete steg (etter-MVP / drift)
- Observer at systemd-timeren publiserer hver 6. time (`journalctl --user -u setups.service`).
- **Spissing/forbedring:** flere drivere (GVZ/DXY/ENSO egne fetchere), gamma BTC/ETH (Deribit), validér gate på OOS.
- **Skalér forbi MVP:** flere instrumenter (alle 22) når tesen er bekreftet på Gull/EURUSD/Kaffe.
- Vurdér: full historikk vs train-panel som naboer; optimalisér panel-bygg (~55s/instr).

## Drift
- Manuell publisering: `./update.sh`. Pipeline: `python -m setups.run`.
- Full re-seed/henting: `python -m setups.seed`; `python -m setups.ctrader_prices GOLD EURUSD Coffee --years 15`.
- Timer: `systemctl --user {status,start,stop} setups.timer`.

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
- **Fase 5–6:** `publish.py` + `run.py` (→ `web/data/setups.json`, committes for Pages — `/data/` ignoreres, ikke `web/data/`),
  `web/index.html` (regnbue-UI, vanilla JS, visuelt verifisert). `pytest` 28 grønne + 1 skip.
  Kjørt 2026-05-28: 3 signaler, 0 publisert (ærlig gate). MVP fase 0–6 komplett lokalt.

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
