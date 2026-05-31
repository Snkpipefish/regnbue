"""Kalibrerings-arbitrasje — nyvinningen: rut per instrument til best-kalibrerte modell.

For hvert instrument sammenlignes scenario-modellene (FHS-baseline vs foundation-modell
Chronos) på SAMME out-of-sample CRPS/PIT, og vi velger den som faktisk er best. Foundation-
modellen «fortjener plassen» kun der den slår baselinjen. Resultatet er en ruting-tabell;
den publiserte forward-fordelingen hentes så fra vinner-modellen.

FM er valgfri (torch): mangler den, faller alt tilbake til FHS — ærlig og robust.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from setups import store
from setups.scenario import Scenario, evaluate, fhs_scenario, log_returns

DEFAULT_OUT = Path("web/data/scenario_models.json")


def _fm_available() -> bool:
    try:
        import chronos  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def compare(symbol: str, closes: np.ndarray, *, start_idx: int, horizon: int = 20,
            step: int = 20, use_fm: bool = True) -> dict:
    """Sammenlign FHS vs FM på OOS-CRPS/PIT for ett instrument; kår en vinner."""
    returns = log_returns(closes)
    fhs = evaluate(returns, start_idx=start_idx, horizon=horizon, step=step, n_paths=400)
    result = {"symbol": symbol, "horizon": horizon, "fhs": fhs, "fm": None,
              "winner": "FHS", "n": fhs["n"]}
    if use_fm and _fm_available():
        from setups.scenario_fm import evaluate_chronos
        try:
            fm = evaluate_chronos(closes, start_idx=start_idx, horizon=horizon, step=step)
            result["fm"] = fm
            if fm["mean_crps"] is not None and fhs["mean_crps"] is not None \
                    and fm["mean_crps"] < fhs["mean_crps"]:
                result["winner"] = "FM"
        except Exception as e:  # FM er best-effort; baseline står uansett
            result["fm_error"] = str(e)
    return result


def published_scenario(symbol: str, closes: np.ndarray, model: str, *,
                       horizon: int = 20) -> Scenario | None:
    """Forward-fordeling as-of siste bar fra valgt modell (FM faller tilbake til FHS)."""
    returns = log_returns(closes)
    as_of = len(returns) - 1
    if model == "FM" and _fm_available():
        from setups.scenario_fm import chronos_scenario
        try:
            samples = chronos_scenario(closes, len(closes) - 1, horizon=horizon)
            return Scenario(as_of, horizon, samples)
        except Exception:
            pass
    return fhs_scenario(returns, as_of, horizon=horizon)


def _closes(conn, symbol: str) -> np.ndarray:
    return np.array([r[0] for r in conn.execute(
        "SELECT close FROM prices WHERE symbol=? AND tf='D1' ORDER BY ts", (symbol,))])


def route_all(db_path=store.DEFAULT_DB_PATH, horizon: int = 20, step: int = 20,
              min_bars: int = 600, out=DEFAULT_OUT) -> dict:
    """Bygg ruting-tabell + publiser forward-scenario fra vinner-modell pr instrument."""
    table = {}
    with store.connect(db_path) as conn:
        syms = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM prices ORDER BY symbol")]
        for s in syms:
            cl = _closes(conn, s)
            if len(cl) < min_bars:
                continue
            cmp = compare(s, cl, start_idx=520, horizon=horizon, step=step)
            sc = published_scenario(s, cl, cmp["winner"], horizon=horizon)
            cmp["scenario"] = sc.summary() if sc else None
            table[s] = cmp
            tag = cmp["winner"]
            fmc = cmp["fm"]["mean_crps"] if cmp["fm"] else None
            print(f"  {s:<12} vinner={tag:<3} FHS={cmp['fhs']['mean_crps']} FM={fmc}")
    payload = {"generated_horizon_days": horizon, "models": table}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, indent=2))
    fm_wins = sum(1 for v in table.values() if v["winner"] == "FM")
    print(f"\nSkrev {out}: {len(table)} instr, FM vinner {fm_wins}, FHS {len(table) - fm_wins}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Kalibrerings-arbitrasje FHS vs FM pr instrument.")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--step", type=int, default=20)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    route_all(db_path=args.db, horizon=args.horizon, step=args.step, out=args.out)


if __name__ == "__main__":
    main()
