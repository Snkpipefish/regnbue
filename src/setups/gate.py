"""Base-rate-gatekeeper (skjerpet etter audit K2/V3).

En setup slippes gjennom kun hvis HISTORISKE analoger støtter den:
  * naboer = paneldatoer med samme retning og **likhetsavstand <= terskel**
    (ikke bare K nærmeste — vi krever ekte likhet),
  * **effektiv n >= ~30** (ellers er base-raten meningsløs),
  * hit-rate med **Wilson-konfidensintervall** over terskel (nedre grense, ikke punktestimat),
  * **expectancy i R** positiv med margin.

Terskler settes i fingerprintet (`base_rate:`) og LÅSES før resultater ses (audit V3).
Forkastede setups bærer `reason` + `n` + CI til UI-et.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from setups.outcomes import PanelRow


@dataclass(frozen=True)
class BaseRate:
    n: int
    hit_rate: float
    hit_rate_ci: tuple[float, float]
    expectancy_r: float
    expectancy_ci: tuple[float, float]
    passes: bool
    reason: str


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson-score-intervall for en andel (mer ærlig enn normal-approx ved liten n)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _mean_ci(values: list[float], z: float = 1.96) -> tuple[float, tuple[float, float]]:
    n = len(values)
    if n == 0:
        return (0.0, (0.0, 0.0))
    mean = sum(values) / n
    if n == 1:
        return (mean, (mean, mean))
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(var / n)
    return (mean, (mean - z * se, mean + z * se))


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Euklidsk avstand pr dimensjon (normalisert), kun over felles drivere."""
    keys = a.keys() & b.keys()
    if not keys:
        return float("inf")
    sq = sum((a[k] - b[k]) ** 2 for k in keys)
    return math.sqrt(sq / len(keys))


def evaluate(rows: list[PanelRow], current_vector: dict[str, float], direction: str, *,
             similarity: float = 0.15, min_effective_n: int = 30,
             min_hit_rate_pct: float = 55.0, min_expectancy_r: float = 0.3) -> BaseRate:
    """Vurder en setup mot historiske analoger."""
    neighbors = [r for r in rows
                 if r.direction == direction
                 and distance(r.vector, current_vector) <= similarity]
    n = len(neighbors)
    if n == 0:
        return BaseRate(0, 0.0, (0.0, 0.0), 0.0, (0.0, 0.0), False,
                        "ingen historiske analoger innenfor likhetsterskel")

    k = sum(1 for r in neighbors if r.hit)
    hit_rate = k / n
    hr_ci = _wilson(k, n)
    expectancy, exp_ci = _mean_ci([r.outcome_r for r in neighbors])

    reasons: list[str] = []
    if n < min_effective_n:
        reasons.append(f"for få analoger (n={n} < {min_effective_n})")
    if hr_ci[0] * 100 < min_hit_rate_pct:
        reasons.append(
            f"hit-rate nedre CI {hr_ci[0]*100:.0f}% < {min_hit_rate_pct:.0f}%")
    if expectancy < min_expectancy_r:
        reasons.append(f"expectancy {expectancy:+.2f}R < {min_expectancy_r:.2f}R")
    if exp_ci[0] <= 0:
        reasons.append(f"expectancy CI inkluderer ≤0 ({exp_ci[0]:+.2f}R)")

    passes = not reasons
    reason = "godkjent" if passes else "; ".join(reasons)
    return BaseRate(n, round(hit_rate, 4), (round(hr_ci[0], 4), round(hr_ci[1], 4)),
                    round(expectancy, 4), (round(exp_ci[0], 4), round(exp_ci[1], 4)),
                    passes, reason)
