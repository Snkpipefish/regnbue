# Regnbue — STATE (live status)

> Oppdater denne ved slutten av hver økt. Et nytt kontekstvindu leser denne rett etter `CLAUDE.md`.

**Sist oppdatert:** 2026-06-15 (audit-fikser #1/#2/#3/#5 + #7 coverage-match + #10 swap + #12 scenario-base-rate + #13 driver-IC)
**Nåværende fase:** MVP live + scenario-generator bygget. **Neste: OOS-valider opt-ins (`engine: scenario`, `match_coverage`) + fyll `swap`-rater pr instrument før de slås på.**
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
- ✅ **corn/soybean/wheat/cotton** (2026-05-31) — US-vekstsesong-vær (ny `active_months`-gate på
  `rainfall_anomaly` så bare vekstsesongen teller), dollar (eksport), COT. Corn har i tillegg etanol/olje
  (DCOILWTICO). Dyp Open-Meteo for us_cornbelt/us_wheat_plains/us_cotton (2000→).
- ✅ **cocoa** (2026-05-31) — Vest-Afrika-vær (west_africa_cocoa, 2000→), ENSO (El Niño=bull), COT.
  Fanger 2023–24 supply-krisen (LONG A). NB grain/softs Skilling-pris kun 2021→ → base-rate tynn.
- ✅ **gbpusd / usdjpy / audusd** (2026-05-31) — EURUSD-mønster: US−utland 10y rentespread (hentet dypt
  fra FRED, 1990→), Fed-forventninger (US 2y) / dollar, COT, VIX. VIX-fortegn pr valuta: yen styrkes &
  AUD selges i risk-off. Fjernet `price_vs_sma`. NB: carry-modeller misfyrer i USD-likviditetskriser
  (GBP 2020-03) — tunes IKKE etter resultat.
- ✅ **sp500 / nasdaq** (2026-05-31) — makro-regime: HY-kredittspread, 10y-rente-momentum, rentekurve
  (10y−2y), COT. VIX bevisst utelatt (= SPX' egen implisitte vol → sirkulær). Verifisert: SP500 2020-03
  LONG A+ (COVID-bunn), 2022-06 SHORT A+.
- ✅ **btcusd / ethusd** (2026-05-31) — dollar-likviditet, VIX risk-sentiment, COT. Dokumentert svakest
  fundamentale grunnlag (flyt/narrativ; spot-ETF-flyt usynlig). VIX ikke sirkulær her (aksje-avledet).
- 🎉 **ALLE 22 HÅNDTILPASSET** — `gen_universe_fingerprints.py` SPEC tom (no-op, beholdt som mal).

### Gjenbrukbare drivere (registrert i `score/drivers.py`)
`level_percentile`, `momentum`, `price_momentum`, `series_spread_percentile`, `price_vs_sma`,
`cot_spec_net_percentile`, `ethanol_parity`, `series_ratio`, `rainfall_anomaly`, `etf_flow`, `frost_anomaly`,
`price_ratio`, `seasonal_anomaly`, `degree_days_anomaly`. Lag nye ved behov med `@register`.

---

## AUDIT-FIKSER i trading-logikken (2026-06-15)
Gjennomgang av setup-genereringen avdekket at base-rate-gaten validerte en *annen* trade enn
den som ble publisert. Fire avgrensede korrekthetsfikser (alle med tester, 61 grønne):
- **#1 R:R-justert base-rate:** panelet ble bygd med faste 1×/2×ATR mens setup-en hadde
  nivåbasert R:R → gaten beskrev feil trade. Splittet `build_panel` i RR-uavhengig
  `build_scored_panel` (dyr scoring, bygges én gang i `run.py`) + `ScoredPanel.outcomes(sl_atr,
  tp_atr)` (billig barriere). `generator` materialiserer nå utfall med setup-ens *faktiske*
  SL/TP-avstander (`risk/atr`, `reward/atr`).
- **#2 effektiv n:** Wilson/expectancy-CI antok uavhengige obs, men PANEL_STEP=10 < horizon=30
  → overlappende forward-vinduer → falsk presisjon. `gate.evaluate(horizon_days=…)` teller nå
  ikke-overlappende blokker (`_effective_n`) og bruker det i n-terskel + CI-bredde. Eksponert
  som `BaseRate.n_eff` (gull: n=31 → n_eff=23).
- **#3 COT-frigjøringslag:** `ctx.cot()` filtrerte på `report_date<=as_of`, men CFTC slipper
  tirsdagsdata først fredag (+3d) → ~3 dagers look-ahead. Nå `report_date+3d<=as_of`.
- **#5 SL-gulv:** `sl_floor_atr=0.5` hindrer at en swing rett ved entry gir mikro-risiko og
  kunstig høy R:R som stoppes ut umiddelbart.
- **#4 (TIME-klipp) forkastet:** viste seg å være no-op — barriere-løkka skanner t.o.m. siste
  bar, så TIME-`outcome_r` ligger allerede i (−1, +rr).

### Strategiske grep (2026-06-15) — bygget
- **#12 forward base-rate fra scenario-fordelingen:** `scenario.fhs_barrier_prob` simulerer
  sti-avhengig P(TP før SL) + expectancy (i R) fra FHS-baner med setup-ens entry/SL/TP.
  `generator` fester `scenario`-summary på hver setup (vises i `setups.json` ved siden av
  analog-base-raten). Krysssjekk gull: analog exp −0.12R / scenario exp −0.12R, P(TP)≈48% —
  to uavhengige metoder enige. **Opt-in gating:** sett `base_rate.engine: scenario` (+
  `min_prob_tp`) i et fingerprint for å la scenario-motoren gate publisering i stedet for
  analog. Standard = `analog` (uendret), så ingen av de 22 flippes stille.
- **#13 per-driver IC:** `validate.py` regner `driver_ic` = corr(driver-score, forward-R) på
  OOS pr driver (`_driver_ic`). IC≈0 = ingen påvist forward-info (kandidat for nedvekting),
  klart positiv = signal. Endrer ingen vekter automatisk — ærlig diagnostikk, printes i run().

### #7 + #10 (2026-06-15) — bygget
- **#7 sammensetnings-bevisst matching:** `gate.evaluate(coverage=…)` / `neighbors_by_score`
  krever at analoger hadde NØYAKTIG samme tilgjengelige drivere, så renormalisert score er
  sammenlignbar (0.3 fra 2 drivere ≠ 0.3 fra 4). **Opt-in** via `base_rate.match_coverage:
  true` i fingerprintet (av som standard — låste terskler endres ikke stille). Generator
  beregner current-coverage fra `res.drivers` ok.
- **#10 swap/carry i expectancy:** `outcomes.swap_cost_r` + `triple_barrier(return_held=True)`
  trekker carry fra hvert panel-utfall pr FAKTISK holdetid; scenario-motoren gjør det samme
  eksakt pr bane. Konfig pr fingerprint: `swap: {long_cost_pct_per_day, short_cost_pct_per_day}`
  (positiv = debet, negativ = kreditt). Mangler ennå reell swap-rate-kilde wiret → må fylles
  pr instrument (negativ-swap-instrumenter flagges, PLAN §5b). Av som standard (ingen swap-nøkkel).

### Gjenstående forslag fra auditen (ikke gjort — bevisst utsatt)
- **#9 ikke-lineær aggregering:** lineær additiv sum av ikke-monotone + monotone drivere til én
  skalar visker ut struktur. Spekulativt modell-redesign; prosjektets eget hovedfunn tilsier
  forsiktighet → egen beslutning før noe bygges.

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

## Ytelse (panel-bygging)
- `build_panel` re-scorer pr dato → tungt. `run.py` sampler hver `PANEL_STEP=10`. dag (ytelse, ikke
  terskel-tuning). To cache-lag gir **bit-identiske resultater** (verifisert: alle 83 driver-scorer + 22
  samlet-scorer matcher gammel ucachet kode mot `setups.json`; + look-ahead-tester):
  1. **Data-laget** (`_FULL_CACHE` i `context.py`): full makro/pris/spread/ETF/COT-serie hentes/merges
     ÉN gang pr innholds-signatur (count,min,max,SUM); `as_of` skjæres med bisect. Driverne er urørt.
     Fjernet bl.a. gulls 16000-rad spread-merge pr kall → gull 58→22s (~2.6×).
  2. **Vær-laget** (`_WEATHER_ROLL_CACHE` i `drivers.py`): rullende vindu pr region cachet (natgas 11→2.9s).
- Signaturen har verdi-sjekksum (SUM) så ulike datasett/test-conns med samme antall/datospenn aldri
  deler nøkkel. Look-ahead bevart (kun ≤as_of eksponeres). `setups.json` uendret (identisk → ingen re-kjøring).
- Videre (valgfritt): prefiks-sum for `pstdev` i momentum/etf_flow ville gi O(1) pr kall, men kan avvike på
  flyttall-nivå (ofret bit-identitet) — derfor ikke gjort. `PANEL_STEP` kan nå senkes for tettere paneler.

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
