"""Datavask for `prices`: reparer skalerings-glitcher (10er-potens-feil).

Noen feeds (oppdaget på SPX500 nov 2016–jan 2017) noterer enkelte barer på feil
skala — typisk ×0.1 eller ×10 av riktig nivå. Vi oppdager barer som ligger en
10er-potens unna sin lokale median og reparerer OHLC tilbake til riktig skala.

Idempotent. Kjør etter henting:  python -m setups.clean
"""

from __future__ import annotations

import argparse
import statistics

from setups import store

FACTORS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]


def clean_symbol(conn, symbol: str, tf: str = "D1", tol: float = 0.5, win: int = 15) -> int:
    """Reparer skala-glitcher for ett symbol. Returnerer antall reparerte barer.

    Sekvensiell venstre-til-høyre mot en ETTERSLEPENDE median av allerede *korrigerte*
    closes. Da forblir referansen ren selv om annenhver bar i en periode er ×0.1 (slik
    forurensning ville ødelagt en sentrert median). Kun 10er-potens-avvik repareres —
    ekte store bevegelser (ingen 10x-faktor passer) lar vi stå.
    """
    rows = conn.execute(
        "SELECT ts, open, high, low, close FROM prices WHERE symbol=? AND tf=? ORDER BY ts",
        (symbol, tf),
    ).fetchall()
    corrected = [r[4] for r in rows]   # løpende korrigerte closes (referanse)
    factor = [1.0] * len(rows)
    for i in range(len(rows)):
        ref_pool = [corrected[j] for j in range(max(0, i - win), i) if corrected[j] > 0]
        if len(ref_pool) < 3 or corrected[i] <= 0:
            continue
        ref = statistics.median(ref_pool)
        if abs(corrected[i] / ref - 1.0) <= tol:
            continue
        best = min(FACTORS, key=lambda f: abs(corrected[i] * f - ref))
        if best != 1.0 and abs(corrected[i] * best - ref) / ref <= tol:
            corrected[i] *= best
            factor[i] = best
    fixes = [(rows[i][1] * factor[i], rows[i][2] * factor[i], rows[i][3] * factor[i],
              rows[i][4] * factor[i], symbol, tf, rows[i][0])
             for i in range(len(rows)) if factor[i] != 1.0]
    conn.executemany(
        "UPDATE prices SET open=?, high=?, low=?, close=? WHERE symbol=? AND tf=? AND ts=?",
        fixes,
    )
    return len(fixes)


def clean_all(db_path=store.DEFAULT_DB_PATH, tf: str = "D1") -> dict[str, int]:
    counts: dict[str, int] = {}
    with store.connect(db_path) as conn:
        syms = [r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM prices WHERE tf=?", (tf,))]
        for s in syms:
            n = clean_symbol(conn, s, tf)
            if n:
                counts[s] = n
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Vask prices for skalerings-glitcher.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()
    counts = clean_all(args.db)
    if counts:
        print("Reparerte barer:")
        for s, n in counts.items():
            print(f"  {s}: {n}")
    else:
        print("Ingen skala-glitcher funnet.")


if __name__ == "__main__":
    main()
