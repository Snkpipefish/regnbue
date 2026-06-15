"""Fase: scenario-generator (FHS) + CRPS/PIT — sanity (nettverksfritt)."""

from __future__ import annotations

import numpy as np
import pytest

from setups.scenario import (
    crps,
    ewma_vol,
    fhs_barrier_prob,
    fhs_scenario,
    pit,
    pit_uniformity,
)


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


def test_fhs_barrier_prob_partitions_and_is_direction_symmetric():
    rng = np.random.default_rng(3)
    rets = rng.normal(0, 0.012, 600)
    # Eksplisitt symmetrisk, driftløs residual-pool (z og −z) → ingen retnings-bias fra
    # finite-sample-drift (z = r/σ recentres ikke, så empirisk drift ville ellers favorisert
    # én retning over 20 steg). Da MÅ LONG og SHORT gi ~lik P(TP).
    sd = float(np.std(rets))
    sym_pool = np.concatenate([rets / sd, -rets / sd])
    kw = dict(tp_ret=0.03, sl_ret=0.03, horizon=20, n_paths=4000, resid_pool=sym_pool, seed=1)
    long = fhs_barrier_prob(rets, len(rets) - 1, direction="LONG", **kw)
    short = fhs_barrier_prob(rets, len(rets) - 1, direction="SHORT", **kw)
    # Sannsynlighetene partisjonerer (TP+SL+TIME=1).
    assert abs(long.prob_tp + long.prob_sl + long.prob_time - 1.0) < 1e-9
    # Symmetrisk null-drift → LONG og SHORT har ~lik P(TP).
    assert abs(long.prob_tp - short.prob_tp) < 0.06


def test_fhs_barrier_prob_monotone_in_barrier_distance():
    rng = np.random.default_rng(4)
    rets = rng.normal(0, 0.012, 600)
    easy = fhs_barrier_prob(rets, len(rets) - 1, direction="LONG", tp_ret=0.02, sl_ret=0.06,
                            horizon=20, n_paths=4000, seed=1)   # nær TP, fjern SL
    hard = fhs_barrier_prob(rets, len(rets) - 1, direction="LONG", tp_ret=0.06, sl_ret=0.02,
                            horizon=20, n_paths=4000, seed=1)   # fjern TP, nær SL
    assert easy.prob_tp > hard.prob_tp


def test_fhs_barrier_prob_rejects_nonpositive_distance():
    rng = np.random.default_rng(5)
    rets = rng.normal(0, 0.01, 200)
    with pytest.raises(ValueError):
        fhs_barrier_prob(rets, len(rets) - 1, direction="LONG", tp_ret=0.0, sl_ret=0.02)


def test_fhs_barrier_prob_swap_lowers_expectancy_not_probs():
    rng = np.random.default_rng(6)
    rets = rng.normal(0, 0.012, 600)
    kw = dict(direction="LONG", tp_ret=0.03, sl_ret=0.03, horizon=20, n_paths=4000, seed=2)
    free = fhs_barrier_prob(rets, len(rets) - 1, **kw)
    costed = fhs_barrier_prob(rets, len(rets) - 1, **kw,
                              swap={"long_cost_pct_per_day": 0.002})
    # Carry trekkes fra hver bane → lavere expectancy; barrierene (P(TP)) flyttes ikke.
    assert costed.expectancy_r < free.expectancy_r
    assert costed.prob_tp == free.prob_tp and costed.prob_sl == free.prob_sl
