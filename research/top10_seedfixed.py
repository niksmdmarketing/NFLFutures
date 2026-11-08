"""Final-week 'seed fixed' flag and penalty (rule: research/TOP10_BACKTEST_EDGES_RULE.md, Amendment 2).
Usage: python research/top10_seedfixed.py <edges_fix_round1.csv> <out dir>"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M
from common import games, TEAMS, TIX
import simulate as SIM
import ratings
S = ratings.S


def fixed_clubs(g, y, N=4000, thr=0.99):
    gy = g[(g.season == y) & (g.game_type == "REG")].copy()
    last = gy.week.max()
    gy.loc[gy.week == last, "result"] = np.nan
    res = SIM.simulate(gy, np.zeros(len(TEAMS)), N, 0.0, S["sim"]["sigma"], 0.0, n_seeds=6 if y <= 2019 else 7)
    sd = res["seed_dist"]                      # (teams, seeds [+ out?])
    ns = 6 if y <= 2019 else 7
    flag = {}
    for t in TEAMS:
        v = np.asarray(sd[TIX[t]], float)
        flag[t] = bool(v[:ns].max() >= thr)
    return flag, gy[gy.week == last]


def main():
    D = pd.read_csv(sys.argv[1]); out = sys.argv[2]
    g = games(); lam = S["qb"]["lambda"]; sigma = (S["sim"]["sigma"] ** 2 + 2 * S["sim"]["tau"] ** 2) ** 0.5
    D["fixd"] = 0
    nfl = {}
    for y in sorted(D.season.unique()):
        flag, fin = fixed_clubs(g, y)
        nfl[int(y)] = sorted(t for t, v in flag.items() if v)
        for r in fin.itertuples():
            h, a = flag.get(r.home_team, False), flag.get(r.away_team, False)
            D.loc[D.game == r.game_id, "fixd"] = 1 if (h and not a) else -1 if (a and not h) else 0
    print("games with exactly one seed-fixed club:", int((D.fixd != 0).sum()), D[D.fixd != 0].groupby("season").size().to_dict())
    D["margin0"] = D.base + lam * D.qdiff
    final = D[D.fixd != 0].copy()
    # club-side residual: actual margin from the fixed club's side minus the model margin from its side
    final["resid_club"] = (final.result - final.margin0) * -final.fixd * -1 * -1
    # fixd=+1 means home club fixed: resid = (result - margin0) from home side; fixd=-1: from away side = -(result - margin0)
    final["resid_club"] = np.where(final.fixd == 1, final.result - final.margin0, -(final.result - final.margin0))
    others = D[(D.week == D.groupby("season").week.transform("max")) & (D.fixd == 0)]
    rng = np.random.default_rng(1)
    def boot(X, sel):
        ss = sorted(X.season.unique()); m = []
        for _ in range(4000):
            pick = rng.choice(ss, len(ss)); v = np.concatenate([X[X.season == s][sel].values for s in pick])
            if len(v): m.append(v.mean())
        return np.percentile(m, [5, 95])
    disc = final[final.season <= 2019]; ev = final[final.season >= 2020]
    lo, hi = boot(disc, "resid_club")
    print(f"disc 2014-19 fixed-club residual {disc.resid_club.mean():+.2f} pts (n {len(disc)}) 90% [{lo:+.2f},{hi:+.2f}]; eval {ev.resid_club.mean():+.2f} (n {len(ev)})")
    ctrl = others.assign(r=others.result - others.margin0)
    print("control final-week other games mean resid (home side)", round(ctrl[ctrl.season <= 2019].r.mean(), 2), "disc;", round(ctrl[ctrl.season >= 2020].r.mean(), 2), "eval")
    P = -float(disc.resid_club.mean())
    D["margin_fix"] = D.margin0 - P * D.fixd
    print("P (from discovery only) =", round(P, 2))
    def ll(p, y): p = np.clip(p, 1e-4, 1 - 1e-4); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    l0 = ll(M.phi(D.margin0 / sigma), D.y.values); l1 = ll(M.phi(D.margin_fix / sigma), D.y.values)
    D["l0"], D["l1"] = l0, l1
    gain = pd.Series(l0 - l1).groupby(D.season.values).mean()
    evg = gain[gain.index >= 2020]
    bs = [rng.choice(evg.values, len(evg)).mean() for _ in range(4000)]
    print(f"eval gain per game {evg.mean():+.5f} 90% [{np.percentile(bs,5):+.5f},{np.percentile(bs,95):+.5f}] worse seasons {(evg<0).sum()}/{len(evg)}; disc gain {gain[gain.index<=2019].mean():+.5f}")
    print("flagged clubs by season", {k: len(v) for k, v in nfl.items()})
    D.to_csv(os.path.join(out, "edges_fix_round2.csv"), index=False)
    json.dump({"P": P, "flagged": nfl}, open(os.path.join(out, "seedfixed.json"), "w"))


if __name__ == "__main__":
    main()
