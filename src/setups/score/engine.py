"""Scoring-motor: kjør et fingerprint mot en ScoreContext og produser score + explain.

Vekter re-normaliseres over de driverne som faktisk har data, så manglende kilder ikke
trekker scoren kunstig mot null (i stedet rapporteres de i trace som `ok=False`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from setups.score.context import ScoreContext
from setups.score.drivers import DriverResult, get_driver
from setups.score.grade import Grade, grade_score

FINGERPRINT_DIR = Path(__file__).resolve().parents[3] / "config" / "instruments"


@dataclass
class ScoreResult:
    instrument: str
    ticker: str
    as_of: str
    score: float
    grade: Grade
    drivers: list[DriverResult] = field(default_factory=list)

    def explain(self) -> dict:
        """Full trace for UI/feilsøking."""
        return {
            "instrument": self.instrument,
            "ticker": self.ticker,
            "as_of": self.as_of,
            "score": round(self.score, 4),
            "direction": self.grade.direction,
            "grade": self.grade.grade,
            "strength": self.grade.strength,
            "drivers": [
                {
                    "name": d.name,
                    "ok": d.ok,
                    "score": d.score,
                    "weight": d.params.get("_weight"),
                    "contribution": d.params.get("_contribution"),
                    "value": d.value,
                    "detail": d.detail,
                }
                for d in self.drivers
            ],
        }


def load_fingerprint(name_or_path: str | Path) -> dict:
    path = Path(name_or_path)
    if not path.exists():
        path = FINGERPRINT_DIR / f"{name_or_path}.yaml"
    with open(path) as fh:
        return yaml.safe_load(fh)


def score_instrument(ctx: ScoreContext, fingerprint: dict) -> ScoreResult:
    results: list[DriverResult] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for spec in fingerprint.get("drivers", []):
        fn = get_driver(spec["name"])
        weight = float(spec.get("weight", 0.0))
        params = dict(spec.get("params", {}))
        res = fn(ctx, params)
        # Bær vekt + bidrag i params for explain-trace.
        res.params = {**params, "_weight": weight}
        if res.ok:
            contribution = weight * res.score
            res.params["_contribution"] = round(contribution, 4)
            weighted_sum += contribution
            weight_total += weight
        results.append(res)

    score = weighted_sum / weight_total if weight_total else 0.0
    grade = grade_score(score, fingerprint.get("grade_thresholds"))
    return ScoreResult(
        instrument=fingerprint.get("id", "?"),
        ticker=fingerprint.get("ticker", "?"),
        as_of=ctx.as_of,
        score=round(score, 4),
        grade=grade,
        drivers=results,
    )
