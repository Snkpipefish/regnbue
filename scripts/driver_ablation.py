"""Driver-ablasjon: mål OOS-effekten av å FJERNE én driver fra hvert fingerprint.

Motoren renormaliserer allerede over tilgjengelige drivere, så «ablasjon» = å droppe driver-
specen; de gjenværende vektene re-normaliseres automatisk. Verktøyet RØRER IKKE produksjons-
fingerprintene — det laster, kopierer, fjerner driveren i minnet og sammenligner OOS.

Forhåndsregistrert hypotese (se EXPERIMENTS.md): `cot_spec_net_percentile` bærer ikke konsistent
forward-edge (driver-IC sprikende/kontrær i 2026-06-valideringen). Å fjerne den skal IKKE svekke
OOS sign-agreement på tvers; den kan bedre den der COT-IC var negativ.

Kjør:  python scripts/driver_ablation.py [--driver cot_spec_net_percentile] [--oos-start 2025-01-01]
"""
from __future__ import annotations

import argparse
import copy

from setups import store
from setups.outcomes import build_panel
from setups.score.engine import FINGERPRINT_DIR, load_fingerprint
from setups.validate import validate

STEP = 5


def _sign(panel_v) -> float:
    return panel_v.sign_agreement * 100


def main() -> None:
    ap = argparse.ArgumentParser(description="OOS driver-ablasjon (forhåndsregistrert).")
    ap.add_argument("--driver", default="cot_spec_net_percentile")
    ap.add_argument("--oos-start", default="2025-01-01")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()

    names = sorted(p.stem for p in FINGERPRINT_DIR.glob("*.yaml"))
    deltas: list[float] = []
    with store.connect(args.db) as conn:
        print(f"# ablasjon av '{args.driver}'  oos_start={args.oos_start}  step={STEP}\n",
              flush=True)
        for name in names:
            fp = load_fingerprint(name)
            if not any(d["name"] == args.driver for d in fp.get("drivers", [])):
                continue
            br = fp.get("base_rate", {})
            hz = br.get("horizon_days", 30)
            kw = dict(band=br.get("band", 0.1), min_effective_n=br.get("min_effective_n", 30),
                      min_hit_rate_pct=br.get("min_hit_rate_pct", 55.0),
                      min_expectancy_r=br.get("min_expectancy_r", 0.3), horizon_days=hz)
            try:
                base = validate(build_panel(conn, fp, horizon=hz, oos_start=args.oos_start,
                                            step=STEP), **kw)
                fp2 = copy.deepcopy(fp)
                fp2["drivers"] = [d for d in fp2["drivers"] if d["name"] != args.driver]
                abl = validate(build_panel(conn, fp2, horizon=hz, oos_start=args.oos_start,
                                           step=STEP), **kw)
            except Exception as e:  # noqa: BLE001
                print(f"{name:10s} FEIL: {e}", flush=True)
                continue
            d = _sign(abl) - _sign(base)
            deltas.append(d)
            print(f"{name:10s} sign base={_sign(base):3.0f}%  ablert={_sign(abl):3.0f}%  "
                  f"Δ={d:+4.0f}pp   exp|pred+ base={base.exp_when_pred_bull:+.2f} "
                  f"abl={abl.exp_when_pred_bull:+.2f}", flush=True)
    if deltas:
        mean = sum(deltas) / len(deltas)
        better = sum(1 for d in deltas if d > 0)
        print(f"\n# snitt Δ sign-agreement = {mean:+.1f}pp over {len(deltas)} instr "
              f"({better} bedre, {len(deltas)-better} verre/likt)", flush=True)
        print("# Tolkning: Δ≈0 ⇒ COT er støy (kan fjernes trygt); Δ>0 ⇒ COT skader; "
              "Δ<0 ⇒ COT bidrar.", flush=True)


if __name__ == "__main__":
    main()
