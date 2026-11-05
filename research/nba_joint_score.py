"""Score the joint-model futures replay against the gates of research/NBA_JOINT_TEAM_PLAYER_RULE.md (and Amendment 1).
Reads <dir>/<arm>/nba_<season>.csv for arms A0, A1, A2 (+ A2_noscale, A1_noleak, A2_noleak) in model/replay/nba_joint/ (override: arg 1).
Gain = baseline log loss - challenger log loss (clip 0.002-0.998), per team-market, mean over teams, then weekly checkpoints equally
weighted within a season, then the five markets (title, finals, division, No.1 seed, playoffs) equally, then seasons.
Gates compare A2 against A1 (G1-G6) and A2 against A0 (G7). Bootstrap: seasons resampled, 4,000 draws, seed 1, 90% lower bound = 5th pct.
Usage: python research/nba_joint_score.py [dir] [out.json] [seasons comma list for smoke tests]"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MK = {"title": ("p_title", "y_title"), "finals": ("p_conf", "y_finals"), "div": ("p_div", "y_div"),
      "seed1": ("p_seed1", "y_seed1"), "playoff": ("p_playoff", "y_playoff")}
TEST = [y for y in range(2016, 2027) if y != 2020]


def ll(p, y, lo=0.002):
    p = np.clip(np.asarray(p, float), lo, 1 - lo)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def load(d, arm, seasons):
    fs = [os.path.join(d, arm, f"nba_{y}.csv") for y in seasons]
    if not all(os.path.exists(f) for f in fs):
        return None
    D = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    for m, (pc, yc) in MK.items():
        D["ll_" + m] = ll(D[pc], D[yc])
    return D


def weekly(D):
    """season x week x market mean log loss over teams."""
    g = D.groupby(["season", "week"])
    out = pd.DataFrame({m: g["ll_" + m].mean() for m in MK})
    out["gp"] = g.gp_avg.first()
    return out


def stage(gp):
    return np.where(gp == 0, "pre", np.where(gp < 20, "early", np.where(gp < 42, "middle", "late")))


def pair(base, ch):
    """Per season x week x market gain (base - challenger) and the aggregates."""
    wb, wc = weekly(base), weekly(ch)
    G = (wb[list(MK)] - wc[list(MK)])
    G["gp"] = wb.gp
    G["stage"] = stage(G.gp.to_numpy())
    return G


def aggregates(G, boot=True):
    seas_m = G.groupby("season")[list(MK)].mean()          # season x market (weeks equally weighted)
    comb = seas_m.mean(axis=1)                              # five markets equally
    r = {"combined_mean": float(comb.mean()), "by_season": {int(k): round(float(v), 5) for k, v in comb.items()},
         "seasons_better": int((comb > 0).sum()), "seasons": int(len(comb)),
         "by_market": {m: round(float(seas_m[m].mean()), 5) for m in MK}}
    if boot:
        rng = np.random.default_rng(1)
        v = comb.to_numpy()
        means = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(4000)])
        r["lb90"] = float(np.percentile(means, 5))
        r["ub90"] = float(np.percentile(means, 95))
    st = {}
    for s in ("pre", "early", "middle", "late"):
        x = G[G.stage == s]
        if len(x):
            st[s] = round(float(x.groupby("season")[list(MK)].mean().mean(axis=1).mean()), 5)
    r["by_stage"] = st
    pre = G[G.stage == "pre"].groupby("season")[list(MK)].mean().mean(axis=1)
    r["preseason_only"] = {"mean": round(float(pre.mean()), 5), "better": int((pre > 0).sum()), "seasons": int(len(pre))}
    return r


def logit_slope(p, y):
    x = np.log(np.clip(p, 0.002, 0.998) / (1 - np.clip(p, 0.002, 0.998)))
    X = np.c_[np.ones(len(x)), x]
    b = np.array([0.0, 1.0])
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-8 * np.eye(2), X.T @ (y - mu))
        b = b + step
        if np.abs(step).max() < 1e-8:
            break
    return float(b[1])


def calibration(D):
    out = {}
    D = D.assign(stage=stage(D.gp_avg.to_numpy()))
    for m, (pc, yc) in MK.items():
        out[m] = {"all": round(logit_slope(D[pc].to_numpy(), D[yc].to_numpy()), 3)}
        for s in ("pre", "early", "middle", "late"):
            x = D[D.stage == s]
            if len(x) > 200:
                out[m][s] = round(logit_slope(x[pc].to_numpy(), x[yc].to_numpy()), 3)
    return out


def single_games(arms, seasons):
    """Supporting evidence only: pre-game margin MSE and win log loss from each checkpoint's ratings (needs the rating column).
    margin = rating gap + 2.2, pace 1, sigma 12.2; the same for every arm, so only the ratings differ."""
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    sys.path.insert(0, os.path.join(ROOT, "research"))
    import nba_backtest as B
    import nba as N
    from math import erf, sqrt
    boxes = B.load_boxes(max(seasons))
    res = {a: {"se": [], "ll": [], "early": [], "season": []} for a in arms}
    for y in seasons:
        g = B.season_games(boxes, y)
        for a, D in arms.items():
            if "rating" not in D:
                continue
            Dy = D[D.season == y]
            ck = Dy.drop_duplicates("week")[["week", "date", "gp_avg"]].assign(date=lambda x: pd.to_datetime(x.date)).sort_values("date")
            rat = {w: Dy[Dy.week == w].set_index("team").rating for w in ck.week}
            for r in g.itertuples():
                prev = ck[ck.date < r.date]
                if prev.empty:
                    continue
                w = prev.iloc[-1]
                rr = rat[w.week]
                pred = rr[r.home] - rr[r.away] + 2.2
                res[a]["se"].append((r.margin - pred) ** 2)
                p = 0.5 * (1 + erf(pred / 12.2 / sqrt(2)))
                p = min(max(p, 0.002), 0.998)
                res[a]["ll"].append(-np.log(p if r.margin > 0 else 1 - p))
                res[a]["early"].append(w.gp_avg < 20)
                res[a]["season"].append(y)
    out = {}
    for a, v in res.items():
        if not v["se"]:
            continue
        e = np.array(v["early"])
        out[a] = {"mse": round(float(np.mean(v["se"])), 3), "logloss": round(float(np.mean(v["ll"])), 5), "games": len(v["se"]),
                  "mse_early": round(float(np.mean(np.array(v["se"])[e])), 3) if e.any() else None,
                  "mse_later": round(float(np.mean(np.array(v["se"])[~e])), 3) if (~e).any() else None}
    return out


def main(d, out, seasons):
    arms = {a: load(d, a, seasons) for a in ("A0", "A1", "A2", "A2_noscale", "A1_noleak", "A2_noleak")}
    R = {"seasons": seasons}
    full = len(seasons) == len(TEST)
    G21 = pair(arms["A1"], arms["A2"])
    A = aggregates(G21)
    R["A2_vs_A1"] = A
    g1 = A["combined_mean"] > 0 and A["lb90"] > 0
    g2 = A["seasons_better"] >= 7
    g3 = all(v >= -0.0005 for v in A["by_market"].values())
    s26 = A["by_season"].get(2026)
    g4 = None if s26 is None else s26 >= -0.005
    g5 = all(v >= -0.002 for v in A["by_stage"].values())
    gates = {"G1_combined_gain_and_lb90_positive": g1, "G2_better_in_7_of_10": g2, "G3_no_market_below_-0.0005": g3,
             "G4_2026_not_below_-0.005": g4, "G5_no_stage_below_-0.002": g5}
    if arms["A2_noleak"] is not None and arms["A1_noleak"] is not None:
        An = aggregates(pair(arms["A1_noleak"], arms["A2_noleak"]), boot=False)
        R["absence_sensitivity_A2_vs_A1_noleak"] = An
        gates["G6_absence_sensitivity_gain_positive"] = An["combined_mean"] > 0
    if arms["A0"] is not None:
        A7 = aggregates(pair(arms["A0"], arms["A2"]))
        R["A2_vs_A0"] = A7
        gates["G7_A2_vs_A0_point_estimate_positive"] = A7["combined_mean"] > 0
        R["A1_vs_A0"] = aggregates(pair(arms["A0"], arms["A1"]))
    if arms["A2_noscale"] is not None:
        R["A2_noscale_vs_A1"] = aggregates(pair(arms["A1"], arms["A2_noscale"]))
    R["gates"] = gates
    R["all_gates_pass"] = bool(all(v is True for v in gates.values())) if full else None
    if full:
        R["calibration_slope"] = {a: calibration(arms[a]) for a in ("A0", "A1", "A2") if arms[a] is not None}
    sp = {}
    for a in ("A0", "A1", "A2"):
        if arms[a] is not None and "rating" in arms[a]:
            sp[a] = round(float(arms[a].groupby(["season", "week"]).rating.std().mean()), 3)
    R["rating_sd_across_teams_mean"] = sp
    if arms["A2"] is not None and "part_players" in arms["A2"]:
        g = arms["A2"].groupby(["season", "week"])
        vp, vt = g.part_players.var(), g.part_tau.var()
        R["A2_rating_variance_share_players"] = round(float((vp / (vp + vt)).mean()), 3)
        R["A2_player_tau_corr"] = round(float(g.apply(lambda x: np.corrcoef(x.part_players, x.part_tau)[0, 1], include_groups=False).mean()), 3)
    if arms["A1"] is not None and arms["A2"] is not None and "rating" in arms["A2"] and "rating" in arms["A1"]:
        m = arms["A1"][["season", "week", "team", "rating"]].merge(arms["A2"][["season", "week", "team", "rating"]], on=["season", "week", "team"], suffixes=("1", "2"))
        R["mean_abs_rating_change_A2_vs_A1"] = round(float((m.rating1 - m.rating2).abs().mean()), 3)
    if full or os.environ.get("NJ_SINGLE_GAMES") == "1":
        R["single_games"] = single_games({a: arms[a] for a in ("A0", "A1", "A2") if arms[a] is not None}, seasons)
    json.dump(R, open(out, "w"), indent=1)
    print(json.dumps({k: R[k] for k in R if k not in ("calibration_slope",)}, indent=1))


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "model", "replay", "nba_joint")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "model", "replay", "nba_joint_score.json")
    seasons = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else TEST
    main(d, out, seasons)
