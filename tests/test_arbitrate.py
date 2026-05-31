"""Kalibrerings-arbitrasje — torch-fri sti (FHS-only) + ruting-logikk."""

from __future__ import annotations

import numpy as np

from setups.scenario_arbitrate import compare, published_scenario


def test_compare_fhs_only_path():
    rng = np.random.default_rng(0)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))
    res = compare("X", closes, start_idx=520, horizon=20, step=40, use_fm=False)
    assert res["winner"] == "FHS"        # uten FM kan bare baselinjen vinne
    assert res["fm"] is None
    assert res["fhs"]["mean_crps"] is not None


def test_published_scenario_falls_back_to_fhs():
    rng = np.random.default_rng(1)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))
    sc = published_scenario("X", closes, model="FHS", horizon=20)
    assert sc is not None
    s = sc.summary()
    assert s["p05"] < s["median"] < s["p95"]
