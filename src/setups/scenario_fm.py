"""Foundation-modell-utfordrer (gated) for scenario-generatoren.

Bruker en forhåndstrent tidsserie-foundation-modell (Chronos) til å produsere en
sannsynlighets-forward-fordeling, scoret med SAMME CRPS/PIT som FHS-baselinjen.
Tas KUN i bruk per instrument hvis den faktisk slår baselinjen out-of-sample
(kalibrerings-arbitrasje). Transfer learning → ingen trening på vårt tynne datagrunnlag.

Isolert i egen modul med lazy import, så resten av pakken ikke avhenger av torch.
"""

from __future__ import annotations

import math

import numpy as np

_PIPE = None


def _pipeline(model: str = "amazon/chronos-bolt-small"):
    global _PIPE
    if _PIPE is None:
        from chronos import BaseChronosPipeline  # lazy: krever torch
        _PIPE = BaseChronosPipeline.from_pretrained(model, device_map="cpu")
    return _PIPE


def chronos_scenario(closes: np.ndarray, as_of_idx: int, horizon: int = 20,
                     context: int = 512, model: str = "amazon/chronos-bolt-small") -> np.ndarray:
    """Forward H-dagers enkel-avkastnings-samples fra Chronos, as-of `as_of_idx`.

    Mater prisnivå-konteksten (kun ≤ as_of) og bygger en sti-fordeling via kvantil-prognosen.
    """
    import torch

    pipe = _pipeline(model)
    hist = closes[max(0, as_of_idx + 1 - context): as_of_idx + 1]
    ctx = torch.tensor(hist, dtype=torch.float32)
    # Chronos-Bolt gir kvantiler pr horisont-steg; vi henter et kvantil-rutenett.
    # Chronos-Bolt er trent på 0.1–0.9; hold oss innenfor for rettferdig/kalibrert prognose.
    qs = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    q, _mean = pipe.predict_quantiles(ctx, prediction_length=horizon, quantile_levels=qs)
    qarr = q[0].cpu().numpy()                      # (horizon, len(qs)) prisnivåer
    entry = float(closes[as_of_idx])
    # Trekk ett kvantil-nivå (samme persentil over hele banen = enkel, monoton bane),
    # og les av kumulativ avkastning ved horisontens slutt.
    samples = []
    for j in range(len(qs)):
        end_price = float(qarr[-1, j])
        samples.append(end_price / entry - 1.0)
    return np.array(samples)


def evaluate_chronos(closes: np.ndarray, *, start_idx: int, horizon: int = 20, step: int = 10,
                     model: str = "amazon/chronos-bolt-small") -> dict:
    """Samme CRPS/PIT-evaluering som FHS, men med Chronos — for direkte sammenligning."""
    from setups.scenario import crps, pit, pit_uniformity

    crps_scores, pits = [], []
    for i in range(start_idx, len(closes) - horizon, step):
        samples = chronos_scenario(closes, i, horizon=horizon, model=model)
        realized = float(closes[i + horizon]) / float(closes[i]) - 1.0
        if not math.isfinite(realized):
            continue
        crps_scores.append(crps(samples, realized))
        pits.append(pit(samples, realized))
    return {
        "n": len(crps_scores),
        "mean_crps": round(float(np.mean(crps_scores)), 5) if crps_scores else None,
        "pit_uniformity": round(pit_uniformity(pits), 3),
    }
