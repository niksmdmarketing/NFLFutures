"""Amendment 1, Test 1 (research/NBA_PLAYER_FIRST_RULE.md): does the player-strength term still add on top of the availability layer?"""
import json, os
import numpy as np, pandas as pd
from scipy.stats import norm
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = pd.read_csv(os.path.join(ROOT, "data", "research", "nba_player_first_rows.csv"))
AV = os.environ.get("AVAIL_CSV", "/tmp/claude-0/-home-claude-nflfutures/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/nba_avail2_games.csv")
A = pd.read_csv(AV)
A["covered"] = A.covered.astype(str) == "True"
A = A[["date", "home", "away", "covered", "v2_base_h", "v2_base_a", "v2_official_h", "v2_official_a"]].drop_duplicates(["date", "home", "away"])
D = D.merge(A, on=["date", "home", "away"], how="left")
D["sB"] = (D.s_prev_h - D.s_prev_a) * D.pace
D["av_base"] = (D.v2_base_h - D.v2_base_a)
D["av_off"] = (D.v2_official_h - D.v2_official_a)


def wf(D, cols, first):
    p = np.full(len(D), np.nan); sd = np.full(len(D), np.nan)
    for t in sorted(D.season.unique()):
        if t < first:
            continue
        tr, te = (D.season < t).to_numpy(), (D.season == t).to_numpy()
        ok = tr & D[cols].notna().all(axis=1).to_numpy()
        if ok.sum() < 500:
            continue
        X = np.column_stack([np.ones(ok.sum())] + [D.loc[ok, c] for c in cols])
        b = np.linalg.lstsq(X, D.margin[ok], rcond=None)[0]
        sd[te] = (D.margin[ok] - X @ b).std()
        p[te] = np.column_stack([np.ones(te.sum())] + [D.loc[te, c] for c in cols]) @ b
    return p, sd


def compare(D, avcol, first, mask, boot):
    pa, sa = wf(D, ["mA", avcol], first)
    pc, sc = wf(D, ["mA", "sB", avcol], first)
    m = mask & ~np.isnan(pa) & ~np.isnan(pc)
    y = D.margin.to_numpy()[m]
    ea, ec = (y - pa[m]) ** 2, (y - pc[m]) ** 2
    w = (y > 0).astype(float)
    ll = lambda p, s: float(np.mean(-(w * np.log(np.clip(norm.cdf(p / s), 1e-4, 1)) + (1 - w) * np.log(np.clip(1 - norm.cdf(p / s), 1e-4, 1)))))
    d = ea - ec
    S = D.season.to_numpy()[m]
    seasons = sorted(set(S))
    bys = {int(s): round(float(d[S == s].mean()), 3) for s in seasons}
    rng = np.random.default_rng(4)
    if boot == "season":
        per = {s: d[S == s] for s in seasons}
        bs = [np.concatenate([per[s] for s in rng.choice(seasons, len(seasons))]).mean() for _ in range(2000)]
    else:
        wk = (D.season.astype(str) + "_" + D.week.astype(str)).to_numpy()[m]
        keys = np.unique(wk)
        per = {k: d[wk == k] for k in keys}
        bs = [np.concatenate([per[k] for k in rng.choice(keys, len(keys))]).mean() for _ in range(2000)]
    lo = float(np.percentile(bs, 10))
    res = {"games": int(m.sum()), "seasons": len(seasons), "mse_A'": round(float(ea.mean()), 3), "mse_C'": round(float(ec.mean()), 3),
           "gain": round(float(d.mean()), 3), "gain_pct": round(float(d.mean() / ea.mean() * 100), 2), "lower90_one_sided": round(lo, 3),
           "by_season": bys, "seasons_better": int(sum(v > 0 for v in bys.values())),
           "ll_A'": round(ll(pa[m], sa[m]), 4), "ll_C'": round(ll(pc[m], sc[m]), 4)}
    need = 8 if boot == "season" else len(seasons) // 2 + 1
    res["gates"] = {"mse_lower_bound_above_0": lo > 0, f"better_in_{need}+_seasons": res["seasons_better"] >= need, "logloss": res["ll_C'"] < res["ll_A'"]}
    res["pass"] = all(res["gates"].values())
    return res


out = {"1a_v2_base_all_seasons": compare(D, "av_base", 2015, (D.season >= 2015).to_numpy(), "season"),
       "1b_official_reports_2022_on": compare(D[D.covered.fillna(False).astype(bool)].reset_index(drop=True), "av_off", 2022,
                                               (D[D.covered.fillna(False).astype(bool)].season >= 2022).to_numpy(), "week"),
       "reported_official_all_covered_2021_on": compare(D[D.covered.fillna(False).astype(bool)].reset_index(drop=True), "av_off", 2021,
                                                        (D[D.covered.fillna(False).astype(bool)].season >= 2021).to_numpy(), "week")}
out["match_rate"] = round(float(D.v2_base_h.notna().mean()), 3)
json.dump(out, open(os.path.join(ROOT, "research", "nba_player_first_avail_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
