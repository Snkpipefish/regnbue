# Regnbue — DECISIONS (låste valg)

Endres bare ved bevisst ny beslutning. Format: dato — valg — kort begrunnelse.

- **2026-05-29 — Navn/tema: Regnbue** (regnbue-tema i UI).
- **2026-05-29 — Ingen kodekopiering** fra #1/#2. Grønt-mark, egen kode; gjenbruk kun datakilder,
  data og API-nøkler + inspirasjon. (Bruker: "nei vi skal ikke kopiere".)
- **2026-05-29 — Ingen bot.** Manuell trading; output publiseres på ny public GitHub Pages-side.
- **2026-05-29 — Nivå-koordinater regnes på Skillings prisfeed** (cTrader Open API, read-only OHLC).
  Futures/COT/EIA kun til bias/regime. Begrunnelse: Skilling priser cash-CFD med basis mot futures;
  #1/#2 løste ikke dette.
- **2026-05-29 — Alle ~22 instrumenter** bedrock trader er i scope.
- **2026-05-29 — Bias-data seedes fra `~/bedrock/bedrock.db`** (lese-only), eget lean fetch holder fersk.
- **2026-05-29 — Public repo**; Claude oppretter GitHub-repo + Pages (fase 7).
- **2026-05-29 — Lavverdi-kilder droppes** (seismikk, oilgas-RSS, news, shipping, krypto-sentiment).
- **2026-05-29 — Prime brokerage-data utelates** (ikke gratis); dealer gamma (GEX) inkluderes kun for
  instrumenter med gratis opsjonsdata (indeks, GLD/SLV/USO, BTC/ETH via Deribit).
- **2026-05-29 — Secrets i `~/.bedrock/secrets.env`** gjenbrukes; `API_DATA_GOV_KEY`=`FAS_API_KEY`=
  `USDA_API_KEY` (samme), `BEDROCK_EIA_API_KEY` separat.

## Etter audit #1 (2026-05-30 — se `AUDIT.md`)
- **MVP = 3 instrumenter** (Gull, EURUSD, Kaffe). No-copy beholdes; alle 22 utsettes til tesen er bevist. (K4)
- **Gate-statistikk skjerpes:** likhetsterskel på naboer + effektiv n (~30+) + konfidensintervall i UI.
  5-nabo-punktestimat forkastes som meningsløst. (K2)
- **Out-of-sample holdout** (siste 2–3 år) tunes aldri på; gate-ytelse rapporteres separat på OOS. (V3)
- **Look-ahead-vern bevises i `test_gate.py`** før noe base-rate-tall stoles på. (V4)
- **Koordinat-konsistens (K3):** én feed for både nivå og base-rate — avgjøres av K1-spiken. Ingen
  blanding av futures-base-rate med Skilling-nivå i samme expectancy-tall.
- **Gamma kun BTC/ETH (Deribit)** i/etter MVP; indeks/GLD/SLV/USO-gamma utsatt (mapping = støy for innsatsen). (V2)
- **Outcomes regnes ferskt** av Regnbue (unntak fra seed-engangs) — `analog_outcomes` mangler 5 instrumenter. (V1)
- **Regnbue er et daglig swing-verktøy** (kun D1-data) — ingen intradag-presisjon loves. (V5)
- **Fase −1 (cTrader-dybde-spike) gater fase 0.** Ingen kode skrives før K1 er målt.
- **2026-05-30 — K1 LØST (positivt):** Skilling/cTrader serverer dyp D1-historikk (Gull ~28 år, Olje
  ~20 år, Indeks ~14 år). **→ K3 låst:** regn BÅDE nivåer OG base-rate på Skilling-feed (ett
  koordinatsystem) — auditens foretrukne alternativ. Fase 0 ikke lenger blokkert. Tickere: GOLD,
  OIL WTI, OIL BRENT, SPX500. Spike: `scripts/ctrader_depth_spike.py` (read-only).

- **2026-05-30 — Lagringsformat: SQLite** (stdlib `sqlite3`, ett ett-filsystem). Begrunnelse: enkelt,
  samme som bedrock, holder for D1-mengder; parquet gir ingen gevinst på denne datastørrelsen.
- **2026-05-30 — Fase 0 ferdig:** git-repo (branch `main`), `pyproject.toml` (src-layout; deps
  pandas/pydantic/pyyaml/requests; dev ruff+pytest; extra `ctrader`), `src/setups/secrets.py`
  (env overstyrer fil, sti via `REGNBUE_SECRETS_ENV`), `tests/test_smoke.py` grønn. `scripts/` ekskl. fra ruff.

- **2026-05-30 — Base-rate-terskler LÅST (V3):** similarity 0.15 (euklidsk pr driver-dim), effektiv n≥30,
  hit-rate≥55% målt på **Wilson nedre CI-grense** (ikke punktestimat), expectancy≥0.3R med CI>0.
  Settes i fingerprintenes `base_rate:`. Tunes IKKE for å tvinge publisering; valideres mot OOS-holdout.
- **2026-05-30 — Utfall: triple-barrier i R** på Skilling-feed (SL=−1R, TP=+rr, ellers delvis ved tidsutløp),
  konservativt SL-først ved tvetydig bar. Nivåer = fraktal-swing (wing=3) + runde tall; SL bak swing − buffer×ATR.
- **2026-05-30 — Fase 4 ferdig (kjerne):** look-ahead-vern bevist (`test_gate.py`), 26 tester grønne.
  Coffee har kun ~5 år D1 på Skilling (gate avviser ærlig ved for få analoger).

- **2026-05-30 — Fase 7 LIVE:** public repo **github.com/Snkpipefish/regnbue** (konto Snkpipefish, ssh),
  Pages via GitHub Actions-deploy fra `web/` (ikke /docs) → **https://snkpipefish.github.io/regnbue/**.
  systemd-user-timer (`setups.timer`, hver 6h, linger på) kjører `update.sh`. Publisert `web/data/setups.json`
  committes (rot-`/data/` ignoreres, ikke `web/data/`). ALLE FASER 0–7 ferdig.

## Uavklart (ikke låst ennå)
- Panel-ytelse (~55s/instr) — caching/vektorisering ved behov.
- Skal live-beslutning bruke full historikk som naboer, eller kun train (OOS ekskludert som nå)?
