# Setups — dataoversikt for bedrock + cot-explorer, og forslag til prosjekt #3

Dato: 2026-05-29
Status: oversikt + forslag, ikke en plan. Mål: kartlegg *all* data i de to eksisterende
prosjektene og hvordan hvert av dem genererer setups, og foreslå et tredje prosjekt som
spisser datainnsamlingen **per instrument** og genererer **realistiske** setups.

Kilder kartlagt: `~/bedrock/` og `~/cot-explorer/`. Slektslinjen er
`cot-explorer/NYTT_PROSJEKT_UTKAST.md` → `cot-explorer/BEDROCK_PLAN.md` → `bedrock/`.

---

## DEL 1 — Hva de to prosjektene er

| | **cot-explorer** | **bedrock** |
|---|---|---|
| Rolle | Datafetch + scoring + **web-UI** (GitHub Pages) | Datafetch + scoring + **setup-generator** + **cTrader-bot** |
| Lager | JSON-filer på disk | SQLite (`bedrock.db`) + JSON-snapshots |
| Scoring | 6-familie driver-matrix (schema 2.0), 0–6 skala | Config-drevet motor, YAML pr instrument, samme 6 familier |
| Setups | Entry/SL/T1/T2 i `signals.json` | Reelle-nivå-setups m/ persistens + analog-matching |
| Trades | Nei (pusher signaler) | Ja — cTrader Open API på demo, full entry/exit-logikk |
| UI | `index.html` + `crypto-intel.html` + `metals-intel.html` | `web/index.html` (4 faner) |

Kort: **cot-explorer var den første** (fetch + scoring + dashboard). **bedrock er den andre**
og mer modne (config-drevet motor, ekte setup-generator, bot). cot-explorer-dashboardet leser
nå *også* bedrock-data inn (`data/bedrock/*.json`) og presenterer begge i én UI.

---

## DEL 2 — All data som hentes (begge prosjekter)

Datakildene overlapper i stor grad. Tabellen markerer hvem som henter hva og den *ærlige*
nytteverdivurderingen fra `NYTT_PROSJEKT_UTKAST.md §2` (bekreftet etter faktisk bruk).

### Posisjonering (COT) — kjernen, få ikke-pris-signaler
| Kilde | Hva | Dekning | Hvor | Nytte |
|---|---|---|---|---|
| CFTC COT (disaggregated/legacy/TFF/supplemental) | MM / kommersielle / index / spec netto-posisjoner | ~50 kontrakter: indekser, FX, renter, metaller, energi, agri, krypto | begge | **HØY** |
| ICE Futures Europe COT | MM long/short/OI | Brent, Gasoil, TTF Gas | begge | MIDDELS |
| Euronext COT | MM long/short | Milling Wheat (EBM), Corn (EMA), Canola (ECO) | begge | MIDDELS (EU-vs-US relativ) |

### Pris
| Kilde | Hva | Hvor | Nytte |
|---|---|---|---|
| cTrader bot-feed | OHLC for instrumenter som faktisk trades | bedrock (cot-explorer leser den) | **HØY** (primær pris-sannhet) |
| Yahoo / Stooq fallback | OHLCV der bot ikke har feed | begge | LAV–MIDDELS |

### Makro / fundamentals
| Kilde | Hva | Hvor | Nytte |
|---|---|---|---|
| FRED | DGS10, T10YIE, DTWEXBGS (DXY), VIX, CPI, NFP, renter, PMI m.m. | begge | MIDDELS (regime-deteksjon) |
| ForexFactory kalender | High/medium-impact events, forecast/actual | begge | MIDDELS (event-timing) |
| NOAA ONI / IRI ENSO | El Niño/La Niña-indeks | bedrock | MIDDELS (agri) |

### Agri-fundamentals
| Kilde | Hva | Dekning | Hvor | Nytte |
|---|---|---|---|---|
| Open-Meteo (forecast + ERA5 15+ år) | Temp, nedbør, GDD, ET0, frost, tørke pr region | ~20 dyrkingsregioner | begge | MIDDELS |
| USDA WASDE | Ending stocks, yield, stocks-to-use | korn/soya/sukker | bedrock | MIDDELS |
| USDA NASS Crop Progress | % planted/silking/harvested/good-excellent | US-avlinger | bedrock | MIDDELS |
| CONAB (Brasil) | Produksjon/yield: soja, milho, hvete, bomull, kaffe | Brasil | begge | MIDDELS |
| UNICA (Brasil) | Sukker/etanol crush + mix (Centro-Sul) | Brasil sukker | begge | MIDDELS |
| UN Comtrade / USDA PSD / ISMA | India sukker-eksport/produksjon | India | bedrock | LAV–MIDDELS |

### Energi / metall-inventar
| Kilde | Hva | Hvor | Nytte |
|---|---|---|---|
| EIA | Ukentlig crude/gasoline + naturgass-lager | bedrock | MIDDELS |
| AGSI+ / ALSI | EU gass- og LNG-lager (D+1) | bedrock | MIDDELS |
| COMEX warehouse | Gull/sølv/kobber registrert vs eligible | begge | MIDDELS (stress-signal) |

### "Story"-data — ærlig vurdert som støy eller ballast
| Kilde | Hva | Hvor | Nytte |
|---|---|---|---|
| Baltic-indekser (BDI/BCI/BPI/BSI) + chokepoint-risiko | Shipping/handelsproxy | begge | LAV–MIDDELS |
| Oilgas-segment-scoring (OPEC/sanksjoner) | Keyword-scoring av nyheter | cot-explorer | **LAV** (RSS-støy) |
| Google News RSS (metall/krypto/geo) | Narrativ | begge | LAV |
| USGS seismikk | Jordskjelv M≥4.5 nær gruver | begge | LAV (hvilken beslutning?) |
| CoinGecko + Fear&Greed | Krypto dominans/sentiment | begge | LAV–MIDDELS (dashboard-fyll) |

**Konklusjon fra dataaudit (NYTT_PROSJEKT_UTKAST §2.3):** kjernen som faktisk driver
beslutninger er smal — **pris, COT-posisjonering, makro-regime (DXY/VIX/FRED), SMC-struktur,
agri-fundamental (vær + avlingsestimat), og event-risk**. Resten er kontekst eller ballast.

---

## DEL 3 — Hvordan hvert prosjekt genererer setups

### cot-explorer
1. `fetch_*.py` skriver rå JSON pr kilde.
2. `driver_matrix.py` (schema 2.0) scorer hvert instrument over **6 familier** —
   TREND, POSITIONING, MACRO, FUNDAMENTAL, RISK, STRUCTURE — med **horisont-spesifikke vekter**
   (SCALP/SWING/MAKRO). Confluence-lås: 2 familier alene kan ikke gi A-grade.
3. `cot_analytics.py` + `cot_interpreter.py` lager percentiler, MM-vs-kommersiell divergens,
   regime (akkumulasjon→markup→distribusjon→markdown) og narrativ.
4. `smc.py` finner HTF-struktur. `agri_analog.py` gjør K-NN på 15 års vær.
5. `push_signals.py` / `push_agri_signals.py` bygger setups med entry-sone/SL/T1/T2/ATR,
   bruker korrelasjon-grupper (maks samtidige signaler avhengig av VIX-regime), og pusher.
6. `index.html` laster 20+ JSON-filer og viser heatmap, kort, drill-down, agri- og krypto-paneler.

**Svakhet (egen audit):** scoring-logikk har sneket seg inn i fetch-skript; `rescore.py`
dupliserer matrisen; mye innsamlet data brukes aldri i beslutning; TP-er ble til tider for små.

### bedrock
1. `fetch/` (rå I/O) → SQLite via `data/store.py` (30+ kilder, schema i `data/schemas.py`).
2. **Motor** (`engine/engine.py`): én `Engine.score(instrument, store, rules, horizon)`. Regler
   bor i `config/instruments/*.yaml` (arver fra `defaults/`). ~40 drivere i `engine/drivers/`
   registrert pr navn. To aggregatorer: `weighted_horizon` (financial) + `additive_sum` (agri).
   Retnings-bevisst (SELL flipper directional-familier). Full `explain`-trace pr signal.
3. **Setup-generator** (`setups/`): `levels.py` finner reelle nivåer (swing, round numbers,
   prior period H/L), `generator.py` klustrer dem (0.3×ATR) og bygger **asymmetriske** setups —
   entry ved sterkt nivå, SL = buffer×ATR, TP = neste nivå i retningen, R:R-floor pr horisont
   (1.5 scalp / 2.5 swing / MAKRO = trailing, ingen fast TP). `hysteresis.py` hindrer flapping.
   Setups har ID og **persisterer** på tvers av kjøringer (watchlist→triggered→active→closed).
4. **Analog** (`drivers/analog.py`): K-NN mot historiske `analog_outcomes` (forward return + MaxDD
   pr instrument/dato/horisont), gir hit-rate og snitt-avkastning som egne drivere.
5. **Bot** (`bot/`): `comms.py` poller signal-server → `entry.py` (3-punkts bekreftelse: score,
   candles-since-signal, body≥30%ATR, EMA9-gradient) → `sizing.py` (risk-%-tier × lot-tier,
   VIX/geo-nedskalering) → `ctrader_client.py` (market + SL/TP via Protobuf) → `exit.py`
   (P1–P5: geo-spike, kill, weekend, T1-partial+BE, trailing, EMA9-cross, timeout).

**Styrke:** config-drevet, testbar, ekte nivåer, persistente setups, sporbarhet.

---

## DEL 4 — Forslag til prosjekt #3

### Tesen som skiller #3 fra de to andre

bedrock løste *generaliteten* godt: én motor, samme 6-familie-skjelett for alle instrumenter,
per-instrument YAML som bare **vrir på vektene**. Det du nå ber om — "spisse datainnsamlingen
enda mer pr instrument" + "logikk som genererer realistiske setup" — er det neste steget:

> **Hvert instrument er en spesialist, ikke en vektvariant. Og hver setup må bære empirisk bevis
> for at akkurat dette mønsteret historisk har gitt akkurat denne avkastningen.**

To konkrete skift:

**1. Spisset datainnsamling pr instrument ("instrument fingerprint").**
I stedet for å hente *alt* for *alle* og score med et generisk familieskjelett, definerer hvert
instrument sin egen kuraterte datapakke — kun kildene som historisk har prediktiv kraft *for det
instrumentet*:
- **Gull:** realrente (DGS10−T10YIE), DXY, ETF-flows (GLD-tonn), COMEX registrert/total, GVZ, COT-percentil.
- **Kaffe:** Brasil frost-vindu + harmattan (Vest-Afrika), CONAB-revisjon, BRL/USD, COT, lager-trend.
- **EURUSD:** rentedifferensial-endring, DXY-momentum, VIX-regime, term-spread, COT TFF.
- **Brent:** backwardation, EIA/EU-lager, supply-disruption-nivå, ICE-COT-kommersiell, DXY.

Dette gir færre, men skarpere drivere pr instrument — og fjerner "samler men bruker aldri"-gjelden.
Bedrocks driver-registry og SQLite-lag kan gjenbrukes direkte; det nye er en **eksplisitt
`instrument-profil`** som binder kilde → driver → forventet effekt, og en fetch-planlegger som
kun henter det profilene faktisk trenger.

**2. Bevis-basert realisme i setup-generatoren.**
bedrock plasserer setups på reelle nivåer — bra. #3 går videre: en setup publiseres **bare hvis
den historiske analog-fordelingen støtter R:R-en**. For hver kandidat-setup slår vi opp:
"gitt denne konstellasjonen av spissede drivere + denne nivåtypen, hva skjedde historisk?" →
hit-rate til T1, MFE/MAE-fordeling, median tid-til-mål, og en empirisk forventning (expectancy i R).
En setup med fint nivå men svak historisk base-rate forkastes eller nedgraderes. Dette er
forskjellen mellom "et nivå finnes" og "dette har faktisk fungert".

bedrocks `analog_outcomes`-tabell og K-NN er fundamentet — #3 hever det fra *én driver blant 40*
til **gatekeeper for hele setupen**, og knytter analogen til instrumentets egen fingerprint-dimensjoner.

### Hva #3 arver vs bygger nytt

| Arver fra bedrock (gjenbruk) | Bygger nytt i #3 |
|---|---|
| SQLite-lag + schemas + store | `instrument-profil`-spec (kilde→driver→effekt pr instrument) |
| Driver-registry + ~40 drivere | Fetch-planlegger drevet av profiler (henter kun det som brukes) |
| Reelle-nivå-detektor + klustring | Setup-gate på empirisk base-rate (analog-fordeling → expectancy) |
| K-NN / analog_outcomes | Per-instrument analog-dimensjoner knyttet til fingerprint |
| cTrader-bot (uendret) | Realisme-rapport pr setup ("N analoger, X% til T1, +Y R median") |
| `explain`-trace | Profil-drevet narrativ ("disse 5 kildene styrer gull — her er status") |

### Foreslått minimumsleveranse (MVP, 2–3 instrumenter)
1. `instrument-profil` for Gull, EURUSD og Kaffe (én financial-default, én FX, én agri).
2. Fetch-planlegger som kun henter profilenes kilder (gjenbruk bedrock `fetch/`).
3. Setup-generator (gjenbruk bedrock `levels.py`) + ny base-rate-gate på analog-fordeling.
4. CLI: `setups explain <instrument>` viser profil-status + setup + empirisk forventning.
5. Logiske tester i bedrock-stil: "gitt historisk snapshot → forvent setup med ≥X R og base-rate".

Ingen bot-endring i MVP — #3 produserer setups og en realisme-rapport; bot-kobling kommer hvis MVP holder.

### Åpne valg (du bestemmer)
1. **Eget repo `setups/` eller submodul under bedrock?** Mye gjenbruk taler for å starte som
   pakke som importerer bedrock, ikke kopiere koden.
2. **Navn/tema?** Pirat-temaet (Skipsloggen/Skatter/Kartrommet) er identitet nå — beholde?
3. **Hvilke 2–3 instrumenter i MVP?** Forslag: Gull, EURUSD, Kaffe (dekker metall/FX/agri).
4. **Base-rate-terskel:** hvor mange historiske analoger kreves før en setup får publiseres?
5. **UI nå eller senere?** Kan starte CLI-only og gjenbruke cot-explorer-dashboardet for visning.
