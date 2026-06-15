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
SWAP_RATES_PATH = Path(__file__).resolve().parents[3] / "config" / "swap_rates.yaml"
_SWAP_RATES: dict | None = None


def _swap_rates() -> dict:
    """Sentral, dokumentert swap-/carry-tabell (#10), lastet én gang og cachet."""
    global _SWAP_RATES
    if _SWAP_RATES is None:
        try:
            with open(SWAP_RATES_PATH) as fh:
                _SWAP_RATES = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            _SWAP_RATES = {}
    return _SWAP_RATES


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
        fp = yaml.safe_load(fh)
    # Flett inn swap/carry fra den sentrale tabellen (nøklet på filstamme), med mindre
    # fingerprintet definerer `swap:` selv. Gjør expectancy ærlig (#10, PLAN §5b).
    if fp is not None and "swap" not in fp:
        swap = _swap_rates().get(path.stem)
        if swap:
            fp["swap"] = swap
    return fp


def _aggregate(weighted_sum: float, weight_total: float, abs_weighted_sum: float,
               agg: dict) -> float:
    """Slå sammen driver-bidrag til samlet score. Standard = lineær (vektet snitt).

    `method: agreement` (#9): skaler det lineære snittet med driver-ENIGHET, så et signal
    der drivere drar mot hverandre (0.6 og −0.3 → snitt 0.3) dempes ift. ett der alle peker
    samme vei. enighet = |Σ w·s| / Σ w·|s| ∈ [0,1] (1 = ingen kansellering). `gamma` styrer
    skarpheten; gamma=0 ⇒ identisk med lineær (inneholder lineær som spesialtilfelle). Dette
    er parameter-lett og lærer ingenting fra utfall (ingen overtilpasning) — det øker presisjon
    ved å kreve samstemte drivere, ikke å fabrikkere edge.
    """
    if weight_total == 0:
        return 0.0
    base = weighted_sum / weight_total
    if agg.get("method") == "agreement":
        agreement = abs(weighted_sum) / abs_weighted_sum if abs_weighted_sum else 1.0
        return base * (agreement ** float(agg.get("gamma", 1.0)))
    return base


def score_instrument(ctx: ScoreContext, fingerprint: dict) -> ScoreResult:
    results: list[DriverResult] = []
    weighted_sum = 0.0
    weight_total = 0.0
    abs_weighted_sum = 0.0

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
            abs_weighted_sum += weight * abs(res.score)
        results.append(res)

    score = _aggregate(weighted_sum, weight_total, abs_weighted_sum,
                       fingerprint.get("aggregation", {}))
    grade = grade_score(score, fingerprint.get("grade_thresholds"))
    return ScoreResult(
        instrument=fingerprint.get("id", "?"),
        ticker=fingerprint.get("ticker", "?"),
        as_of=ctx.as_of,
        score=round(score, 4),
        grade=grade,
        drivers=results,
    )
