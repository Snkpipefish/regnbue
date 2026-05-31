# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-05-31
**Nåværende fase:** MVP live + scenario-generator bygget. **Neste: instrument-tilpasning for resten (egne drivere pr instrument).**
**Live:** https://snkpipefish.github.io/regnbue/ · repo: github.com/Snkpipefish/regnbue (konto Snkpipefish)

---

## 🎯 NESTE OPPGAVE (for nytt vindu): tilpass hvert instrument som vi gjorde med sukker
Mål: gi hvert instrument **ekte, instrument-spesifikke fundamentale drivere** (ikke generisk pris-trend),
forankret i online-research, og bruk **kun data vi faktisk har / kan hente**. Ett instrument om gangen.

> VIKTIG: sukker er IKKE en driver-mal. Sukkerets drivere (etanol/cane/Brasil) er unike og
> gjelder ikke andre instrumenter. Det som er felles er PROSESSEN under — ikke driverne. Hvert
> instrument må researches på nytt og få sine EGNE drivere.

### Tilpasnings-prosessen (playbook — følg denne pr instrument)
1. **Research online** (WebSearch/WebFetch): hva beveger *faktisk* instrumentet i den virkelige verden
   (årsakskjede), og hvilken konkret datakilde gir det signalet. Få fortegnet riktig (bull_when).
2. **Sjekk hva vi har:** `python -m setups.seed --inspect` + spør `data/regnbue.db`
   (macro_series, cot_positions, prices, weather). Se også `DATA_KARTLEGGING.md`.
3. **Skaff dyp data** (grunne drivere svekker base-rate — foretrekk lange serier):
   - FRED-serier finnes i bedrock `fundamentals` → legg i `seed.py` SEED_MAP[instr]["macro_series"], re-seed.
     Eller hent ferskt: `setups.fetch.fred` (utvid `MVP_SERIES` el. kall `update_macro_series([...])`).
   - Spesialtabeller i bedrock (f.eks. UNICA) → egen seed-funksjon i `seed.py` (se `_seed_unica_mix`).
   - Vær: `setups.fetch.weather` (Open-Meteo, gratis, dyp; legg region i `REGIONS`).
   - Avledede dype proxyer når direkte data er grunt (sukker brukte WTI÷IMF-sukker via `series_ratio`).
4. **Skriv fingerprintet for hånd** i `config/instruments/<id>.yaml` — KUN fundamentale drivere.
   **Fjern instrumentet fra `scripts/gen_universe_fingerprints.py` SPEC** så det ikke overskrives.
5. **Verifiser:** score ende-til-ende på flere historiske datoer (alle drivere ok / faller pent til NA).
6. (Valgfritt) **Scenario/kalibrering:** `setups.scenario`/`scenario_arbitrate` gir forward-fordelingen.
   NB funn under: fundamental-score forutsier IKKE retning godt — valider OOS før du tror på noe.

**Rapporteringsregel (etterprøvbar, ikke moralsk):** valider OOS; oppgi n + konfidensintervall; juster
ALDRI terskler/likhet etter å ha sett resultater; marker tydelig når noe ikke har påvist edge; publiser
ingen setup uten statistisk støtte.

### Hånd-tilpasset status
- ✅ **Sugar** — ferdig som PROSESS-EKSEMPEL (ikke driver-mal). Sukker-unike drivere: `series_ratio`
  (WTI÷IMF-sukker = etanol-incentiv), `rainfall_anomaly` (Brasil C-S), ENSO, BRL, COT, UNICA-mix. Andre
  instrumenter får helt andre drivere.
- ⚠️ **gold, eurusd, coffee** — håndskrevet men fortsatt semi-generisk (bruker price_vs_sma o.l.). Bør tilpasses ordentlig.
- ⚠️ **18 øvrige** (silver, platinum, copper, wti, brent, natgas, corn, soybean, wheat, cocoa, cotton,
  gbpusd, usdjpy, audusd, sp500, nasdaq, btcusd, ethusd) — generisk, generert av `gen_universe_fingerprints.py`.

### Gjenbrukbare drivere (registrert i `score/drivers.py`)
`level_percentile`, `momentum`, `price_momentum`, `series_spread_percentile`, `price_vs_sma`,
`cot_spec_net_percentile`, `ethanol_parity`, `series_ratio`, `rainfall_anomaly`. Lag nye ved behov med `@register`.

---

## HOVEDFUNN (ikke gjenta feilene)
- **Fundamentale lineære scorer forutsier IKKE forward-avkastning** på 30–120d (kalibrering flat/invertert,
  sjekket for sukker på flere horisonter). Base-rate-gaten publiserer ~0 — det er KORREKT, ikke en bug.
- **IKKE pirk på terskler/likhet for å tvinge publisering** (= p-hacking på OOS).
- Det som er reelt: (a) **trendfølging** diversifisert (~0.65 Sharpe brutto, in-sample) — men per instrument er det støy;
  (b) **scenario-generatoren** (kalibrert fordeling), ikke retnings-orakel.

## Scenario-generator (bygget 2026-05-31)
- `scenario.py` — FHS (EWMA-vol + standardiserte residualer + stationary block bootstrap) → betinget
  forward-fordeling. Evaluert med **CRPS + PIT-kalibrering**. Robust mot glitcher (klipper residualer ±8σ).
- `scenario_fm.py` — foundation-modell-utfordrer **Chronos** (zero-shot). Valgfri extra `[fm]` (torch).
- `scenario_arbitrate.py` — **kalibrerings-arbitrasje**: rut per instrument til best-kalibrerte modell.
  Resultat: **Chronos vinner 20/22** på OOS-CRPS. → `web/data/scenario_models.json`. Faller til FHS uten torch.
- `clean.py` — reparerer skala-glitcher (fikset 50 SPX500-barer ×10-feil); kjøres i `update.sh` etter henting.

## Drift / kommandoer
- Pipeline (setups.json): `python -m setups.run` · publiser: `./update.sh` (henter+vasker+kjører+pusher).
- Re-seed: `python -m setups.seed` · priser: `python -m setups.ctrader_prices <TICKERE> --years 15` (alle 22 i db nå).
- Makro: `python -m setups.fetch.fred` · vær: `python -m setups.fetch.weather`.
- Scenario-ruting: `python -m setups.scenario_arbitrate` (krever `[fm]` for Chronos, ellers FHS-only).
- Validering: `python -m setups.validate` (treg, ~30–60s/instr).
- **NB: systemd-timeren er DEAKTIVERT** (slått av for å spare ressurser). Re-aktiver:
  `systemctl --user enable --now setups.timer`.

## Tilstand
- 22 instrumenter med pris (cleaned), COT, makro seedet i `data/regnbue.db` (git-ignorert, regenereres).
- `ruff` rent, `pytest` **38 grønne + 1 skip**. Alt committet.
- Pages live via GitHub Actions-deploy fra `web/`.

## Data / API (detaljer i `DATA_KARTLEGGING.md`)
- Nøkler i `~/.bedrock/secrets.env`: cTrader, FRED, EIA, FAS/USDA/api.data.gov (samme), NASS, AGSI.
- Brukt: cTrader (priser) + FRED (makro) live; resten seedet fra `~/bedrock/bedrock.db`.
- Ikke-wiret ennå: EIA, FAS/PSD, NASS, AGSI, LBMA, CBOE, Deribit, Baker Hughes m.fl. (kandidater for tilpasning).

## Åpne spørsmål
- Skal scenario-generatoren bli hoved-produktet (ærlig fordeling) framfor «setups»? (UI viser i dag setups.json.)
- Kovariat-betinget foundation-modell (Moirai) — utsatt: vårt bevis tilsier kovariatene ikke bærer forward-info.
- Full historikk vs train-panel som naboer i base-rate-gaten.

## K1-resultat (2026-05-30) — løst positivt
cTrader-spike viste dyp D1-historikk: Gull ~28 år, Olje ~20 år, Indeks ~14 år. Skilling demo-konto 32290195.
→ K3 låst: regn både nivåer OG base-rate på Skilling-feed.
