"""Grade-mapping: samlet score [-1,1] → retning + bokstavgrad."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THRESHOLDS = {"A_plus": 0.55, "A": 0.40, "B": 0.25}


@dataclass(frozen=True)
class Grade:
    direction: str   # LONG | SHORT | NEUTRAL
    grade: str       # A+ | A | B | NONE
    strength: float  # |score|


def grade_score(score: float, thresholds: dict | None = None) -> Grade:
    t = thresholds or DEFAULT_THRESHOLDS
    strength = abs(score)
    if strength < t["B"]:
        return Grade("NEUTRAL", "NONE", round(strength, 4))
    direction = "LONG" if score > 0 else "SHORT"
    if strength >= t["A_plus"]:
        letter = "A+"
    elif strength >= t["A"]:
        letter = "A"
    else:
        letter = "B"
    return Grade(direction, letter, round(strength, 4))
