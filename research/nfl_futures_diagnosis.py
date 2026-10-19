"""NFL caution investigation, step 3: WHERE does the futures error occur? Diagnostic replay (no model or setting changes).
Seasons 2013-2025, checkpoints before the season and after weeks 4, 8, 12, 16. Two models, both out of sample, both without the
QB layers (no weekly QB history in the replay):
  v4wf   : v4 components with walk-forward weights (model/replay/nfl_wf_coef.json), v4 simulation (scale 0.89, tau 5, sigma 11.37, hfa 1.8)
  v5like : engine ratings (recency 4, shrinkage 60, walk-forward weights from data/research/nfl_eng_h4a60.npz), v5 simulation
           (scale 0.89, tau 4, sigma 12, hfa 1.8, playoff home edge 4)
Per checkpoint and team it records expected final wins, the simulated 10th/90th percentiles and sd of final wins, the actual wins,
and the five futures probabilities with outcomes. Separately, at the end of each regular season it simulates the playoffs from the
ACTUAL field and seeds (diagnostic only: an earlier forecast could not know the field).
Usage: python research/nfl_futures_diagnosis.py [first] [last]   -> research/nfl_futures_diagnosis_rows.csv, _playoff_rows.csv
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nfl_backtest as B  # noqa: E402
import nfl_engine as E  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, TIX, games, load_pbp  # noqa: E402

N = int(os.environ.get("DIAG_SIMS", "3000"))
CHECK = [0, 4, 8, 12, 16] if os.environ.get("DIAG_FIELD_ONLY") != "1" else []   # DIAG_FIELD_ONLY=1: only the actual-field playoff check
WF = json.load(open(os.path.join(ROOT, "model", "replay", "nfl_wf_coef.json")))["seasons"]
V4 = dict(scale=0.89, tau=5.0, sigma=11.37, hfa=1.8, hfa_post=None)
V5 = dict(scale=0.89, tau=4.0, sigma=12.0, hfa=1.8, hfa_post=4.0)
E.EFF_ALPHA = 60.0
ENG = np.load(os.path.join(ROOT, "data", "research", "nfl_eng_h4a60.npz"), allow_pickle=True)


def eng_weights(y):
    X, yv, s = ENG["X"], ENG["y"], ENG["s"]
    sd = X[s < 2013].std(0)
    sd[sd == 0] = 1
    m = Ridge(alpha=ratings.P["alpha"]).fit(X[s < y] / sd, yv[s < y])
    return m.coef_ / sd


def playoffs_given_field(R, seeds, tau, sigma, hpo, rng):
    """seeds: {conf: [team idx seed1..7]}. Returns P(conference champion), P(title) per team idx."""
    Rs = R[None, :] + rng.normal(0, tau, (N, len(R)))
    u = rng.random((N, 16))
    pc, pt = np.zeros(len(R)), np.zeros(len(R))
    for s in range(N):
        gi, champs = 0, []
        for c in (0, 1):
            sd = seeds[c]
            rank = {t: i for i, t in enumerate(sd)}
            alive = [sd[0]] if len(sd) == 7 else [sd[0], sd[1]]          # 7-seed format (2020+): one bye; 6-seed (to 2019): two
            for h, a in (((1, 6), (2, 5), (3, 4)) if len(sd) == 7 else ((2, 5), (3, 4))):
                x, y = sd[h], sd[a]
                alive.append(x if u[s, gi] < norm.cdf((Rs[s, x] - Rs[s, y] + hpo) / sigma) else y); gi += 1
            alive.sort(key=lambda t: rank[t])
            r2 = []
            while alive:
                x, y = alive.pop(0), alive.pop(-1)
                r2.append(x if u[s, gi] < norm.cdf((Rs[s, x] - Rs[s, y] + hpo) / sigma) else y); gi += 1
            r2.sort(key=lambda t: rank[t])
            x, y = r2
            ch = x if u[s, gi] < norm.cdf((Rs[s, x] - Rs[s, y] + hpo) / sigma) else y; gi += 1
            pc[ch] += 1
            champs.append(ch)
        x, y = champs
        pt[x if u[s, gi] < norm.cdf((Rs[s, x] - Rs[s, y]) / sigma) else y] += 1
    return pc / N, pt / N


def run(y, g, st):
    cur_all, pri = load_pbp(y), load_pbp(y - 1)
    out = B.outcomes(g, y)
    ew = eng_weights(y)
    reg_all = g[(g.season == y) & (g.game_type == "REG")]
    last = int(reg_all.week.max())
    rows, prow = [], []
    rng = np.random.default_rng(y)
    for w in CHECK + ["end"]:
        wk = last if w == "end" else w
        gg = g.copy()
        m = (gg.season == y) & (gg.game_type == "REG") & (gg.week > wk)
        gg.loc[m, "result"] = np.nan
        cur = cur_all[(cur_all.week <= wk) & (cur_all.season_type == "REG")] if wk else cur_all.iloc[0:0]
        ratings.P["coef"] = WF[str(y)]["coef"]
        b4, _ = ratings.base_ratings(cur, pri, gg, y)
        _, XT = E.team_features(cur, pri, gg, y, wk + 1, 4.0, 0, False)
        b5 = XT @ ew
        greg = gg[(gg.season == y) & (gg.game_type == "REG")]
        for name, base, P in (("v4wf", b4, V4), ("v5like", b5, V5)):
            R = P["scale"] * (base - base.mean())
            if w == "end":
                s = st[st.season == y]
                seeds = {}
                for c, conf in ((0, "AFC"), (1, "NFC")):
                    x = s[(s.conf == conf) & s.seed.notna()].sort_values("seed")
                    seeds[c] = [TIX[FIX.get(t, t)] for t in x.team]
                if any(len(v) not in (6, 7) for v in seeds.values()):
                    continue
                hpo = P["hfa"] if P["hfa_post"] is None else P["hfa_post"]
                pc, pt = playoffs_given_field(R, seeds, P["tau"], P["sigma"], hpo, rng)
                for c in (0, 1):
                    for sd_i, t in enumerate(seeds[c]):
                        prow.append(dict(season=y, model=name, team=TEAMS[t], seed=sd_i + 1, rating=float(R[t]), p_conf=float(pc[t]), p_title=float(pt[t]),
                                         y_conf=float(out["conf"][t]), y_title=float(out["sb"][t])))
                continue
            res = simulate.simulate(greg, R, N, P["tau"], P["sigma"], P["hfa"], hfa_post=P["hfa_post"])
            W = res["wins"]
            for i, t in enumerate(TEAMS):
                rows.append(dict(season=y, week=w, model=name, team=t, exp_w=float(W[:, i].mean()), sd_w=float(W[:, i].std()),
                                 q10=float(np.percentile(W[:, i], 10)), q90=float(np.percentile(W[:, i], 90)), wins=float(out["wins"][i]),
                                 p_div=float(res["div"][i]), p_playoff=float(res["playoff"][i]), p_seed1=float(res["seed1"][i]),
                                 p_conf=float(res["conf"][i]), p_title=float(res["sb"][i]), y_div=float(out["div"][i]),
                                 y_playoff=float(out["playoff"][i]), y_seed1=float(out["seed1"][i]), y_conf=float(out["conf"][i]),
                                 y_title=float(out["sb"][i])))
        print(y, w, flush=True)
    return rows, prow


if __name__ == "__main__":
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    st = pd.read_csv(os.path.join(ROOT, "data", "nfl_standings.csv"))
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2013
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    R_, PR = [], []
    for y in range(first, last + 1):
        a, b = run(y, g, st)
        R_ += a
        PR += b
        if os.environ.get("DIAG_FIELD_ONLY") == "1":
            pd.DataFrame(PR).to_csv(os.path.join(ROOT, "research", "nfl_futures_diagnosis_playoff_rows_2013_19.csv"), index=False)
            continue
        pd.DataFrame(R_).to_csv(os.path.join(ROOT, "research", "nfl_futures_diagnosis_rows.csv"), index=False)
        pd.DataFrame(PR).to_csv(os.path.join(ROOT, "research", "nfl_futures_diagnosis_playoff_rows.csv"), index=False)
