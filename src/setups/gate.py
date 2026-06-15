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
from datetime import date

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
    # uavhengige analoger (ikke-overlappende forward-vinduer); = n hvis horisont ukjent
    n_eff: int = 0


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson-score-intervall for en andel (mer ærlig enn normal-approx ved liten n)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _mean_ci(values: list[float], z: float = 1.96,
             n_eff: float | None = None) -> tuple[float, tuple[float, float]]:
    n = len(values)
    if n == 0:
        return (0.0, (0.0, 0.0))
    mean = sum(values) / n
    if n == 1:
        return (mean, (mean, mean))
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    # Standardfeilen bruker EFFEKTIV n (uavhengige obs), ikke rå n: overlappende forward-
    # vinduer er autokorrelerte, så rå-n gir for smal CI (falsk presisjon).
    m = n_eff if n_eff and n_eff > 1 else n
    se = math.sqrt(var / m)
    return (mean, (mean - z * se, mean + z * se))


def _effective_n(dates: list[str], horizon_days: int) -> int:
    """Antall ikke-overlappende forward-vinduer blant analog-datoene (grådig blokk-telling).

    To analoger hvis inngangsdatoer ligger < horizon dager fra hverandre deler det meste av
    forward-vinduet → tilnærmet ÉN uavhengig observasjon. Dette korrigerer den falske
    presisjonen rå n ga base-rate-CI-ene (audit-fiks).
    """
    if not dates:
        return 0
    ds = sorted(date.fromisoformat(d[:10]) for d in dates)
    blocks, last = 1, ds[0]
    for d in ds[1:]:
        if (d - last).days >= horizon_days:
            blocks += 1
            last = d
    return blocks


def neighbors_by_score(rows: list[PanelRow], current_score: float, direction: str,
                       band: float, coverage: frozenset[str] | None = None) -> list[PanelRow]:
    """Train-datoer med samme retning og aggregert score innenfor båndet.

    `coverage` (sett av tilgjengelige driver-navn): når gitt, kreves at naboen hadde NØYAKTIG
    samme tilgjengelige drivere. Da renormaliseres scoren over samme vekt-basis, så score=0.3
    betyr det samme på tvers av datoer (ellers er en 0.3 fra 2 drivere et annet objekt enn en
    0.3 fra 4 — #7). Utelatt = gammel oppførsel (matcher kun på skalar score).
    """
    out = [r for r in rows
           if r.direction == direction and abs(r.score - current_score) <= band]
    if coverage is not None:
        out = [r for r in out if frozenset(r.vector) == coverage]
    return out


def evaluate(rows: list[PanelRow], current_score: float, direction: str, *,
             band: float = 0.1, min_effective_n: int = 30,
             min_hit_rate_pct: float = 55.0, min_expectancy_r: float = 0.3,
             horizon_days: int | None = None,
             coverage: frozenset[str] | None = None) -> BaseRate:
    """Vurder en setup mot historiske analoger (matchet på score-bånd + retning).

    Når `horizon_days` er gitt brukes EFFEKTIV n (ikke-overlappende forward-vinduer) i både
    n-terskelen og CI-bredden, så autokorrelerte naboer ikke gir falsk statistisk presisjon.
    `coverage` aktiverer sammensetnings-bevisst matching (#7) — se `neighbors_by_score`.
    """
    neighbors = neighbors_by_score(rows, current_score, direction, band, coverage)
    n = len(neighbors)
    if n == 0:
        why = ("ingen historiske analoger med samme drivere i score-båndet"
               if coverage is not None else "ingen historiske analoger i score-båndet")
        return BaseRate(0, 0.0, (0.0, 0.0), 0.0, (0.0, 0.0), False, why, n_eff=0)

    n_eff = _effective_n([r.date for r in neighbors], horizon_days) if horizon_days else n
    k = sum(1 for r in neighbors if r.hit)
    hit_rate = k / n
    # CI-er på effektiv n: skaler Wilson-tellingen til n_eff (andelen er uendret) og bruk
    # n_eff i expectancy-standardfeilen.
    hr_ci = _wilson(hit_rate * n_eff, n_eff)
    expectancy, exp_ci = _mean_ci([r.outcome_r for r in neighbors], n_eff=n_eff)

    reasons: list[str] = []
    if n_eff < min_effective_n:
        reasons.append(f"for få uavhengige analoger (n_eff={n_eff} < {min_effective_n}; n={n})")
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
                    passes, reason, n_eff=n_eff)
