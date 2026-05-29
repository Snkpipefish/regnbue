# Regnbue (prosjekt #3) — implementasjonsplan

Prosjektnavn: **Regnbue** (regnbue-tema gjennomgående i UI).
Dato: 2026-05-29
Status: **venter godkjenning** før koding starter.
Referanser: `OVERSIKT_OG_FORSLAG.md` (denne mappen), `~/bedrock/`, `~/cot-explorer/`.

---

## 1. Kontekst

Du har to prosjekter: **cot-explorer** (data + scoring + web-UI) og **bedrock** (data + scoring +
setup-generator + cTrader-bot). Prosjekt #3 er et **helt nytt, frittstående prosjekt** som *lærer*
av de to andre og gjør det bedre — ikke en kopi eller wrapper.

Mål:
- **Spisset datainnsamling per instrument** — hvert instrument får en "fingerprint": kun de kildene
  og driverne som faktisk beveger *det* instrumentet.
- **Realistiske setups** — en setup publiseres bare hvis den historiske base-raten støtter R:R-en.
- **Ingen bot** — du trader manuelt. Output publiseres på en **ny GitHub Pages-side**.

### Hva vi gjenbruker fra de to andre (og hva vi ikke gjør)
| Gjenbruker | Bygger nytt / eget |
|---|---|
| **Datakilder** (hvilke API-er/endepunkter) | Eget, lean fetch-lag (kun høyverdi-kilder) |
| **API-nøkler** fra `~/.bedrock/secrets.env` (FRED, TwelveData, Finnhub, NASS, EIA, …) | Egen `secrets.py` (inspirert av bedrocks env-override-mønster) |
| **Eksisterende data** — seed historikk fra `~/bedrock/bedrock.db` (engangs) | Egen datastore + egen scoring-generator |
| **Inspirasjon** fra 6-familie driver-matrix + config-drevet motor | Egen, renere scoring-motor designet rundt fingerprint + base-rate |

**Vi kopierer ingen kode.** bedrock/cot-explorer brukes som referanse for *hva som funker og hva som
er støy* (din dataaudit i `cot-explorer/NYTT_PROSJEKT_UTKAST.md §2`), ikke som kildekode å løfte.

---

## 2. Lærdom → designvalg

| Lærdom fra #1/#2 | Hva #3 gjør annerledes |
|---|---|
| cot-explorer: scoring-logikk snek seg inn i fetch-skript | Streng separasjon: `fetch` → `store` → `score` → `setups` → `publish` |
| cot-explorer: `rescore.py` duplikat av matrisen | **Én** scoring-vei, ingen duplisering |
| Begge: "samler men bruker aldri" data (seismikk, RSS, shipping, krypto-sentiment) | Fetch henter **kun** det fingerprintene erklærer å trenge |
| bedrock: generisk familieskjelett, per-instrument kun vekt-vri | Fingerprint er førsteklasses: instrumentet erklærer egne kilder **og** drivere |
| Begge: setups på nivå som finnes, men noen ganger svak/små TP | Base-rate-gate: historisk bevis kreves før publisering |
| bedrock godt: config-drevet, testbar, explain-trace | Beholdes som *prinsipp* (egen implementasjon): YAML-drevet, logiske tester, full trace |

---

## 3. Arkitektur (grønt-mark, egen kode)

```
~/prosjekter/setups/                  (nytt git-repo → ny GitHub Pages)
├── pyproject.toml                    # frittstående pakke (pandas, pydantic, pyyaml, requests)
├── config/
│   ├── sources.yaml                  # hvilke datakilder + cadence (kun høyverdi)
│   └── instruments/                  # 22 fingerprint-profiler (egen, enkel YAML)
│       └── gold.yaml ... (×22)
├── src/setups/
│   ├── secrets.py                    # les ~/.bedrock/secrets.env, env-var override (egen)
│   ├── store.py                      # egen datastore (SQLite), seed fra bedrock.db engangs
│   ├── ctrader_prices.py             # read-only OHLC fra Skilling via cTrader Open API (NIVÅ-feed)
│   ├── fetch/                        # egen lean fetch BIAS-data (COT, FRED, EIA, agri, COMEX, kalender, gamma)
│   ├── score/
│   │   ├── drivers.py                # driver-registry (@register), egne implementasjoner
│   │   ├── engine.py                 # egen scoring-motor (fingerprint-drevet)
│   │   └── grade.py                  # grade + explain-trace
│   ├── outcomes.py                   # forward-return + max-drawdown for base-rate
│   ├── generator.py                  # egen setup-generator (reelle nivåer + base-rate-gate)
│   ├── publish.py                    # → web/data/setups.json (schema_version + generated)
│   └── run.py                        # pipeline: fetch → score → setup → gate → publish
├── web/                              # statisk frontend (serveres fra repo-rot)
│   ├── index.html                    # beslutnings-UI (se §6)
│   ├── assets/  └── data/            # publisert JSON
├── systemd/  ├── setups.timer  └── setups.service
├── update.sh                         # flock + git add/commit/rebase/push (mønster fra cot-explorer)
└── tests/  (test_engine, test_gate, test_profiles, test_publish)
```

**Data — to adskilte roller (kritisk, se §5b):**
- **Bias/kontekst** (retning, regime, scoring): COT/FRED/EIA/agri/futures. Seed historikk engangs fra
  `~/bedrock/bedrock.db` (lese-only), deretter eget lean fetch-lag via gjenbrukte API-nøkler.
- **Nivå-koordinater** (entry/SL/TP): **Skillings egen prisfeed via cTrader Open API (read-only OHLC)** —
  *ikke* Yahoo/futures. Dette eliminerer basis-problemet (§5b). cTrader-credentials i `secrets.env`.

Lavverdi-kilder (seismikk, oilgas-RSS, news, shipping, krypto-sentiment) tas **ikke** med.

---

## 4. Fingerprint-profiler (egen, enkel YAML)

Hvert instrument erklærer sin egen datapakke **og** drivere — ikke et generisk skjelett. Eksempel:

```yaml
# config/instruments/gold.yaml
id: Gold
ticker: XAUUSD
asset_class: metals
sources: [prices, cot_disaggregated, fred, comex]   # kun det gull trenger
drivers:
  - {name: real_yield, weight: 0.25, params: {series: DGS10, bull_when: low}}
  - {name: dxy_momentum, weight: 0.20, params: {horizon: 5d}}
  - {name: cot_mm_percentile, weight: 0.20, params: {lookback_weeks: 52}}
  - {name: comex_stress, weight: 0.15}
  - {name: gvz_zscore, weight: 0.10}
  - {name: sma200_align, weight: 0.10, params: {tf: D1}}
grade_thresholds: {A_plus: 0.75, A: 0.55, B: 0.35}
base_rate: {horizon_days: 30, min_neighbors: 5, min_hit_rate_pct: 55, min_expectancy_r: 0.3}
```

Driver-registry og grade-logikk er **vår egen**, men inspirert av bedrocks 6-familie-tankegang.
Vi starter de 22 profilene fra bedrocks instrument-liste som *referanse*, men skriver lean fingerprints.

## 5. Setup-generator + base-rate-gate (egen)

1. `generator.py` finner reelle nivåer (swing/round/prior H-L **+ gamma-vegger/zero-gamma-flip**) og
   bygger asymmetriske setups (entry ved sterkt nivå, SL = buffer×ATR, TP = neste nivå, R:R-floor pr
   horisont). Egen kode, designet for å unngå "for små TP"-problemet fra #1/#2.
   - **Gamma-driver `gamma_regime`:** long gamma = dempede bevegelser (strammere range), short gamma =
     forsterkede (bredere SL, momentum) — kun instrumenter med gratis gamma (indeks/GLD/SLV/USO/BTC/ETH).
     Se `DATA_KARTLEGGING.md §3b`.
2. `outcomes.py` regner forward-return + max-drawdown fra historikk → base-rate-tabell.
3. **Gate (skjerpet etter audit K2/V3/V4):** setup publiseres kun hvis (a) naboer innenfor en
   **likhetsterskel** (ikke bare K=5 nærmeste), (b) **effektiv n ~30+**, (c) hit-rate + **expectancy
   med konfidensintervall** over terskel. Terskler **låses før resultater ses**, og gate-ytelse måles
   på et **out-of-sample-vindu** (siste 2–3 år) som aldri tunes på. `test_gate.py` beviser look-ahead-vern
   (as-of-dato → ingen fremtidige outcomes lekker) FØR base-rate brukes. Forkastede vises i UI med grunn
   + **n og CI** (ikke punktestimat).

## 5b. Broker-prisalignering (Skilling) — egen lærdom #1/#2 ikke løste

Skilling priser commodities/indekser som **udaterte cash-CFD-er syntetisert fra forward/futures**.
Det gir en **basis** mot front-futures som varierer daglig (verst olje/naturgass pga. contango/
backwardation; liten gull/sølv ≈ OTC-spot; indeks har fair-value-premie mot ES). **bedrock løser ikke
dette** — den regner nivåer fra Yahoo continuous futures (`GC=F`/`BZ=F`/`ZC=F`) og bruker dem direkte
mot Skillings bid/ask. Det gir systematisk skjeve nivåer, spesielt olje/gass.

**Regnbue-prinsipp:** nivå-koordinater regnes **alltid på Skillings egen prisfeed** (cTrader Open API,
read-only OHLC pr `cfd_ticker`). Futures/COT/EIA brukes kun til bias/retning/regime, aldri til
nivå-tallene. Dermed er entry/SL/TP per definisjon i brokerens koordinatsystem — ingen basis-feil.

Følger av dette:
- **Gamma-nivåer** (regnet på SPX/GLD/SLV/USO/Deribit) må mappes til Skillings koordinatsystem før de
  brukes som S/R (liten justering gull; cash-vs-ES-offset for indeks; GLD→XAU-skalering).
- **Swap/financing:** Skilling belaster daglig swap 22:00 GMT (trippel onsdag), carry innbakt (udatert).
  For SWING/MAKRO trekkes forventet swap-kostnad inn i setup-ens expectancy; negativ-swap-instrumenter
  (bedrock deaktiverte Platina) flagges i UI.
- **Analog/outcomes:** forward-return for base-rate regnes på beste sammenhengende serie for *bias*;
  selve setup-R:R regnes på Skilling-feed. Nyanse dokumenteres så vi ikke blander koordinatsystem.

## 6. Web — beslutnings-UI for manuell trading

Vanilla JS (mønster fra cot-explorer, men spisset til "skal jeg ta denne traden?"):
- **Topp-kort pr publisert setup:** instrument, retning, horisont, grade, **entry/SL/T1/R:R**,
  + base-rate-badge ("5 analoger, 60% til T1, +0.8R median").
- **Driver-badges** med score + **klikk → modal** med full explain-trace + analog-naboer.
- **Forkastede setups** m/ grunn, og **datakvalitet-stripe** (`generated` + alder pr kilde).

JSON-kontrakt `web/data/setups.json`: `schema_version`, `generated` (ISO UTC), `signals[]`.

## 7. Publisering — ny GitHub Pages

`update.sh` følger cot-explorer-mønsteret (flock på `.git/push.lock`, add/commit/rebase/push, serveres
fra repo-rot). Systemd-timer hver 6. time. **Jeg** oppretter GitHub-repoen via `gh`, skrur på Pages og
gjør første push (fase 7).

---

## 8. Faser

| Fase | Innhold | Test-krav |
|---|---|---|
| **−1** | **GATE (audit K1):** read-only cTrader-spike — mål faktisk D1-historikk-dybde fra Skilling for XAUUSD + indeks-CFD + olje-CFD + rate-limits | antall år D1 dokumentert; avgjør K3 |
| **0** | Repo + `pyproject.toml` + `secrets.py` (leser `~/.bedrock/secrets.env`) + ruff/pytest | `pytest` tomt grønt; secrets lastes |
| **1** | `store.py` + seed historikk fra `bedrock.db` (pris/COT/FRED/vær/COMEX, lese-only) | data-integritets-test |
| **2** | `fetch/` lean (bias-data) + `ctrader_prices.py` (read-only OHLC fra Skilling = NIVÅ-feed, §5b) | smoke-test pr fetcher; cTrader OHLC hentes |
| **3** | `score/` — egen driver-registry + motor + grade + explain. 22 fingerprint-YAML | logiske tester: gitt data → forvent score/grade |
| **4** | `generator.py` reelle nivåer + `outcomes.py` + base-rate-`gate` | logiske tester (`test_gate.py`) |
| **5** | `publish.py` → `web/data/setups.json` | JSON-kontrakt-test |
| **6** | `web/index.html` beslutnings-UI | visuell verifisering lokalt |
| **7** | `update.sh` + systemd; **jeg** lager GitHub-repo + Pages + første push | side viser setups live |

MVP = fase 0–6 lokalt; fase 7 går live til slutt.

## 9. Verifisering (ende-til-ende)

1. `python -m setups.run` → fetch/seed → score → setup → gate → `web/data/setups.json`.
2. `pytest` grønt (engine, gate, profiles, publish, outcome-integritet).
3. `python -m http.server` i `web/` → åpne `index.html`, sjekk entry/SL/T1/R:R + base-rate-badge +
   forkastede med grunn.
4. Manuelt: `update.sh` committer kun ved endring (dry-run først).

## 10. Beslutninger

| Valg | Bestemt |
|---|---|
| Navn / tema | **Regnbue** — regnbue-tema i UI |
| Tilnærming | **Grønt-mark, egen kode** — ingen kopiering fra #1/#2 |
| Gjenbruk | Datakilder, eksisterende data (seed fra `bedrock.db`), API-nøkler (`~/.bedrock/secrets.env`) |
| **Pris-kilde for nivåer** | **Skilling via cTrader Open API (read-only)** — ikke futures. Bias-data fra futures/COT/EIA (§5b) |
| Scoring | **Egen** generator, inspirert av 6-familie-matrix |
| Instrumenter | **MVP = 3** (Gull, EURUSD, Kaffe); alle ~22 utsatt til tesen er bevist (audit K4) |
| Repo | **Public** (kreves for Pages) |
| GitHub | **Jeg** oppretter repo + Pages + pusher (fase 7) |
| Datakartlegging | Egen fase D0 (under) — finn *mer* data fra API-nøkler + gratis kilder pr instrument |

Gjenstår (avgjøres underveis):
- **Base-rate-terskler:** start `min_neighbors=5, min_hit_rate=55%, min_expectancy=0.3R`.
- **Lagringsformat:** SQLite (som bedrock) vs. parquet — foreslår SQLite for enkelhet.

---

## 12. Fase D0 — datakartlegging (kjøres nå, før fingerprint-design)

Før fingerprintene skrives (fase 3/4) kartlegger vi **all** data vi har gratis tilgang til:
1. **Underbrukte muligheter i eksisterende API-nøkler** (FRED, TwelveData, Finnhub, NASS, EIA) —
   hva låser nøklene opp utover det #1/#2 bruker i dag, og free-tier-grenser.
2. **Andre gratis kilder** pr instrument/asset-klasse (metaller, FX, energi, korn, softs, indeks, krypto).

Resultat skrives til `DATA_KARTLEGGING.md` og mapper kilde → instrument → driver-idé. Dette blir
input til de 22 fingerprintene.

**Status: ferdig** — se `DATA_KARTLEGGING.md`. Største gevinster: FRED realrente (`DFII10`) +
kredittspread (`BAMLH0A0HYM2`) + likviditet (`WALCL`/`RRPONTSYD`), instrument-vol (`OVXCLS`/`GVZCLS`),
BIS CBPOL (alle policy-renter ett sted), USDA FAS PSD (alle korn/softs-balanser), EIA Cushing/SPR/
regionalt natgas, + gratis kilder (LBMA, COMEX-XLS, WGC ETF-flows, Baker Hughes, AGSI+, US Drought
Monitor, CBOE put/call, mempool/blockchain.com).
