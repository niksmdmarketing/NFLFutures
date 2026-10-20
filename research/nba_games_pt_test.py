"""NBA single games: player term (PT) against the complete live pipeline (L). Rule: research/NBA_GAMES_PT_RULE.md.

build <first> <last>: weekly point-in-time replay of the live ratings (replay_nba.py, BT_FULL=1, BT_PF=2); at every checkpoint the
    live rating (L, before the player term) and the PT rating are captured with that checkpoint's home edge and pace. No simulation.
    Writes data/research/nba_games_pt_ck_<y>.json.
score: predicts every regular-season game from the latest checkpoint before its date and applies the gates.
"""
import json
import os
import sys
from collections import defaultdict

os.environ.setdefault("BT_FULL", "1")
os.environ["BT_PF"] = "2"
os.environ.setdefault("BT_SIMS", "1")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
CK = os.path.join(ROOT, "data", "research")
AVAIL = os.environ.get("AVAIL_CSV", "/tmp/claude-0/-home-claude-nflfutures/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/nba_avail2_games.csv")
BETA = 0.45   # live points per availability unit (pipeline/nba_avail.py BETA)


def build(first, last):
    import replay_nba as R
    N, B = R.N, R.B
    boxes = B.load_boxes(last)
    orig_pf2 = R._pf2_rating   # taken once: the wrappers below must never wrap each other
    cap = {}
    for y in range(first, last + 1):
        cap.clear()
        cap.update({"L": {}, "ck": []})

        def pf2(yy, cutoff, ratings):
            cap["L"][str(cutoff.date())] = dict(zip(ratings.team, ratings.rating.astype(float)))
            return orig_pf2(yy, cutoff, ratings)

        def sim(s, ratings, n, **kw):
            done = s[s.completed]
            cap["ck"].append({"n_done": int(len(done)), "rating": dict(zip(ratings.team, ratings.rating.astype(float))),
                              "hfa": float(N.HFA), "pace": dict(zip(N.TEAMS, map(float, N.PACE)))})
            return {t: defaultdict(float) for t in N.TEAMS}

        R._pf2_rating, N._simulate = pf2, sim
        R.ERA = False   # ratings are needed for 2020 games too; the format switch only affects simulations
        g = B.season_games(boxes, y)
        first_d, last_d = g.date.min(), g.date.max()
        cuts = [first_d - pd.Timedelta(days=1)]
        d = first_d + pd.Timedelta(days=6)
        while d < last_d - pd.Timedelta(days=6):
            cuts.append(d)
            d += pd.Timedelta(days=7)
        R.run_season(boxes, y)
        assert len(cap["ck"]) == len(cuts), (y, len(cap["ck"]), len(cuts))
        out = []
        for c, k in zip(cuts, cap["ck"]):
            key = str(c.date())
            L = cap["L"].get(key, k["rating"])   # week 0 (no games yet): no player term, L = PT
            out.append({"cutoff": key, "n_done": k["n_done"], "hfa": k["hfa"], "pace": k["pace"], "L": L, "PT": k["rating"],
                        "pt_applied": key in cap["L"]})
        json.dump({"season": y, "sigma": float(N.GAME_SIGMA), "checkpoints": out}, open(os.path.join(CK, f"nba_games_pt_ck_{y}.json"), "w"))
        print("season", y, "checkpoints", len(out), "with player term", sum(o["pt_applied"] for o in out), flush=True)


def _phi(x):
    from scipy.stats import norm
    return norm.cdf(x)


def predictions():
    G = pd.read_csv(os.path.join(ROOT, "data", "research", "nba_player_first_rows.csv"))
    A = pd.read_csv(AVAIL)
    A["covered"] = A.covered.astype(str) == "True"
    A = A[["date", "home", "away", "covered", "v2_base_h", "v2_base_a", "v2_official_h", "v2_official_a"]].drop_duplicates(["date", "home", "away"])
    G = G.merge(A, on=["date", "home", "away"], how="left")
    rows = []
    for y in sorted(G.season.unique()):
        p = os.path.join(CK, f"nba_games_pt_ck_{y}.json")
        if not os.path.exists(p):
            continue
        C = json.load(open(p))
        cks = C["checkpoints"]
        cut = pd.to_datetime([c["cutoff"] for c in cks])
        for g in G[G.season == y].itertuples():
            i = int(np.searchsorted(cut, pd.Timestamp(g.date), side="left")) - 1   # latest checkpoint strictly before the game date
            if i < 0:
                continue
            c = cks[i]
            if not c["pt_applied"]:
                continue   # week 0: identical by construction, not scored
            pace = (c["pace"].get(g.home, 100.0) + c["pace"].get(g.away, 100.0)) / 200
            r = {"season": y, "cutoff": c["cutoff"], "date": g.date, "home": g.home, "away": g.away, "margin": g.margin,
                 "early": bool(max(g.gp_h, g.gp_a) <= 20) if pd.notna(g.gp_h) else None, "covered": bool(g.covered) if pd.notna(g.covered) else False,
                 "sigma": C["sigma"]}
            for v in ("L", "PT"):
                r["m_" + v] = (c[v].get(g.home, 0.0) - c[v].get(g.away, 0.0) + c["hfa"]) * pace
            r["av_off"] = BETA * (g.v2_official_h - g.v2_official_a) if pd.notna(g.v2_official_h) else np.nan
            r["av_base"] = BETA * (g.v2_base_h - g.v2_base_a) if pd.notna(g.v2_base_h) else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _slope(p, y):
    import statsmodels.api as sm
    x = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    return float(sm.Logit(y, sm.add_constant(x)).fit(disp=0).params[1])


def evaluate(D, av):
    D = D[D[av].notna()].copy()
    y = (D.margin > 0).astype(float).to_numpy()
    out = {"games": int(len(D)), "seasons": sorted(int(s) for s in D.season.unique())}
    P, M = {}, {}
    for v in ("L", "PT"):
        m = D["m_" + v].to_numpy() - D[av].to_numpy()
        M[v], P[v] = m, _phi(m / D.sigma.to_numpy())
        out[v] = {"log_loss": round(float(_ll(P[v], y).mean()), 5), "mse": round(float(np.mean((D.margin - m) ** 2)), 3),
                  "calibration_slope": round(_slope(P[v], y), 3)}
    d = _ll(P["L"], y) - _ll(P["PT"], y)   # positive = PT better
    wk = (D.season.astype(str) + "_" + D.cutoff).to_numpy()
    keys = np.unique(wk)
    per = {k: d[wk == k] for k in keys}
    rng = np.random.default_rng(21)
    bs = [np.concatenate([per[k] for k in rng.choice(keys, len(keys))]).mean() for _ in range(2000)]
    out["gain"] = round(float(d.mean()), 6)
    out["gain_lower90_one_sided"] = round(float(np.percentile(bs, 10)), 6)
    S = D.season.to_numpy()
    out["by_season"] = {int(s): round(float(d[S == s].mean()), 6) for s in sorted(set(S))}
    out["seasons_better"] = int(sum(v > 0 for v in out["by_season"].values()))
    e = D.early.fillna(False).to_numpy().astype(bool)
    out["early"] = {"games": int(e.sum()), "gain": round(float(d[e].mean()), 6) if e.any() else None}
    out["later"] = {"games": int((~e).sum()), "gain": round(float(d[~e].mean()), 6)}
    out["mse_gain"] = round(float(np.mean((D.margin - M["L"]) ** 2) - np.mean((D.margin - M["PT"]) ** 2)), 3)
    return out


def score():
    D = predictions()
    prim = D[(D.season >= 2022) & D.covered]
    rob = D[(D.season >= 2015)]
    res = {"primary_2022_2026_official": evaluate(prim, "av_off"), "robustness_2015_2026_v2_base": evaluate(rob, "av_base")}
    p, r = res["primary_2022_2026_official"], res["robustness_2015_2026_v2_base"]
    res["gates"] = {
        "1_primary_logloss_lower_bound_above_0": p["gain"] > 0 and p["gain_lower90_one_sided"] > 0,
        "2_better_in_4_of_5_seasons": p["seasons_better"] >= 4 and len(p["by_season"]) == 5,
        "3_margin_mse_not_higher": p["mse_gain"] >= 0,
        "4_early_and_later_not_worse": (p["early"]["gain"] is None or p["early"]["gain"] >= 0) and p["later"]["gain"] >= 0,
        "5_calibration_slope_0.8_1.2": 0.8 <= p["PT"]["calibration_slope"] <= 1.2,
        "6_robustness_logloss_not_higher": r["gain"] >= 0}
    res["pass"] = all(res["gates"].values())
    json.dump(res, open(os.path.join(ROOT, "research", "nba_games_pt_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(int(sys.argv[2]), int(sys.argv[3]))
    else:
        score()
