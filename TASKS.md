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

## Fase 1 — datastore + seed
- [ ] `store.py` (SQLite)
- [ ] seed bias-historikk fra `~/bedrock/bedrock.db` (COT/FRED/vær/COMEX, lese-only)

## Fase 2 — fetch + nivå-feed
- [ ] `ctrader_prices.py` — read-only OHLC fra Skilling (NIVÅ-feed), test token live
- [ ] `fetch/` lean bias-data via gjenbrukte API-nøkler (kun høyverdi-kilder)

## Fase 3 — scoring
- [ ] `score/` egen driver-registry + motor + grade + explain
- [ ] 3 fingerprint-YAML (Gull, EURUSD, Kaffe)

## Fase 4 — setups + base-rate
- [ ] `generator.py` reelle nivåer (swing/round/prior) på Skilling-koordinat (gamma: kun BTC/ETH, post-MVP)
- [ ] `outcomes.py` forward-return/MaxDD (regnes ferskt; OOS-holdout siste 2–3 år)
- [ ] `test_gate.py` beviser look-ahead-vern FØR base-rate brukes (audit V4)
- [ ] `gate.py` base-rate-gatekeeper: likhetsterskel + effektiv n ~30+ + konfidensintervall (audit K2)
- [ ] spiss de 3 MVP-fingerprintene

## Fase 5 — publisering
- [ ] `publish.py` → `web/data/setups.json` (schema_version + generated)

## Fase 6 — UI
- [ ] `web/index.html` beslutnings-UI (regnbue-tema)

## Fase 7 — live
- [ ] `update.sh` + systemd-timer
- [ ] opprett public GitHub-repo + Pages + første push
