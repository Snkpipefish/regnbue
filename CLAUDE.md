# Regnbue — prosjekt-anker (les dette først)

Dette er **prosjekt #3** i et trading-system. Mål: en setup-generator som spisser datainnsamling
**per instrument** og genererer **realistiske** setups (base-rate-bevis), publisert på en **ny public
GitHub Pages-side** for **manuell** trading på **Skilling.com**. Ingen bot.

> **Flersesjongs-prosjekt.** Dette dokumentet + `STATE.md` gjør at et hvilket som helst kontekstvindu
> kan gjenoppta uten kontekst-tap. Følg resume-protokollen nederst.

## Les i denne rekkefølgen ved oppstart
1. **`CLAUDE.md`** (dette) — identitet, regler, dokumentkart.
2. **`STATE.md`** — hvor vi er NÅ: fase, hva er gjort, neste konkrete steg, åpne spørsmål.
3. **`TASKS.md`** — avkrysningsliste per fase.
4. **`PLAN.md`** — detaljert arkitektur + faser (den autoritative planen).
5. Referanse ved behov: **`DECISIONS.md`** (låste valg), **`DATA_KARTLEGGING.md`** (alle datakilder),
   **`OVERSIKT_OG_FORSLAG.md`** (hva #1/#2 gjør + tesen).

## Harde regler (ikke bryt uten ny beslutning i DECISIONS.md)
- **Ingen kodekopiering** fra `~/bedrock` eller `~/cot-explorer`. Bygg friskt; bruk dem kun som
  *inspirasjon* + for *datakilder/data/API-nøkler*.
- **Nivå-koordinater (entry/SL/TP) regnes ALLTID på Skillings egen prisfeed** (cTrader Open API,
  read-only OHLC). Futures/COT/EIA brukes kun til bias/retning/regime. (Se PLAN §5b.)
- **API-nøkler** ligger i `~/.bedrock/secrets.env` — aldri commit, aldri i repo, aldri i UI.
  `API_DATA_GOV_KEY` = `FAS_API_KEY` = `USDA_API_KEY` (samme); `BEDROCK_EIA_API_KEY` separat.
- **Bias-data seedes engangs** fra `~/bedrock/bedrock.db` (lese-only), ikke re-backfill.
- **Public repo** (kreves for Pages). Claude oppretter GitHub-repo + Pages i siste fase.
- Norsk er arbeidsspråk. Prosjektnavn/tema: **Regnbue** (regnbue-tema i UI).

## Resume-protokoll (kontekstbytte uten issues)
**Ved START av økt:** les rekkefølgen over. `STATE.md` forteller eksakt neste steg.
**UNDERVEIS:** kryss av i `TASKS.md` så snart en oppgave er ferdig (ikke i batch).
**Ved SLUTT av økt (eller når konteksten nærmer seg full):** oppdater `STATE.md`:
- Sett `Sist oppdatert`, `Nåværende fase`, hva som ble gjort, og **neste konkrete steg** (én setning).
- Noter nye åpne spørsmål. Logg nye låste valg i `DECISIONS.md`.
Slik kan neste vindu starte kaldt og fortsette presist.
