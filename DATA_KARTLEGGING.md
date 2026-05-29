# Regnbue — datakartlegging (fase D0)

Dato: 2026-05-29
Formål: finne **all** gratis data vi kan bruke for å spisse hvert instrument — både underbrukte
muligheter i API-nøklene vi allerede har, og andre gratis kilder. Input til de 22 fingerprintene.
Verifisert via offisielle API-doc/sider mai 2026. Merk: noen ID-er bør røyktestes mot live-nøkler én gang.

Tagger: **GRATIS** (ingen auth) · **GRATIS-NØKKEL** (gratis registrering) · **SCRAPE** (HTML/PDF) ·
**BETALT-FLAGG** (var gratis, nå gated).

---

## 1. De største gevinstene (gjør disse først)

1. **FRED realrente + kredittspread + likviditet** — `DFII10`/`DFII5` (TIPS realrente, den enkeltbeste
   gull-driveren), `BAMLH0A0HYM2` (high-yield OAS = risikoappetitt), `WALCL`/`RRPONTSYD`/`WTREGEN`
   (Fed-likviditet, sterk for gull/krypto/indeks). I dag bruker vi kun nominell DGS10.
2. **Instrument-spesifikk volatilitet** — `OVXCLS` (olje-VIX), `GVZCLS` (gull-VIX) i FRED. I dag kun VIXCLS.
3. **BIS CBPOL** — *alle* sentralbank-styringsrenter i ett gratis datasett → rentedifferensial/carry for
   alle FX-par. Pluss BIS REER for verdsettelse. Én kilde dekker 8 valutaer.
4. **api.data.gov-nøkkelen** (bekreftet 2026-05-29: `FAS_API_KEY` = `USDA_API_KEY` = `API_DATA_GOV_KEY`,
   **samme nøkkel**) er én delt portal for *mange* regjerings-API-er. Låser opp **USDA FAS PSD**
   (verdens supply/demand = strukturert WASDE uten PDF-parsing), **FAS Export Sales (ESR)** (ukentlig
   US-eksportsalg pr kornsort/destinasjon — markedsbevegende), USDA ERS, samt hele api.data.gov-gatewayen
   (NREL m.fl.). Dekker også softs (kaffe/sukker/kakao/bomull) som NASS mangler. **Alt bekreftet mot live-nøkkel.**
5. **EIA-utdyping** — Cushing-lager (WTI-leveringshub), raffineri-utnyttelse, SPR, **regionalt** natgas-lager.
6. **CFTC COT** (gratis, ingen nøkkel) — vi henter dette allerede; behold som kjerne-positioneringssignal.

---

## 2. Underbrukte muligheter i eksisterende API-nøkler

### FRED (gratis, ~120 req/min) — massivt underbrukt
| Serie | Hva | Spisser |
|---|---|---|
| `DFII10`, `DFII5` | 10y/5y realrente (TIPS) | Gull, Sølv, Platina, krypto |
| `T5YIFR` | 5y5y forward inflasjonsforventning | Gull, USD, råvarer |
| `T10Y2Y`, `T10Y3M` | Yield-kurve-helning (resesjonsproxy) | Indeks, Kobber, Crude, AUD/NZD/CAD |
| `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAA10Y` | Kreditt-spreads (risikoappetitt) | Indeks, Kobber, Crude, risk-FX, BTC |
| `DTWEXAFEGS`, `RBUSBIS` | USD vs avanserte økonomier / real broad USD | All FX, gull, råvarer |
| `M2SL`, `WALCL`, `RRPONTSYD`, `WTREGEN` | Pengemengde + Fed-balanse + likviditet | BTC/ETH, gull, indeks |
| `DCOILWTICO`, `DCOILBRENTEU`, `DHHNGSP` | WTI/Brent/Henry Hub natgas spot | Crude, Brent, NatGas |
| `PCOPPUSDM`, `PWHEAMTUSDM`, `PMAIZMTUSDM`, `PSOYBUSDM`, `PSUGAISAUSDM`, `PCOFFOTMUSDM`, `PCOTTINDUSDM` | IMF råvarepriser (mnd) | Kobber, korn, softs |
| `DEXUSEU`/`DEXUSUK`/`DEXJPUS`/`DEXSZUS`/`DEXCAUS`/`DEXUSAL`/`DEXUSNZ`/`DEXNOUS` | Offisielle FX-fixinger inkl. USDNOK | Alle FX |
| `ECBDFR`/`ECBMRRFR`, BoE/BoJ/Norge-renter, `DGS2`/`DGS5`/`DGS30` | Policy-renter + kurve-noder (2y-diff driver JPY) | EURUSD, GBP, JPY, NOK |
| `OVXCLS`, `GVZCLS`, `VXOCLS` | Olje-/gull-vol-indekser | Crude, Gull |
| `STLFSI4`, `NFCI` | Finansiell stress / Chicago Fed | Indeks, risk-FX, BTC |

### TwelveData (gratis: 8 credits/min, 800/dag — US-aksjer + forex + krypto)
- `/technical_indicators` (RSI, MACD, ATR, ADX, BBANDS, SUPERTREND, ICHIMOKU — 100+): server-side TA, alle instrumenter.
- `/exchange_rate`, `/quote`, `/price`: FX inkl. USDNOK, rik snapshot.
- **Ikke gratis:** economic_calendar, etf-holdings, fundamentals, dedikert commodities, WebSocket → ikke planlegg rundt disse.

### Finnhub (gratis: 60 calls/min)
- `/calendar/economic` (CPI/NFP/FOMC/PMI — event-risk-timing), `/news` + `/news-sentiment` (FX, krypto, indeks).
- `/scan/support-resistance`, `/scan/pattern`, `/scan/technical-indicator`: **ferdigberegnede S/R-nivåer** — direkte nyttig for setup.
- `/forex/*`, `/crypto/candle`: FX + BTC/ETH OHLC.
- **Ingen COT-endpoint** → bruk CFTC direkte. ETF/insider/institusjonell = premium.

### USDA NASS QuickStats (gratis-nøkkel) — utover crop progress
- `statisticcat_desc=YIELD|PRODUCTION|STOCKS|AREA PLANTED|AREA HARVESTED|PRICE RECEIVED` for Corn/Wheat/Soy/Cotton.
- **Quarterly Grain Stocks** + **June Acreage (30. juni)** er markedsbevegende events. Per stat (IA/IL/KS/TX).
- Ingen Coffee/Sugar/Cocoa (ikke US-jordbruk) → bruk FAS PSD + FRED IMF-priser + CFTC COT.

### EIA Open Data v2 (gratis-nøkkel, ~5000 req/t) — utover ukentlig lager
| Rute | Hva | Spisser |
|---|---|---|
| `PET.W_EPC0_SAX_YCUOK_MBBL.W` | **Cushing** crude-lager (WTI-hub) | WTI |
| `PET.WCRFPUS2.W`, `PET.WGIRIUS2.W` | US crude-produksjon, **raffineri-utnyttelse %** | WTI, Brent |
| `PET.WCESTUS1.W` | **SPR-lager** (politiske releases/refills) | WTI |
| `PET.WCREXUS2.W`/`WCEIMUS2.W` | Crude eksport/import | WTI–Brent-spread |
| `NG.NW2_EPG0_SWO_R3{1..4}_BCF.W` | **Regionalt** natgas-lager (East/Midwest/Mtn/Pacific/South-Central) | NatGas (basis-spikes) |
| STEO-serier | Short-Term Energy Outlook (forward-prognoser) | Crude, NatGas |

**Bekreftet 2026-05-29 mot live-nøkkel:** EIA-nøkkelen låser opp **14 datasett**, ikke bare
petroleum/natgas. Nye trade-relevante ruter (`api.eia.gov/v2/<rute>`):
| Rute | Hva | Spisser |
|---|---|---|
| `steo` | Short Term Energy Outlook — forward-prognoser for WTI/Brent/Henry Hub pris + produksjon/konsum | Crude, Brent, NatGas (forward) |
| `international` | Global produksjon/konsum/lager pr land+produkt (OPEC-supply) | Brent (globale balanser) |
| `nuclear-outages/us-nuclear-outages` | Kjernekraft offline → gass/kull-demand spiker | **NatGas** (sterk gratis driver) |
| `electricity/rto` | Daglig/timesvis kraftdrift (gass-fyrt demand) | NatGas (demand) |
| `coal/consumption-and-quality` | Kull-konsum → kull-til-gass-substitusjon | NatGas |
| `crude-oil-imports` | Import-kvantum pr kilde | WTI–Brent-spread |
Øvrige ruter (`total-energy`, `seds`, `aeo`, `ieo`, `densified-biomass`, `co2-emissions`) er for
lang-horisont/lite tradbare — droppes.

### USDA FAS + api.data.gov (én delt nøkkel — bekreftet mot live)
`FAS_API_KEY` = `USDA_API_KEY` = `API_DATA_GOV_KEY` (identiske). EIA-nøkkelen er separat.
| Endpoint | Hva | Spisser | Status |
|---|---|---|---|
| `api.fas.usda.gov/api/psd/...` | **PSD** — verdens produksjon/konsum/ending-stocks/S2U pr commodity+region (≈ strukturert WASDE) | Corn, Wheat, Soy, **+ softs** (kaffe/sukker/kakao/bomull) | ✅ verifisert (header `X-Api-Key`) |
| `api.fas.usda.gov/api/esr/...` | **Export Sales (ESR)** — ukentlig US-eksportsalg pr kornsort + destinasjon | Wheat (HRW/SRW/HRS/…), Corn, Soybeans, Cotton | ✅ verifisert — markedsbevegende ukentlig |
| `api.ers.usda.gov/data/...` | ERS økonomisk forskningsdata | makro-agri-kontekst | nøkkel gyldig (endepunkt-sti må bekreftes) |
| `developer.nrel.gov/api/...` + andre api.data.gov-etater | energi m.m. via gateway | situasjonsbestemt | ✅ gateway bekreftet (NREL svarte) |

Andre nøkler i `secrets.env` vi gjenbruker: `BEDROCK_AGSI_API_KEY`/`AGSI_API_KEY` (EU gass-lager),
`FRED_API_KEY`, `BEDROCK_NASS_API_KEY`, `TWELVEDATA_API_KEY`, `FINNHUB_API_KEY`.

---

## 3. Andre gratis kilder pr asset-klasse

### Edelmetaller (Gull, Sølv, Platina)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **LBMA priser JSON** | Daglige auksjonspriser USD/GBP/EUR | **GRATIS** `prices.lbma.org.uk/json/gold_pm.json` (+ silver, platinum) | benchmark alle |
| **CME COMEX warehouse** | Registrert/eligible lager | **GRATIS** XLS `cmegroup.com/delivery_reports/Gold_Stocks.xls` | tightness/squeeze |
| **World Gold Council / Goldhub** | ETF-holdings & flows, demand trends | **GRATIS** Excel | Gull (investeringsdemand) |
| **Silver Institute** | Årlig supply/demand, deficit | **GRATIS** PDF (årlig) | Sølv (strukturelt deficit) |
| ~~LBMA lease/GOFO~~ | leie-rater | **BETALT-FLAGG** — ikke lenger gratis, ingen god erstatning | — |

### Industrimetall (Kobber)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **LME warehouse** | Lager, live/cancelled warrants | **GRATIS** (dag-forsinket) på LME.com; API = betalt | Kobber |
| **SHFE weekly (eng)** | Shanghai kobber-lager | **GRATIS** `shfe.com.cn/eng/reports/...` | Kobber (Kina-demand) |
| **CME COMEX copper** | US kobber-lager | **GRATIS** XLS | arb LME/SHFE |
| **China PMI** | NBS Manufacturing PMI | **GRATIS** via FRED | Kobber (Dr. Copper) |
| Cochilco/Codelco | Chile produksjon | **SCRAPE** PDF | Kobber (supply) |

### Energi (WTI, Brent, NatGas)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **EIA** | Lager/produksjon/Cushing/SPR | **GRATIS-NØKKEL** (har) | WTI, Brent, NatGas |
| **Baker Hughes rig count** | NA+intl rigger, olje/gass-split | **GRATIS** Excel (fre 12:00 CT) | WTI (supply) |
| **EU AGSI+ (GIE)** | EU gass-lager, fill-level | **GRATIS-NØKKEL** `agsi.gie.eu` | NatGas/TTF |
| **JODI-Oil** | Produksjon/demand/lager 49+ land | **GRATIS** CSV (mnd) | WTI, Brent (globale balanser) |
| **OPEC MOMR** | Produksjon, demand-outlook | **GRATIS** PDF (mnd) | Brent |
| ~~Argus/Platts/Baltic~~ | margins/freight | **BETALT-FLAGG** — bygg crack selv fra EIA | — |

### FX-majors (EUR/GBP/JPY/CHF/CAD/AUD/NZD/NOK vs USD)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **BIS Data Portal** | Policy-renter (CBPOL) alle majors + REER/NEER | **GRATIS** SDMX `data.bis.org` | alle par (rentediff, verdsettelse) |
| **ECB / BoE / Norges Bank / Riksbank / SNB / BoC / RBA / RBNZ / BoJ** | Renter + FX | **GRATIS** API/CSV/SDMX | hver respektive valuta |

> Beste praksis: hent alle styringsrenter fra **BIS CBPOL** (ett datasett) for rentedifferensial-carry,
> og BIS REER som verdsettelses-overlay.

### Korn (Corn, Wheat, Soybeans)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **USDA FAS PSD Online** | Verdens supply/demand, ending stocks, S2U (≈ WASDE) | **GRATIS-NØKKEL** (har: api.data.gov) ✅ verifisert | alle korn (global balanse) |
| **USDA FAS Export Sales (ESR)** | Ukentlig US-eksportsalg pr kornsort + destinasjon | **GRATIS-NØKKEL** (samme nøkkel) ✅ verifisert | Wheat, Corn, Soybeans, Cotton |
| **USDA NASS** | US areal/yield/stocks | **GRATIS-NØKKEL** (har) | US-avlinger |
| **US Drought Monitor** | Tørke-alvor pr område | **GRATIS** REST `usdmdataservices.unl.edu` | US vær-risiko |
| **CONAB (Brasil)** | Brasil avlingssurvey | **SCRAPE**/PDF | Soya, Corn (Brasil) |
| **Open-Meteo** | Vær, GDD | **GRATIS** (har) | alle korn |

### Softs (Coffee, Sugar, Cocoa, Cotton)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **ICO (kaffe)** | I-CIP composite price | I-CIP PDF **GRATIS**; full Excel email-gated | Coffee |
| **UNICA (Brasil C-S)** | Sukkerrør-crush, sukker-vs-etanol-mix | **GRATIS** UNICAdata | Sukker (mix = driver) |
| **USDA FAS PSD** | Verdens sukker/bomull/kakao + India-sukker | **GRATIS** | alle softs |
| **Open-Meteo** | Brasil-frost (kaffe/sukker), V-Afrika harmattan | **GRATIS** | Coffee, Cocoa, Sugar |
| **ICE warehouse** | Sertifisert kaffe/kakao/sukker-lager | **SCRAPE** | Coffee, Cocoa |
| ~~ISO sukker / ICCO kakao~~ | bulletins | **BETALT-FLAGG** → bruk FAS PSD | — |

### Indeks (S&P 500)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **FRED** | Makro, VIX, kurve, stress | **GRATIS-NØKKEL** (har) | S&P |
| **CBOE Daily Market Statistics** | Put/call-ratio, volum | **GRATIS** CSV | S&P (sentiment) |
| **VIX term structure** | VIX vs VIX3M (contango/backwardation) | **GRATIS** CBOE + FRED | S&P |
| **AAII Sentiment** | Bull/bear/neutral % | **GRATIS** (core) | S&P (kontrarian) |

### Krypto (BTC/ETH)
| Kilde | Hva | Tilgang | Spisser |
|---|---|---|---|
| **CoinGecko** | Pris, market cap, dominans | **GRATIS-NØKKEL** (Demo 100/min) | BTC, ETH |
| **alternative.me Fear & Greed** | Sentiment-indeks | **GRATIS** `api.alternative.me/fng/` | BTC, ETH (kontrarian) |
| **mempool.space** | Fees, mempool, tx-stats | **GRATIS** REST | BTC (on-chain) |
| **blockchain.com charts** | Hashrate, aktive adresser | **GRATIS** | BTC (nettverk) |
| **CFTC COT (PRE)** | BTC-futures-positioning | **GRATIS** API | BTC (institusjonell) |
| ~~Glassnode/CryptoQuant/Nansen~~ | netflows | **BETALT-FLAGG** → bruk mempool/blockchain.com | — |

---

## 3b. Posisjoneringsdybde — COT / prime broker / dealer gamma (fra video)

Kilde: Nicholas Crown, "Why did no one tell me this" — posisjoneringsdata slår pris (etterslepende).
Tre kilder vurdert ærlig mot hva vi får gratis:

| Kilde | Verdikt | Detalj |
|---|---|---|
| **CFTC COT** | ✅ **Har** — kjernen | "Crowded vs rom å bevege seg på" = MM-percentil (planlagt). Ingen ny jobb. |
| **Prime brokerage** (GS-stil brutto/netto hedgefond) | ❌ **Ikke gratis** | Proprietær (GS Marquee, kun institusjonelle kunder). Ingen gratis API/proxy. Svake proxyer: 13F (45d lag, kun longs), short interest (FINRA, 2-ukentlig), nyhets-sitater. **Ikke implementer — ville vært støy forkledd som signal.** |
| **Dealer gamma (GEX)** | ✅ **Implementerbart** (utvalgte instrumenter) | Positive gamma-nivåer = faktiske S/R. Passer setup-generatoren som ny nivåtype. |

### Dealer gamma — hva vi får gratis (verifisert 2026-05-29)
| Instrument | Kilde | Tilgang | Kvalitet |
|---|---|---|---|
| **BTC / ETH** | Deribit public API | **GRATIS** ingen auth — `/public/ticker` gir **gamma + OI + greeks** per kontrakt, `/public/get_book_summary_by_currency`, DVOL-indeks. Sanntid. | Ren — gamma servert ferdig, ingen Black-Scholes nødvendig |
| **S&P/indeks, Gull (GLD), Sølv (SLV), Olje (USO)** | yfinance/yahooquery + Nasdaq opsjonskjeder | **GRATIS** (~15 min forsinket, OI+IV, ingen greeks → regn BS-gamma selv) | Brukbar men skjør; EOD-OI begrenser intradag |
| **SPX gamma-nivåer (ferdig)** | Menthor Q gratis dagsrapport | **GRATIS-TIER** | Sanity-check/fallback, kun SPX/indeks |
| FX-par, kaffe/sukker/korn | — | ingen gratis listede opsjoner | ikke i fingerprint |

**Naiv DIY GEX:** `GEX_strike = gamma × OI × multiplier × spot² × 0.01 × fortegn` (dealer long puts /
short calls). Zero-gamma = der total-GEX krysser 0. Input: spot, strike, IV, OI, tid-til-utløp, rente.
**Forbehold (vær ærlig i UI):** naiv dealer-fortegn-antakelse + EOD-OI → *estimat*, ikke SpotGamma-kopi.
Retningsmessig nyttig for regime/nivåer, ikke presist intradag. "Sanntid" kun for Deribit/krypto.
Holder for **manuell swing-trading på daglige strukturnivåer** (som Regnbue er).

### Hvordan dette brukes i Regnbue
1. **Ny datakilde `gamma`** — Deribit (BTC/ETH) + opsjonskjeder (indeks/GLD/SLV/USO). Kun disse instrumentene.
2. **Ny nivåtype i setup-generatoren:** gamma-vegger + zero-gamma-flip → reelle S/R (videoens hovedpoeng).
3. **Ny driver `gamma_regime`:** long gamma = dempede bevegelser (strammere range, nærmere TP),
   short gamma = forsterkede (bredere SL, momentum-bias) — påvirker SL/TP-plassering.
4. Per-instrument-prinsippet styrer scope: kun instrumenter med gratis gamma får driveren; resten ignorerer.

---

## 4. Gotchas / flagg
- **LBMA lease/GOFO**, **ISO sukker**, **ICCO kakao**, **Glassnode/CryptoQuant netflows**, **Argus/Platts/Baltic
  freight** er ikke lenger gratis. Bruk angitte gratis-erstatninger.
- **Røyktest** regionale EIA-fasettkoder + et par FRED IMF/vol-tickere mot live-nøkler én gang (format stabilt,
  men EIA endrer av og til v2-koder).
- BIS CBPOL og USDA FAS PSD er "one-stop"-gevinster — hver dekker mange instrumenter gratis.

---

## 5. Neste steg
Denne kartleggingen mater de 22 fingerprintene (PLAN fase 3/4). Hvert instrument velger fra tabellene
over kun de driverne med ekte signal. Lavverdi-støy (seismikk, RSS-news-scoring, shipping, generisk
krypto-korr) tas ikke med — jf. dataaudit i `OVERSIKT_OG_FORSLAG.md` Del 2.
