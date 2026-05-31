"""Fase: scenario-generator (FHS) + CRPS/PIT — sanity (nettverksfritt)."""

from __future__ import annotations

import numpy as np

from setups.scenario import crps, ewma_vol, fhs_scenario, pit, pit_uniformity


def test_crps_rewards_accuracy():
    rng = np.random.default_rng(0)
    samples = rng.normal(0, 1, 2000)
    # Forventning sentrert på sannheten skal gi lavere CRPS enn en skjev en.
    assert crps(samples, 0.0) < crps(samples, 3.0)


def test_pit_bounds_and_uniformity():
    samples = np.linspace(-1, 1, 1000)
    assert pit(samples, -2) == 0.0
    assert pit(samples, 2) == 1.0
    # Perfekt kalibrerte PIT-er (uniforme) → lavt avvik.
    uni = list(np.linspace(0, 1, 1000))
    assert pit_uniformity(uni) < 0.1


def test_ewma_vol_positive_and_aligned():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, 500)
    vol = ewma_vol(r)
    assert len(vol) == len(r)
    assert np.all(vol > 0)


def test_fhs_scenario_shape_and_asof():
    rng = np.random.default_rng(2)
    r = rng.normal(0, 0.01, 600)
    sc = fhs_scenario(r, as_of_idx=400, horizon=20, n_paths=300)
    assert sc.samples.shape == (300,)
    # Median nær 0 for driftløs støy; fordelingen er ikke degenerert.
    assert abs(sc.quantile(0.5)) < 0.05
    assert sc.quantile(0.95) > sc.quantile(0.05)
