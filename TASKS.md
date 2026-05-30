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

## Fase 5 — publisering
- [ ] `publish.py` → `web/data/setups.json` (schema_version + generated)

## Fase 6 — UI
- [ ] `web/index.html` beslutnings-UI (regnbue-tema)

## Fase 7 — live
- [ ] `update.sh` + systemd-timer
- [ ] opprett public GitHub-repo + Pages + første push
