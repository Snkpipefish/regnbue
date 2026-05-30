"""Pipeline: score → generator → gate → publish.

Bygger setups for alle MVP-fingerprint på siste tilgjengelige beslutningsdato (NIVÅ-feed)
og skriver `web/data/setups.json`. Antar at data allerede er seedet/hentet (`setups.seed`,
`setups.ctrader_prices`, `setups.fetch.fred`).

Bruk:  python -m setups.run [--db data/regnbue.db] [--out web/data/setups.json]
"""

from __future__ import annotations

import argparse

from setups import publish, store
from setups.generator import build_setup
from setups.outcomes import build_panel
from setups.score.engine import load_fingerprint


def _all_fingerprints() -> list[str]:
    from setups.score.engine import FINGERPRINT_DIR
    return sorted(p.stem for p in FINGERPRINT_DIR.glob("*.yaml"))


def _latest_date(conn, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT substr(MAX(ts),1,10) FROM prices WHERE symbol=?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def run(db_path=store.DEFAULT_DB_PATH, fingerprints: list[str] | None = None,
        out=publish.DEFAULT_OUT, as_of: str | None = None) -> dict:
    fingerprints = fingerprints or _all_fingerprints()
    setups = []
    resolved_as_of = as_of
    with store.connect(db_path) as conn:
        for name in fingerprints:
            fp = load_fingerprint(name)
            day = as_of or _latest_date(conn, fp["ticker"])
            if day is None:
                continue
            resolved_as_of = max(resolved_as_of or day, day)
            br = fp.get("base_rate", {})
            # Panel bygges én gang pr instrument (tregt: re-scorer pr dato).
            panel = build_panel(conn, fp, horizon=br.get("horizon_days", 30),
                                oos_start=br.get("oos_start"))
            setup = build_setup(conn, fp, day, panel=panel)
            if setup is not None:
                setups.append(setup)
    payload = publish.build_payload(setups, resolved_as_of or "")
    path = publish.write_json(payload, out)
    pub = sum(1 for s in payload["signals"] if s["published"])
    print(f"Skrev {path}: {len(payload['signals'])} signaler "
          f"({pub} publisert), as_of={payload['as_of']}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Kjør Regnbue-pipeline → setups.json")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    ap.add_argument("--out", default=str(publish.DEFAULT_OUT))
    ap.add_argument("--as-of", default=None, help="overstyr beslutningsdato (YYYY-MM-DD)")
    args = ap.parse_args()
    run(db_path=args.db, out=args.out, as_of=args.as_of)


if __name__ == "__main__":
    main()
