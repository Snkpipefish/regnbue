"""Scenario-generator: betinget forward-fordeling via Filtered Historical Simulation (FHS).

Moderne, riktig-skalert kjerne (ingen overtilpasning):
  * volatilitet fra avkastning (EWMA) — kan byttes til range-basert (Yang-Zhang) senere,
  * standardiserte residualer z = r/σ (renset for vol-regime),
  * stationary block bootstrap (Politis–Romano) av z → bevarer autokorrelasjon/trend,
  * skalér med dagens σ_t → forward-baner som fanger vol-klynging + fete haler.

Output er en FORDELING (kvantiler, P(opp), forventet avkastning), ikke en retning.
Evalueres ærlig med CRPS + PIT (se `evaluate`). Alt as-of: bruker kun data ≤ beslutningsdato.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Scenario:
    as_of_idx: int
    horizon: int
    samples: np.ndarray      # H-dagers kumulative avkastninger (n_paths,)

    def quantile(self, q: float) -> float:
        return float(np.quantile(self.samples, q))

    def prob_up(self) -> float:
        return float(np.mean(self.samples > 0))

    def expected(self) -> float:
        return float(np.mean(self.samples))

    def summary(self) -> dict:
        return {
            "p05": round(self.quantile(0.05), 4), "p25": round(self.quantile(0.25), 4),
            "median": round(self.quantile(0.50), 4), "p75": round(self.quantile(0.75), 4),
            "p95": round(self.quantile(0.95), 4),
            "prob_up": round(self.prob_up(), 3), "expected": round(self.expected(), 4),
        }


def log_returns(closes: np.ndarray) -> np.ndarray:
    return np.diff(np.log(closes))


def ewma_vol(returns: np.ndarray, lam: float = 0.94) -> np.ndarray:
    """EWMA betinget volatilitet (RiskMetrics). var_t = λ var_{t-1} + (1-λ) r_{t-1}^2."""
    var = np.empty(len(returns))
    v = float(np.var(returns[:20])) if len(returns) >= 20 else float(np.var(returns) or 1e-8)
    for i, r in enumerate(returns):
        var[i] = v
        v = lam * v + (1 - lam) * r * r
    return np.sqrt(var)


def _stationary_block_indices(n: int, horizon: int, mean_block: int,
                              rng: np.random.Generator) -> np.ndarray:
    """Politis–Romano stationary bootstrap: geometriske blokklengder, sirkulær indeksering."""
    p = 1.0 / mean_block
    idx = np.empty(horizon, dtype=np.int64)
    cur = rng.integers(0, n)
    for t in range(horizon):
        idx[t] = cur
        if rng.random() < p:
            cur = rng.integers(0, n)       # nytt blokk-startpunkt
        else:
            cur = (cur + 1) % n             # fortsett blokken
    return idx


def fhs_scenario(returns: np.ndarray, as_of_idx: int, horizon: int = 20,
                 n_paths: int = 1000, mean_block: int = 5, lam: float = 0.94,
                 resid_pool: np.ndarray | None = None, seed: int = 0) -> Scenario:
    """FHS forward-fordeling as-of `as_of_idx` (bruker kun returns[:as_of_idx+1])."""
    hist = returns[: as_of_idx + 1]
    vol = ewma_vol(hist, lam)
    sigma_now = vol[-1]
    z = hist / vol                                   # standardiserte residualer
    pool = z if resid_pool is None else resid_pool   # ev. kryss-instrument-pool
    pool = pool[np.isfinite(pool)]
    # Robusthet: klipp ekstreme residualer (avvikende barer) så én glitch ikke gir
    # astronomiske bootstrap-baner (oppdaget på SPX500). ±8σ er rikelig for fete haler.
    pool = np.clip(pool, -8.0, 8.0)
    rng = np.random.default_rng(seed + as_of_idx)
    paths = np.empty(n_paths)
    n = len(pool)
    for k in range(n_paths):
        idx = _stationary_block_indices(n, horizon, mean_block, rng)
        # skalér residualer med dagens vol → daglige sjokk → kumulativ logg-avkastning
        paths[k] = float(np.sum(pool[idx] * sigma_now))
    return Scenario(as_of_idx, horizon, np.expm1(paths))   # tilbake til enkel avkastning


# --- sti-avhengig barriere-sannsynlighet (forward base-rate fra fordelingen) ---
@dataclass
class BarrierProb:
    n_paths: int
    prob_tp: float          # andel baner som treffer TP først
    prob_sl: float          # andel som treffer SL først
    prob_time: float        # andel som verken (tidsutløp)
    expectancy_r: float     # forventet utfall i R (TP=+rr, SL=-1, TIME=delvis)
    expectancy_ci: tuple[float, float]

    def summary(self) -> dict:
        return {
            "engine": "scenario",
            "n_paths": self.n_paths,
            "prob_tp": round(self.prob_tp, 4),
            "prob_sl": round(self.prob_sl, 4),
            "prob_time": round(self.prob_time, 4),
            "expectancy_r": round(self.expectancy_r, 4),
            "expectancy_ci": [round(self.expectancy_ci[0], 4), round(self.expectancy_ci[1], 4)],
        }


def fhs_barrier_prob(returns: np.ndarray, as_of_idx: int, *, direction: str,
                     tp_ret: float, sl_ret: float, horizon: int = 20, n_paths: int = 2000,
                     mean_block: int = 5, lam: float = 0.94,
                     resid_pool: np.ndarray | None = None, seed: int = 0,
                     swap: dict | None = None) -> BarrierProb:
    """Forward P(TP før SL) + expectancy fra FHS-baner, sti-avhengig (first-passage).

    `tp_ret`/`sl_ret` er POSITIVE avstander i enkel-avkastning fra entry til hhv. TP og SL
    (f.eks. 0.03 = 3 %). Retningen avgjør fortegnet på banen som er gunstig. Ved samtidig
    treff samme dag teller vi SL først (samme konservative konvensjon som triple_barrier).
    R: TP=+rr, SL=−1, tidsutløp = terminal bevegelse / risiko (delvis). Når `swap` er gitt
    (#10) trekkes carry-kostnad fra hver bane pr EKSAKT holdetid (cpd·dager/sl_ret i R).
    """
    if tp_ret <= 0 or sl_ret <= 0:
        raise ValueError("tp_ret og sl_ret må være positive avstander")
    rr = tp_ret / sl_ret
    hist = returns[: as_of_idx + 1]
    vol = ewma_vol(hist, lam)
    sigma_now = vol[-1]
    z = hist / vol
    pool = z if resid_pool is None else resid_pool
    pool = pool[np.isfinite(pool)]
    pool = np.clip(pool, -8.0, 8.0)
    rng = np.random.default_rng(seed + as_of_idx)
    n = len(pool)
    long = direction == "LONG"
    cpd = 0.0
    if swap:
        cpd = swap.get("long_cost_pct_per_day" if long else "short_cost_pct_per_day", 0.0)

    outcomes = np.empty(n_paths)
    n_tp = n_sl = n_time = 0
    for k in range(n_paths):
        idx = _stationary_block_indices(n, horizon, mean_block, rng)
        level = np.expm1(np.cumsum(pool[idx] * sigma_now))   # enkel-avkastning pr dag
        # gunstig/ugunstig grense avhengig av retning
        up_hit = np.flatnonzero(level >= (tp_ret if long else sl_ret))
        dn_hit = np.flatnonzero(level <= -(sl_ret if long else tp_ret))
        t_up = up_hit[0] if up_hit.size else horizon + 1
        t_dn = dn_hit[0] if dn_hit.size else horizon + 1
        # for LONG: TP=opp, SL=ned; for SHORT: TP=ned, SL=opp
        t_tp, t_sl = (t_up, t_dn) if long else (t_dn, t_up)
        if t_sl <= t_tp and t_sl <= horizon:          # SL først (tie → SL)
            outcomes[k] = -1.0
            held = t_sl + 1
            n_sl += 1
        elif t_tp < t_sl and t_tp <= horizon:
            outcomes[k] = rr
            held = t_tp + 1
            n_tp += 1
        else:                                          # tidsutløp: delvis R
            term = level[-1] if long else -level[-1]
            outcomes[k] = term / sl_ret
            held = horizon
            n_time += 1
        if cpd:
            outcomes[k] -= cpd * held / sl_ret         # carry over faktisk holdetid

    mean = float(np.mean(outcomes))
    se = float(np.std(outcomes, ddof=1) / math.sqrt(n_paths)) if n_paths > 1 else 0.0
    return BarrierProb(
        n_paths=n_paths, prob_tp=n_tp / n_paths, prob_sl=n_sl / n_paths,
        prob_time=n_time / n_paths, expectancy_r=mean,
        expectancy_ci=(mean - 1.96 * se, mean + 1.96 * se))


# --- ærlig evaluering: CRPS + PIT ---
def crps(samples: np.ndarray, y: float) -> float:
    """CRPS for et ensemble (lavere = bedre). Sortert O(n log n)-estimator."""
    x = np.sort(samples)
    n = len(x)
    term1 = float(np.mean(np.abs(x - y)))
    i = np.arange(1, n + 1)
    term2 = float(np.sum((2 * i - n - 1) * x)) / (n * n)   # = mean_{i,j}|x_i-x_j|
    return term1 - 0.5 * term2


def pit(samples: np.ndarray, y: float) -> float:
    """Probability Integral Transform: andel av samples <= realisert. Skal være ~Uniform(0,1)."""
    return float(np.mean(samples <= y))


def pit_uniformity(pits: list[float], bins: int = 10) -> float:
    """Avvik fra uniform kalibrering (0 = perfekt). Snitt |observert − forventet| pr bin."""
    if not pits:
        return float("nan")
    hist, _ = np.histogram(pits, bins=bins, range=(0, 1))
    expected = len(pits) / bins
    return float(np.mean(np.abs(hist - expected)) / expected)


def evaluate(returns: np.ndarray, *, start_idx: int, horizon: int = 20, step: int = 5,
             n_paths: int = 500, mean_block: int = 5) -> dict:
    """Gå over historikken (as-of), generer FHS-fordeling, scor mot faktisk utfall."""
    crps_scores: list[float] = []
    pits: list[float] = []
    closes_len = len(returns)
    for i in range(start_idx, closes_len - horizon, step):
        sc = fhs_scenario(returns, i, horizon=horizon, n_paths=n_paths, mean_block=mean_block)
        realized = math.expm1(float(np.sum(returns[i + 1: i + 1 + horizon])))
        crps_scores.append(crps(sc.samples, realized))
        pits.append(pit(sc.samples, realized))
    return {
        "n": len(crps_scores),
        "mean_crps": round(float(np.mean(crps_scores)), 5) if crps_scores else None,
        "pit_uniformity": round(pit_uniformity(pits), 3),
    }
