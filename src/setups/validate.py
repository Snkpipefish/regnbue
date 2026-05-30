"""Out-of-sample-validering av base-rate-gaten (audit V3).

Spørsmålet tesen står og faller på: har historiske analoger prediktiv verdi på data
de ALDRI er tunet på? Vi bruker kun train-panelet som analog-pool og måler på OOS-vinduet:

  1. Prediktiv verdi: for hver OOS-dato, predikér utfall = snitt-R blant train-naboer
     (innenfor likhetsterskel). Sammenlign fortegns-treff + snitt-R for prediksjon>0 vs <0.
  2. Gate-lift: utfallene til OOS-datoer der gaten ville PUBLISERT vs baseline (alle OOS).

Ingen terskler tunes her — de er låst i fingerprintet. Dette er ren validering.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from setups import gate, store
from setups.outcomes import Panel, build_panel
from setups.score.engine import load_fingerprint


@dataclass
class Validation:
    instrument: str
    n_train: int
    n_oos: int
    base_hit: float
    base_exp: float
    # prediktiv verdi (fortegn av nabo-snitt vs realisert)
    n_predicted: int
    sign_agreement: float
    exp_when_pred_bull: float
    exp_when_pred_bear: float
    # gate-lift
    n_gate_pass: int
    gate_hit: float
    gate_exp: float


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def validate(panel: Panel, *, band: float, min_effective_n: int,
             min_hit_rate_pct: float, min_expectancy_r: float) -> Validation:
    train, oos = panel.train(), panel.oos()
    base_hit = _mean([1.0 if r.hit else 0.0 for r in oos])
    base_exp = _mean([r.outcome_r for r in oos])

    pred_pairs: list[tuple[float, float]] = []   # (predikert nabo-snitt-R, realisert R)
    gate_rows = []
    for row in oos:
        neighbors = gate.neighbors_by_score(train, row.score, row.direction, band)
        if len(neighbors) >= min_effective_n:
            pred_pairs.append((_mean([n.outcome_r for n in neighbors]), row.outcome_r))
        br = gate.evaluate(train, row.score, row.direction, band=band,
                           min_effective_n=min_effective_n, min_hit_rate_pct=min_hit_rate_pct,
                           min_expectancy_r=min_expectancy_r)
        if br.passes:
            gate_rows.append(row)

    agree = _mean([1.0 if (p > 0) == (a > 0) else 0.0 for p, a in pred_pairs])
    exp_bull = _mean([a for p, a in pred_pairs if p > 0])
    exp_bear = _mean([a for p, a in pred_pairs if p <= 0])

    return Validation(
        instrument=panel.instrument, n_train=len(train), n_oos=len(oos),
        base_hit=base_hit, base_exp=base_exp,
        n_predicted=len(pred_pairs), sign_agreement=agree,
        exp_when_pred_bull=exp_bull, exp_when_pred_bear=exp_bear,
        n_gate_pass=len(gate_rows),
        gate_hit=_mean([1.0 if r.hit else 0.0 for r in gate_rows]),
        gate_exp=_mean([r.outcome_r for r in gate_rows]),
    )


def _all_fingerprints() -> list[str]:
    from setups.score.engine import FINGERPRINT_DIR
    return sorted(p.stem for p in FINGERPRINT_DIR.glob("*.yaml"))


def run(db_path=store.DEFAULT_DB_PATH, fingerprints=None,
        oos_start="2024-01-01") -> list[Validation]:
    fingerprints = fingerprints or _all_fingerprints()
    out: list[Validation] = []
    with store.connect(db_path) as conn:
        for name in fingerprints:
            fp = load_fingerprint(name)
            br = fp.get("base_rate", {})
            panel = build_panel(conn, fp, horizon=br.get("horizon_days", 30),
                                oos_start=oos_start)
            out.append(validate(
                panel, band=br.get("band", 0.1),
                min_effective_n=br.get("min_effective_n", 30),
                min_hit_rate_pct=br.get("min_hit_rate_pct", 55.0),
                min_expectancy_r=br.get("min_expectancy_r", 0.3)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="OOS-validering av base-rate-gaten.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    ap.add_argument("--oos-start", default="2024-01-01")
    args = ap.parse_args()
    for v in run(db_path=args.db, oos_start=args.oos_start):
        print(f"\n=== {v.instrument}  (train {v.n_train}, oos {v.n_oos})")
        print(f"  baseline OOS:    hit {v.base_hit*100:.0f}%  exp {v.base_exp:+.2f}R")
        print(f"  prediktiv (n={v.n_predicted}): "
              f"fortegns-treff {v.sign_agreement*100:.0f}%  "
              f"exp|pred+ {v.exp_when_pred_bull:+.2f}R  exp|pred- {v.exp_when_pred_bear:+.2f}R")
        print(f"  gate publiserte: n={v.n_gate_pass}  "
              f"hit {v.gate_hit*100:.0f}%  exp {v.gate_exp:+.2f}R")


if __name__ == "__main__":
    main()
