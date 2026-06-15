"""Fase etter-MVP: OOS-validering — logikk på syntetisk panel."""

from __future__ import annotations

from setups.outcomes import Panel, PanelRow
from setups.validate import _driver_ic, validate, walk_forward


def _row(date, score, direction, r, oos):
    return PanelRow(date=date, vector={"d": score}, direction=direction, outcome_r=r,
                    hit=(r > 0), score=score, oos=oos)


def test_validate_detects_predictive_signal():
    # Train: LONG-stater med score ~0.5 ga vinnere (+2R); OOS-staten ligner → predikerer bull.
    train = [_row(f"2020-01-{i+1:02d}", 0.5, "LONG", 2.0, False) for i in range(40)]
    oos = [_row(f"2024-01-{i+1:02d}", 0.5, "LONG", 2.0, True) for i in range(20)]
    v = validate(Panel("X", train + oos), band=0.1, min_effective_n=30,
                 min_hit_rate_pct=55, min_expectancy_r=0.3)
    assert v.n_train == 40 and v.n_oos == 20
    assert v.n_predicted == 20            # alle OOS har nok naboer
    assert v.sign_agreement == 1.0        # alle predikert + og realisert +
    assert v.n_gate_pass == 20            # sterk evidens → gaten publiserer
    assert v.gate_exp == 2.0


def test_validate_no_neighbors_when_too_far():
    train = [_row(f"2020-01-{i+1:02d}", 0.0, "LONG", 2.0, False) for i in range(40)]
    oos = [_row(f"2024-01-{i+1:02d}", 0.9, "LONG", 2.0, True) for i in range(20)]
    v = validate(Panel("X", train + oos), band=0.1, min_effective_n=30,
                 min_hit_rate_pct=55, min_expectancy_r=0.3)
    assert v.n_predicted == 0 and v.n_gate_pass == 0


def test_driver_ic_separates_signal_from_noise():
    # 'good' korrelerer perfekt med utfallet; 'flat' er konstant → ingen IC (#13).
    rows = []
    for i in range(40):
        s = (i - 20) / 20.0
        rows.append(PanelRow(date=f"2024-{(i % 12) + 1:02d}-01",
                             vector={"good": s, "flat": 0.5},
                             direction="LONG" if s >= 0 else "SHORT",
                             outcome_r=2.0 * s, hit=s > 0, score=s, oos=True))
    ic = _driver_ic(rows)
    assert ic["good"][0] > 0.95 and ic["good"][1] == 40   # sterk forward-IC
    assert ic["flat"][0] == 0.0                           # konstant → null varians → IC 0


def test_walk_forward_expanding_yearly_folds():
    # Tre år med konsistent vinner-state → expanding-window walk-forward gir 2023 + 2024 som
    # test-folder (2022 finnes bare som train), begge med perfekt fortegns-treff.
    rows = []
    for y in (2022, 2023, 2024):
        for i in range(40):
            rows.append(PanelRow(date=f"{y}-{(i % 12) + 1:02d}-15", vector={"d": 0.5},
                                 direction="LONG", outcome_r=2.0, hit=True, score=0.5))
    folds = walk_forward(Panel("X", rows), band=0.1, min_effective_n=30)
    years = [f.fold for f in folds]
    assert years == ["2023", "2024"]
    f24 = next(f for f in folds if f.fold == "2024")
    assert f24.n_train == 80 and f24.n_predicted == 40 and f24.sign_agreement == 1.0
