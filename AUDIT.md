# Regnbue — audit #1 (2026-05-30)

Kjørt i eget kontekstvindu, verifisert mot ekte kode i `~/bedrock` + `~/.bedrock/secrets.env`.
Beslutninger tatt som følge: se `DECISIONS.md` (2026-05-30-oppføringer). Sammendrag under.

## Verifiserte fakta (grunnlag)
- `prices` i `bedrock.db` kommer fra **Yahoo**, ikke cTrader (`backfill.py:173-176`). cTrader-klienten
  henter kun ~50 bars for bot-init, aldri historikk til DB. → cTrader som NIVÅ-feed er **uprøvd**.
- `analog_outcomes` er regnet på Yahoo-D1 (futures-koordinat), og dekker **17 av 22** instrumenter
  (mangler BTC, ETH, Copper, NaturalGas, Platinum).
- Ingen basis-/broker-prisjustering finnes i bedrock — ingen kode å "lære av" der.
- Look-ahead-vern finnes kun i backtest-laget (`AsOfDateStore`, `min_history_days=365`), ikke i
  selve `analog_outcomes`-bygget.

## KRITISK
- **K1 — cTrader som nivå-feed uprøvd/sannsynligvis for grunn.** Hele arkitekturen hviler på dette.
  Tiltak: read-only spike som måler faktisk D1-historikk-dybde for 3 instrumenter + rate-limits FØR alt annet.
  **→ LØST 2026-05-30:** spike viste dyp historikk (Gull ~28 år, Olje ~20 år, Indeks ~14 år). Ikke for grunn.
- **K2 — base-rate-gaten statistisk meningsløs.** K=5 fast uten likhetsterskel → "min 5 naboer" trivielt;
  hit-rate på 5 punkter har ±22pp feil. Krev likhetsterskel + effektiv n (~30+) + konfidensintervall.
- **K3 — base-rate på futures, setup på Skilling = blandet koordinatsystem.** Ett expectancy-tall måler
  feil ting. Velg ÉN feed for både nivå og base-rate (avhenger av K1), eller gjør nivåene futures-relative.
  **→ LØST 2026-05-30:** K1 ga dyp Skilling-historikk → regn BÅDE nivåer og base-rate på Skilling-feed.
- **K4 — no-copy × alle 22 × egen-alt er undervurdert scope.** Løst: no-copy beholdes, men **3-instrument MVP**.

## VIKTIG
- **V1** — 5 instrumenter mangler seedet base-rate → regn outcomes ferskt (unntak fra seed-regel).
- **V2** — gamma-mapping er støy for innsatsen utenom Deribit → gamma kun BTC/ETH, resten post-MVP.
- **V3** — terskler "justeres etter spissing" = overfitting → lås terskler, hold ut **out-of-sample**-vindu.
- **V4** — look-ahead-vern må reimplementeres bevisst → `test_gate.py` beviser as-of-vern FØR base-rate brukes.
- **V5** — kun D1-data → Regnbue er eksplisitt et **daglig swing-verktøy**, ikke intradag.

## MINDRE
- M1 swap ikke i noen kartlagt kilde (flagg manuelt i MVP). M2 ikke dra inn lavverdi-seed-tabeller.
- M3 FX vs råvare-timestamps ulike (sjekk tidssone i outcome-beregning). M4 vis n + CI i UI.
- M5 vurder realisert-vs-implisitt vol-spread + VIX-terminstruktur (billigere enn DIY-gamma).

## Konklusjon: **betinget GO**, men ikke på fase 0 ennå.
Gjør K1-spiken + lås K2/K3-statistikk + 3-instrument-MVP (gjort: K4). Farligste utgang er ikke høyt
fall, men at det *ser ut til å virke* (fine badges) mens det er overfittet støy på feil koordinatsystem.
