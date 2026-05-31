# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-05-31 (9 instr fundamentalt tilpasset: + energi wti/brent/natgas)
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
- ✅ **gold** (2026-05-31) — fundamentalt tilpasset, generisk pris-trend fjernet. Gull-unike drivere:
  realrente `series_spread_percentile` (DGS10−T10YIE, lav=bull, 0.35), bred dollar `momentum` (DTWEXBGS, 0.20),
  **`etf_flow`** (ny driver: GLD tonnes-in-trust flyt, inn=bull, 0.25), COT (0.20). GLD-data dyp (2004→).
  Verifisert: 2020-08 LONG / 2022-09 SHORT / 2018-06 SHORT — koherent med faktiske vendepunkter.
- ✅ **eurusd** (2026-05-31) — fundamentalt tilpasset. Drivere: US−DE 10y rentespread
  `series_spread_percentile` (DGS10−IRLTLT01DEM156N, lav=bull, 0.35), US 2y `momentum` (Fed-forventninger,
  lav=bull, 0.25), COT EUR (0.20), `level_percentile` VIXCLS (risk-off=USD-bud=bear, lav=bull, 0.20). Fjernet
  generisk `price_vs_sma` OG sirkulær DTWEXBGS-momentum (≈invers av EURUSD selv). Verifisert: 2022/2025 SHORT, 2017 LONG.
- ✅ **coffee** (2026-05-31) — fundamentalt tilpasset. Drivere: `frost_anomaly` (ny: Sul de Minas kaldeste
  natt vs sesong-baseline + absolutt kulde-gate så sommer-kjøling ikke fyrer, 0.30), `rainfall_anomaly`
  (samme region, 0.20), BRL `momentum` (DEXBZUS, lav=bull, 0.25), COT (0.25). Fjernet `price_vs_sma` +
  tvetydig ENSO. Dyp vær hentet via Open-Meteo (`brazil_sul_minas`, 2000→, lagt i `fetch.weather` REGIONS).
  NB: Skilling-pris kun ~5 år → base-rate-gaten avviser ærlig (korrekt). Verifisert juli-2021-frost fyrer.
- ✅ **silver** (2026-05-31) — realrente (DGS10−T10YIE), bred dollar, **SLV `etf_flow`** (SLV mangler tonn i
  kilden → la til `shares_outstanding`-kolonne + COALESCE-fallback i ctx; etf_flow er skala-invariant), COT.
- ✅ **platinum** (2026-05-31) — **`price_ratio` PLATINUM/GOLD** (ny driver: relativverdi/substitusjon,
  mean-reversion, ikke pris-trend), COT, dollar, realrente (lav vekt). Verifisert 2025/2021 LONG, 2018/2023 SHORT.
- ✅ **copper** (2026-05-31) — dollar, HY-kredittspread (vekst), COT, VIX. NB: pris kun 2023→, COT 2022→,
  BAMLH0A0HYM2 leverer kun 2023→ på FRED → base-rate tynn (gaten avviser ærlig). Drivere fundamentalt riktige.
- ✅ **wti / brent** (2026-05-31) — `seasonal_anomaly` på EIA crude-lager (WCESTUS1) vs sesong-norm
  (ny EIA-fetcher `fetch.eia`), COT, dollar, OVX. Brent-COT grunn (2022→) → renormaliserer pent til NA.
- ✅ **natgas** (2026-05-31) — `seasonal_anomaly` EIA gass-lager (NG_STOR_L48) + `degree_days_anomaly`
  (ny driver: vær-drevet etterspørsel, Chicago us_gas_demand 2005→), COT. Pris kun 2019→ (tynn base-rate).
- ⚠️ **12 øvrige** (corn, soybean, wheat, cocoa, cotton,
  gbpusd, usdjpy, audusd, sp500, nasdaq, btcusd, ethusd) — generisk, generert av `gen_universe_fingerprints.py`.

### Gjenbrukbare drivere (registrert i `score/drivers.py`)
`level_percentile`, `momentum`, `price_momentum`, `series_spread_percentile`, `price_vs_sma`,
`cot_spec_net_percentile`, `ethanol_parity`, `series_ratio`, `rainfall_anomaly`, `etf_flow`, `frost_anomaly`,
`price_ratio`, `seasonal_anomaly`, `degree_days_anomaly`. Lag nye ved behov med `@register`.

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
- **EIA wiret (2026-05-31):** `fetch.eia` henter crude-lager (WCESTUS1, 1995→) + gass-lager (NG_STOR_L48,
  2010→) via EIA API v2 data-rute. Lagt i `update.sh`. Open-Meteo-vær også i `update.sh` nå.
- Ikke-wiret ennå: FAS/PSD, NASS, AGSI, LBMA, CBOE, Deribit, Baker Hughes m.fl. (kandidater for tilpasning).

## Åpne spørsmål
- Skal scenario-generatoren bli hoved-produktet (ærlig fordeling) framfor «setups»? (UI viser i dag setups.json.)
- Kovariat-betinget foundation-modell (Moirai) — utsatt: vårt bevis tilsier kovariatene ikke bærer forward-info.
- Full historikk vs train-panel som naboer i base-rate-gaten.

## K1-resultat (2026-05-30) — løst positivt
cTrader-spike viste dyp D1-historikk: Gull ~28 år, Olje ~20 år, Indeks ~14 år. Skilling demo-konto 32290195.
→ K3 låst: regn både nivåer OG base-rate på Skilling-feed.
