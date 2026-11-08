"""Round-N fix test for the top-10 edges rule: final-week locked-club rest (live REST_PEN) and the v5 QB-prior term at game level.
Usage: python research/top10_fix_round.py <edges_all.csv> <out dir>. Uses only outcomes (log loss of the model); prices only choose cohorts."""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M
from common import games, FIX, DIVS
import ratings
S = ratings.S


def locked_by_game(g):
    """{game_id: (home_locked, away_locked)} for each season's final regular-season week, from results of earlier weeks (rule definition)."""
    out = {}
    for y, gy in g[g.game_type == "REG"].groupby("season"):
        last = gy.week.max()
        pre = gy[(gy.week < last) & gy.result.notna()]
        W = {}
        for r in pre.itertuples():
            h, a = FIX.get(r.home_team, r.home_team), FIX.get(r.away_team, r.away_team)
            hw = 1.0 if r.result > 0 else 0.5 if r.result == 0 else 0.0
            W[h] = W.get(h, 0) + hw; W[a] = W.get(a, 0) + 1 - hw
        divs = {d: [t for t in ts] for d, ts in DIVS.items()}
        lead = {d: max(W.get(t, 0) for t in ts) for d, ts in divs.items()}
        cont = {t: W.get(t, 0) >= lead[d] - 1.0 for d, ts in divs.items() for t in ts}
        lock = {}
        for d, ts in divs.items():
            conf = d.split()[0]
            other = [u for dd, tt in divs.items() if dd.split()[0] == conf and dd != d for u in tt]
            for t in ts:
                ok = all(W.get(t, 0) - W.get(u, 0) > 1.0 for u in ts if u != t)
                ok = ok and all((not cont[u]) or abs(W.get(t, 0) - W.get(u, 0)) > 1.0 for u in other)
                lock[t] = ok
        for r in gy[gy.week == last].itertuples():
            h, a = FIX.get(r.home_team, r.home_team), FIX.get(r.away_team, r.away_team)
            out[r.game_id] = (lock.get(h, False), lock.get(a, False))
    return out


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main():
    D = pd.read_csv(sys.argv[1]); out = sys.argv[2]
    g = games(); lk = locked_by_game(g)
    D["lockd"] = [(1 if lk.get(x, (False, False))[0] and not lk.get(x, (False, False))[1] else -1 if lk.get(x, (False, False))[1] and not lk.get(x, (False, False))[0] else 0) for x in D.game]
    print("final-week games with exactly one locked club:", int((D.lockd != 0).sum()), "by season", D[D.lockd != 0].groupby("season").size().to_dict())
    lam = S["qb"]["lambda"]; sigma = (S["sim"]["sigma"] ** 2 + 2 * S["sim"]["tau"] ** 2) ** 0.5
    P0 = 17.891
    D["margin0"] = D.base + lam * D.qdiff
    arms = {"v4 (harness)": D.margin0,
            "+ rest 17.891": D.margin0 - P0 * D.lockd,
            "+ rest 16.4": D.margin0 - 16.4 * D.lockd,
            "+ v5 qb prior L=1": D.margin0 + 1.0 * D.qpdiff,
            "+ rest + qb prior": D.margin0 - P0 * D.lockd + 1.0 * D.qpdiff}
    rows = []
    for name, m in arms.items():
        p = M.phi(m / sigma)
        l = ll(p, D.y.values)
        r = {"arm": name, "all": l.mean()}
        for lab, mask in (("disc 14-19", D.season <= 2019), ("eval 20-25", D.season >= 2020), ("locked games", D.lockd != 0), ("weeks 2-3", D.week <= 3), ("weeks 2-3 eval", (D.week <= 3) & (D.season >= 2020))):
            r[lab] = l[mask.values].mean()
        # evaluation-season paired gain vs baseline with season-cluster interval
        rows.append(r)
        D["l_" + name] = l
    R = pd.DataFrame(rows).set_index("arm")
    print(R.round(5).to_string())
    base = D["l_v4 (harness)"]
    for name in list(arms)[1:]:
        gain = (base - D["l_" + name]).groupby(D.season).mean()
        ev = gain[gain.index >= 2020]
        rng = np.random.default_rng(0)
        bs = [rng.choice(ev.values, len(ev)).mean() for _ in range(4000)]
        print(f"{name:22s} eval gain per game {ev.mean():+.5f} 90% [{np.percentile(bs,5):+.5f},{np.percentile(bs,95):+.5f}]  seasons better {int((ev>0).sum())}/{len(ev)}   disc gain {gain[gain.index<=2019].mean():+.5f}")
    D.to_csv(os.path.join(out, "edges_fix_round1.csv"), index=False)
    json.dump({"P0": P0, "lam": lam, "sigma": sigma}, open(os.path.join(out, "fix_round1_params.json"), "w"))


if __name__ == "__main__":
    main()
