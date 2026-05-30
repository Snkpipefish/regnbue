"""Base-rate-gatekeeper (skjerpet etter audit K2/V3).

Analoger matches på **aggregert score + retning** (kalibrering: "når modellen historisk
var ~så bullish, hva skjedde de neste N dagene?"). Dette er dimensjonsreduksjon gjort
riktig — vi matcher på det vi faktisk vedder på, ikke hele driver-vektoren (4D-nærmeste-nabo
ble for glissent og publiserte aldri; OOS-validering 2026-05-30).

En setup slippes gjennom kun hvis:
  * naboer = train-datoer med samme retning og **|score − current| <= bånd**,
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


def neighbors_by_score(rows: list[PanelRow], current_score: float, direction: str,
                       band: float) -> list[PanelRow]:
    """Train-datoer med samme retning og aggregert score innenfor båndet."""
    return [r for r in rows
            if r.direction == direction and abs(r.score - current_score) <= band]


def evaluate(rows: list[PanelRow], current_score: float, direction: str, *,
             band: float = 0.1, min_effective_n: int = 30,
             min_hit_rate_pct: float = 55.0, min_expectancy_r: float = 0.3) -> BaseRate:
    """Vurder en setup mot historiske analoger (matchet på score-bånd + retning)."""
    neighbors = neighbors_by_score(rows, current_score, direction, band)
    n = len(neighbors)
    if n == 0:
        return BaseRate(0, 0.0, (0.0, 0.0), 0.0, (0.0, 0.0), False,
                        "ingen historiske analoger i score-båndet")

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
