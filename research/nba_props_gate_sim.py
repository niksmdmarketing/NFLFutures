"""End-to-end false-positive simulation of the G2 gate (Amendment 18). Synthetic rows only; no price data, no outcomes read.
No-edge world: the model is the market plus independent noise, the close is the market plus independent noise, best prices carry a
random book spread. Counts how often the full CLV gate (n, dates, close coverage, lb90 > 0, binding floor) passes.
Usage: python research/nba_props_gate_sim.py [n_sims] [edge]   (edge 0 = null; >0 injects that much information into the close)"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba_props_price_test as PT  # noqa: E402

LOGIT = lambda p: np.log(p / (1 - p))
SIG = lambda z: 1 / (1 + np.exp(-z))


def world(rng, n=1200, edge=0.0, dates=60):
    mk = SIG(rng.normal(0, 0.55, n))
    info = rng.normal(0, 0.12, n)                      # what the close learns after entry
    close = SIG(LOGIT(mk) + info + rng.normal(0, 0.05, n))
    model = SIG(LOGIT(mk) + edge * info + rng.normal(0, 0.12, n))   # edge 0: model noise is independent of the close
    spread = rng.uniform(0.0, 0.03, (n, 2))             # best-of-books price spread over the consensus price
    vig = 1.04
    return pd.DataFrame(dict(date=rng.integers(0, dates, n).astype(str), market_over=mk, model_over=model, close_market_over=close,
                             best_over=(1 + spread[:, 0]) / (mk * vig), best_under=(1 + spread[:, 1]) / ((1 - mk) * vig)))


def g2_pass(D):
    B = PT.bets(D.assign(over=0), 0.05)
    s = PT.clv_summary(B)
    if s.get("n", 0) < 200 or s.get("dates", 0) < 20 or not s.get("close_coverage_ok", False):
        return None
    ctl = PT.placebo_arms(D, n_perm=200)
    return bool(s["clv_lb90"] > 0 and ctl["exceeds_binding"]), ctl["perm_null_mean"], ctl["perm_null_bonferroni_q"], s["clv_mean"]


def main(n_sims=300, edge=0.0):
    PT.BOOT = 500
    rng = np.random.default_rng(20261107)
    res = [g2_pass(world(rng, edge=edge)) for _ in range(n_sims)]
    eligible = [r for r in res if r is not None]
    passes = sum(r[0] for r in eligible)
    print(f"edge={edge} sims={n_sims} eligible={len(eligible)} passes={passes} rate={passes / max(1, len(eligible)):.3%}")
    if eligible:
        print(f"mean CLV {np.mean([r[3] for r in eligible]):+.4f}  null mean {np.mean([r[1] for r in eligible]):+.4f}  null q98.3 {np.mean([r[2] for r in eligible]):+.4f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300, float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
