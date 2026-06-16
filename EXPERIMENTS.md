# Forhåndsregistrerte eksperimenter

Hensikt: teste hypoteser om driverne **uten p-hacking**. Prosjektregelen (`STATE.md`) er at
terskler/vekter/likhet ALDRI justeres etter at resultater er sett. Derfor registrerer vi
hypotese + nøyaktig endring + akseptkriterium HER, *før* vi endrer produksjons-fingerprintene,
og bekrefter på et vindu vi ikke har tunet på.

> Verktøy: `python scripts/driver_ablation.py --driver <navn> --oos-start <dato>`. Det laster
> fingerprintene, fjerner driveren i minnet (motoren renormaliserer resten) og sammenligner OOS.
> **Det endrer ingen produksjonsfiler.**

---

## EXP-1 — Fjerne `cot_spec_net_percentile` (COT)

**Status:** eksplorativ (hypotese generert fra OOS-validering 2026-06-15). Krever forward-bekreftelse
før produksjonsendring (se «Bekreftelse» under).

**Bakgrunn / hypotese.** Driver-IC fra hele-universet-valideringen (oos_start 2024-01-01) viser at
COT-driveren ikke bærer konsistent forward-edge: fortegnet spriker og er ofte kontrært
(gull −0.10, wti −0.13, corn −0.12, brent +0.10, men sp500 +0.20, usdjpy +0.19, sugar +0.20).
**H1:** å fjerne COT svekker IKKE OSS sign-agreement i snitt (Δ ≈ 0 eller positiv); den er støy
som kan fjernes trygt, og redusere overflate for overtilpasning.

**Nøyaktig endring som testes (låst).** Slett `cot_spec_net_percentile`-driver-specen fra hvert
fingerprint som har den; gjenværende vekter renormaliseres av motoren (ingen manuell omvekting).

**Akseptkriterium (låst FØR resultat).** Adopter fjerningen i produksjon kun hvis, på
bekreftelses-vinduet:
1. snitt Δ sign-agreement ≥ −2pp (ikke en meningsfull svekkelse), OG
2. ingen enkelt-instrument med ekte historikk (train ≥ 200) faller > 8pp i sign-agreement.
Ellers: behold COT (kanskje den bidrar på noen instrumenter selv om snittet er flatt).

**Bekreftelse (ikke sett ennå).** Det indikative resultatet under bruker oos_start 2025-01-01
(samme æra som hypotesen ble generert i → IKKE rent uavhengig). En ren bekreftelse krever det
**neste forward-kvartalet** etter 2026-06 ettersom data akkumuleres, kjørt ÉN gang mot kriteriet
over. Først da endres fingerprintene.

### Indikativt resultat (oos_start 2025-01-01) — **H1 AVKREFTET, behold COT**

`python scripts/driver_ablation.py --driver cot_spec_net_percentile --oos-start 2025-01-01`:

```
snitt Δ sign-agreement = +2.8pp over 22 instr (8 bedre, 14 verre/likt)
```

**Men snittet er villedende** — det er trukket opp av TYNN-DATA-instrumentene (train≈84, base-sign
nær 0 → ren støy): cocoa +59pp, coffee +41pp, soybean +38pp, wheat +26pp. Blant instrumentene med
**ekte historikk (train ≥ 200)** SKADER COT-fjerning nesten alltid:

| instrument | train | Δ sign | exp\|pred+ base→abl |
|---|---|---|---|
| audusd | 634 | **−19pp** | −0.17 → −1.04 |
| wti | 605 | **−15pp** | +0.52 → +0.01 |
| ethusd | 536 | **−13pp** | −0.09 → −0.14 |
| gold | 589 | **−10pp** | +0.93 → −0.60 |
| gbpusd | 631 | −8pp | +0.44 → −0.05 |
| eurusd/nasdaq/sp500 | ~620 | −6pp | (svekkes) |
| platinum/silver/brent | ~600 | −1…−4pp | (svekkes) |
| btcusd/usdjpy/sugar | ~200–600 | +3…+9pp | (blandet) |

**Beslutning: H1 avkreftet → BEHOLD COT.** Akseptkriteriet (ingen ekte-historikk-instrument
faller > 8pp) brytes klart (audusd −19, wti −15, ethusd −13, gull −10). Ingen produksjonsendring.

**Lærdom (viktig):** lav *marginal* driver-IC betyr IKKE at driveren er nytteløs. COT bidrar til
den retningsbestemte analog-strukturen selv der dens egen IC er svak — ablasjon (marginalt bidrag
i ensemblet) er mer informativ enn enkelt-driver-IC. Ikke fjern drivere på IC alene.

---

## EXP-2 — Intraday timesbasert reversal (GULL H1), netto etter spread

**Status:** kjørt 2026-06-16 → **AVKREFTET**. Parameter-fri ⇒ hver måned er OOS.

**Hypotese (H1).** Timesavkastning mean-reverterer (lag-1 autokorr < 0) → «fade forrige time»
(`s_t = −sign(r_{t-1})`, hold 1 time). Ingen tunede parametre.

**Nøyaktig oppsett (låst).** GULL H1 (9249 sammenhengende timesbarer, okt-2024→jun-2026; sesongbrudd
>2t droppet). Kostnad: gull-spread ~1.5 bps round-trip (0.75 bps × turnover). Kjørt via
`/tmp/intraday_check.py`-mønster.

**Akseptkriterium (låst FØR resultat).** Netto-bps/bar positiv i >60 % av måneder OG totalt positiv.

**Resultat.** Lag-1 autokorr **−0.0137** (reversal finnes, men bittelite). **Netto −0.53 bps/bar**,
kun **7/21 måneder positive**, hit-rate 46–52 % (myntkast). → **IKKE BESTÅTT.**

**Konklusjon/beslutning.** Mikro-reversal-effekten er REELL men **mindre enn spreaden** → ikke
tradbar netto på Skilling-kostnad. Bygger IKKE intraday-produkt på dette. H1-fetch-infrastruktur
beholdt (`ctrader_prices --period H1`). Høyere frekvens (M5/M1) har enda høyere spread-andel →
usannsynlig bedre; ikke prioritert. **Lærdom:** intraday-edger eksisterer på papiret men dør i
transaksjonskostnaden på likvide instrumenter — samme mønster som alt annet vi har testet.

## Mal for nye eksperimenter
- **Hypotese (H1):** …
- **Nøyaktig endring (låst):** …
- **Akseptkriterium (låst før resultat):** …
- **Bekreftelses-vindu (ikke sett):** …
- **Resultat + beslutning:** …
