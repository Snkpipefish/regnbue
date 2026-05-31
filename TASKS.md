# Regnbue — TASKS (kryss av underveis)

Detaljer per fase i `PLAN.md §8`. Kryss av straks ferdig. **MVP = 3 instrumenter: Gull, EURUSD, Kaffe.**

## Fase −1 — GATE (audit K1): mål cTrader-historikk ✅ FERDIG 2026-05-30
- [x] Read-only cTrader-spike (`scripts/ctrader_depth_spike.py`): Gull ~28år, Olje ~20år, Indeks ~14år
- [x] K3 avgjort: dyp historikk → **både nivåer og base-rate på Skilling-feed** (ett koordinatsystem)
- [x] Skilling-tickere: GOLD(41), OIL WTI(99), OIL BRENT, SPX500(203); demo-konto 32290195, 1344 symboler

## Fase 0 — oppsett ✅ FERDIG 2026-05-30
- [x] git-repo + `pyproject.toml` (pandas, pydantic, pyyaml, requests; dev: ruff/pytest; extra: ctrader)
- [x] `src/setups/secrets.py` (leser `~/.bedrock/secrets.env`, env-override + `REGNBUE_SECRETS_ENV`)
- [x] ruff + pytest grønn (`tests/test_smoke.py`: import + env-override-test). `scripts/` ekskl. fra ruff

## Fase 1 — datastore + seed ✅ FERDIG 2026-05-30
- [x] `store.py` (SQLite): normalisert bias-schema (cot_positions/macro_series/comex/weather/etf + seed_log)
- [x] `seed.py` engangs lese-only fra `bedrock.db`: Gull/Kaffe COT 856 (2010→), EURUSD 542 (2016→),
      makro 37k rader, ENSO/DEXBZUS for kaffe. NB: vær + COMEX grunne i bedrock (fetch-lag fyller i fase 2)
- [x] `test_store.py` data-integritet + idempotens (6 tester grønne)

## Fase 2 — fetch + nivå-feed ✅ FERDIG 2026-05-30
- [x] `ctrader_prices.py` — read-only OHLC fra Skilling (NIVÅ-feed). Live testet: GOLD/EURUSD/Coffee
      D1 hentet (2 år), OHLC fornuftig. Tickere: GOLD, EURUSD, **Coffee** (ikke COFFEE)
- [x] `fetch/fred.py` lean makro-henter (FRED_API_KEY), live testet (DGS10). NB: DXY/GVZ/ENSO-fetchere
      utsatt til driverne defineres (fase 3) — de er ikke FRED i bedrock

## Fase 3 — scoring ✅ FERDIG 2026-05-30
- [x] `score/` egen driver-registry (@register) + motor + grade + explain-trace + as-of-context
      (drivere: level_percentile, momentum, series_spread_percentile, price_vs_sma, cot_spec_net_percentile)
- [x] 3 fingerprint-YAML (`config/instruments/`: gold, eurusd, coffee). Live-kjørt mot seedet db:
      alle 4 drivere fyrer pr instrument, koherente traces, NEUTRAL på 2026-05-28
- [x] logiske tester (17 grønne): as-of-vern, persentil-ekstrem, vekt-renormalisering, grade-terskler

## Fase 4 — setups + base-rate ✅ FERDIG 2026-05-30 (kjerne)
- [x] `generator.py` reelle nivåer (fraktal-swing + runde tall) på Skilling-koordinat, entry/SL(buffer×ATR)/TP, R:R-floor
- [x] `outcomes.py` triple-barrier i R + ATR + look-ahead-trygt panel (score-vektor + utfall), OOS-merking
- [x] `test_gate.py` beviser look-ahead-vern (utfall ignorerer bevegelser etter horisont; as-of-trygt panel) — GRØNT
- [x] `gate.py` base-rate-gatekeeper: likhetsterskel + effektiv n + **Wilson nedre CI** på hit-rate + expectancy-CI (audit K2)
- [x] Ende-til-ende verifisert på ekte data: alle 3 korrekt IKKE publisert (svakt signal + for få analoger) — ærlig gate
- [ ] spiss de 3 MVP-fingerprintene (løpende; terskler LÅST før resultater — tunes ikke for å tvinge publisering)
- Åpent: (a) panel-bygg ~55s/instrument (re-scorer pr dato) — optimaliser ved behov; (b) runtime bruker
  kun train-panel som naboer (OOS ekskludert) → færre analoger; vurder full historikk for live-beslutning

## Fase 5 — publisering ✅ FERDIG 2026-05-30
- [x] `publish.py` → `web/data/setups.json` (schema_version, generated ISO, as_of, signals[] m/ base-rate+drivere)
- [x] `run.py` binder score→generator→gate→publish (panel pr instrument). JSON-kontrakt-test grønn

## Fase 6 — UI ✅ FERDIG 2026-05-30
- [x] `web/index.html` beslutnings-UI (regnbue-tema, vanilla JS): setup-kort m/ entry/SL/T1/R:R,
      base-rate-badge (n+CI+R), driver-chips → modal, forkastede m/grunn. Visuelt verifisert (screenshot)

## Fase 7 — live ✅ FERDIG 2026-05-30
- [x] `update.sh` (flock + fersk fetch + run + commit/rebase/push kun ved endring)
- [x] `systemd/setups.{service,timer}` (user-units, hver 6h) + `.github/workflows/pages.yml` (deploy web/)
- [x] public repo **github.com/Snkpipefish/regnbue** opprettet + pushet; Pages live (Actions-deploy)
- [x] systemd-user-timer aktivert (linger på) — kjørte første runde OK via timeren
- **LIVE:** https://snkpipefish.github.io/regnbue/ (index 200, data/setups.json 200)
- **NB (2026-05-31): timeren er nå DEAKTIVERT** (ressurssparing). Re-aktiver ved behov.

## Etter-MVP — scenario-generator ✅ FERDIG 2026-05-31
- [x] `scenario.py` FHS (EWMA-vol + block bootstrap) + CRPS/PIT-kalibrering + residual-klipp
- [x] `scenario_fm.py` Chronos-utfordrer (zero-shot, valgfri `[fm]`) + `scenario_arbitrate.py` ruting
- [x] Chronos vinner 20/22 på OOS-CRPS → `web/data/scenario_models.json`
- [x] `clean.py` reparerer skala-glitcher (50 SPX500-barer), koblet inn i `update.sh`
- [x] 22 instrumenter med pris/COT/makro seedet; tester 38 grønne

## NESTE: instrument-tilpasning (sukker-metoden) — ett om gangen
Se playbook i `STATE.md`. Pr instrument: research → skaff dyp data → hånd-skriv fundamentalt fingerprint
(fjern fra `gen_universe_fingerprints.py`) → verifiser scoring → ev. scenario/kalibrering.
- [x] **Sugar** — ferdig mal (series_ratio energi/sukker, rainfall_anomaly, ENSO, BRL, COT, UNICA)
- [x] **gold** — realrente (DGS10−T10YIE), bred dollar (DTWEXBGS), **GLD ETF-flyt (ny `etf_flow`-driver)**, COT.
      Fjernet generisk `price_vs_sma`. Verifisert: 2020/2022/2018-vendepunkter koherente. 40 tester grønne.
- [x] **eurusd** — US−DE 10y rentespread, US 2y-momentum (Fed-forventninger), COT EUR, VIX risk-sentiment.
      Fjernet `price_vs_sma` + sirkulær DTWEXBGS. Verifisert: 2022/2025 SHORT, 2017 LONG — koherent.
- [x] **coffee** — frost (`frost_anomaly`, ny driver, Sul de Minas kaldeste natt m/abs-gate),
      nedbør-anomali (dyp Open-Meteo 2000→), BRL (DEXBZUS), COT. Fjernet `price_vs_sma` + tvetydig ENSO.
      Verifisert: juli-2021-frosten fyrer (3.2°C, z=-2.76); sommer-kjøling gated til 0. Skilling-pris kun ~5 år.
- [x] **silver** — realrente, bred dollar, SLV ETF-flyt (via shares_outstanding-fallback), COT.
- [x] **platinum** — platina/gull-relativverdi (ny `price_ratio`-driver), COT, dollar, realrente (lav vekt).
- [x] **copper** — dollar, HY-kredittspread (vekst), COT, VIX risk-sentiment. NB data tynn (pris 2023→).
- [x] **wti** — EIA crude-lager vs sesong-norm (ny `seasonal_anomaly` + ny EIA-fetcher), COT, dollar, OVX.
- [x] **brent** — samme som WTI (US-lager som global-proxy); Brent-COT grunn (2022→), renormaliserer pent.
- [x] **natgas** — EIA gass-lager vs sesong-norm + degree-days vær-etterspørsel (ny `degree_days_anomaly`,
      dyp Chicago-vær), COT. NB pris kun 2019→. Verifisert: 2024-02 SHORT A+ (mild vinter + glut).
- [x] **corn** — kornbelte-vær (sesong-gated mai–sep), etanol/olje (DCOILWTICO), dollar, COT.
- [x] **soybean** — kornbelte-vær (jun–sep), dollar, COT.
- [x] **wheat** — sletteland-vær (apr–jun), dollar, COT.
- [x] **cocoa** — Vest-Afrika-vær, ENSO (El Niño=bull), COT. Fanger 2023–24 supply-krisen (LONG A).
- [x] **cotton** — bomullsbelte-vær (jun–sep), dollar, COT.
  Ny `active_months`-sesong-gate på rainfall_anomaly; dyp Open-Meteo for 4 nye avlings-regioner.
- [ ] gbpusd, usdjpy, audusd
- [ ] sp500, nasdaq
- [ ] btcusd, ethusd
