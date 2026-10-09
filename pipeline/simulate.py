"""Monte Carlo of the rest of the season and playoffs (same engine that was backtested).

Each run draws every team's strength once (N(rating, tau)), plays every unplayed game with
margin ~ N(diff + hfa, sigma), applies simplified tiebreakers, seeds 7 per conference and plays the bracket.
"""
import numpy as np
from scipy.stats import norm

from common import DIVS, NT, TEAMS, TIX

DIV_OF = np.zeros(NT, int)
CONF_OF = np.zeros(NT, int)
DIV_TEAMS = []
for di, (name, ts) in enumerate(DIVS.items()):
    DIV_TEAMS.append([TIX[t] for t in ts])
    for t in ts:
        DIV_OF[TIX[t]] = di
        CONF_OF[TIX[t]] = 0 if name.startswith("AFC") else 1
CONF_DIVS = {0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}


def simulate(g, R, N, tau, sigma, hfa, seed=7):
    """g: this season's regular-season games (with result where played). Returns dict of probabilities + wins."""
    rng = np.random.default_rng(seed)
    g = g.sort_values(["week", "gameday"]).reset_index(drop=True)
    hi, ai = g.home_team.map(TIX).values, g.away_team.map(TIX).values
    nG = len(g)
    played = g.result.notna().values
    Rs = R[None, :] + rng.normal(0, tau, (N, NT))
    margin = Rs[:, hi] - Rs[:, ai] + hfa + rng.normal(0, sigma, (N, nG))
    margin[:, played] = g.result.values[played][None, :]
    hw = margin > 0
    Ho = np.zeros((nG, NT), np.float32); Ho[np.arange(nG), hi] = 1
    Ao = np.zeros((nG, NT), np.float32); Ao[np.arange(nG), ai] = 1
    hwf = hw.astype(np.float32); awf = 1 - hwf
    W = hwf @ Ho + awf @ Ao
    dmask = (DIV_OF[hi] == DIV_OF[ai]).astype(np.float32)
    cmask = (CONF_OF[hi] == CONF_OF[ai]).astype(np.float32)
    DW = (hwf * dmask) @ Ho + (awf * dmask) @ Ao
    CW = (hwf * cmask) @ Ho + (awf * cmask) @ Ao
    PD = margin.astype(np.float32) @ Ho - margin.astype(np.float32) @ Ao
    pair = {}
    for k in range(nG):
        a, b = hi[k], ai[k]
        pair.setdefault((min(a, b), max(a, b)), []).append(k)
    pair = {k: (np.array(v), np.array([hi[x] == k[0] for x in v])) for k, v in pair.items()}
    rnd = rng.random((N, NT))
    rnd2 = rng.random((N, 40))

    def h2h(a, b, s):
        key = (min(a, b), max(a, b))
        if key not in pair:
            return 0
        idx, a0_home = pair[key]
        w0 = int((hw[s, idx] == a0_home).sum())
        d = w0 - (len(idx) - w0)
        return d if a == key[0] else -d

    def order(ts, s, scope):
        ts = sorted(ts, key=lambda t: -W[s, t])
        out, i = [], 0
        while i < len(ts):
            j = i
            while j < len(ts) and W[s, ts[j]] == W[s, ts[i]]:
                j += 1
            grp = ts[i:j]
            if len(grp) == 2 and h2h(grp[0], grp[1], s) != 0:
                grp = grp if h2h(grp[0], grp[1], s) > 0 else grp[::-1]
            elif len(grp) > 1:
                key = (lambda t: (-DW[s, t], -CW[s, t], -PD[s, t], rnd[s, t])) if scope == "div" else \
                      (lambda t: (-CW[s, t], -PD[s, t], rnd[s, t]))
                grp = sorted(grp, key=key)
            out += grp
            i = j
        return out

    cnt = {k: np.zeros(NT) for k in ("div", "playoff", "seed1", "conf", "sb")}
    gi = [0]

    def game(a, b, s, adv):
        gi[0] += 1
        p = norm.cdf((Rs[s, a] - Rs[s, b] + adv) / sigma)
        return a if rnd2[s, gi[0]] < p else b

    for s in range(N):
        gi[0] = 0
        champs = []
        for c in (0, 1):
            winners = [order(DIV_TEAMS[d], s, "div")[0] for d in CONF_DIVS[c]]
            seeds = order(winners, s, "wc")
            rest = [t for d in CONF_DIVS[c] for t in DIV_TEAMS[d] if t not in winners]
            seeds = seeds + order(rest, s, "wc")[:3]
            for t in winners:
                cnt["div"][t] += 1
            for t in seeds:
                cnt["playoff"][t] += 1
            cnt["seed1"][seeds[0]] += 1
            alive = [seeds[0]] + [game(seeds[h], seeds[a], s, hfa) for h, a in ((1, 6), (2, 5), (3, 4))]
            rank = {t: seeds.index(t) for t in alive}
            alive = sorted(alive, key=lambda t: rank[t])
            r2 = []
            while alive:
                a, b = alive.pop(0), alive.pop(-1)
                r2.append(game(a, b, s, hfa))
            r2 = sorted(r2, key=lambda t: rank[t])
            champ = game(r2[0], r2[1], s, hfa)
            cnt["conf"][champ] += 1
            champs.append(champ)
        cnt["sb"][game(champs[0], champs[1], s, 0.0)] += 1
    out = {k: v / N for k, v in cnt.items()}
    out["wins"] = W.astype(np.int16)
    out["games_per_team"] = (Ho.sum(0) + Ao.sum(0)).astype(int)
    return out


def futures_table(res, R, ratings_df):
    W = res["wins"]
    teams = {}
    for t in TEAMS:
        i = TIX[t]
        dist = np.bincount(W[:, i], minlength=18)[:18] / W.shape[0]
        teams[t] = {"rating": round(float(R[i]), 2), "mean_wins": round(float(W[:, i].mean()), 2),
                    "win_dist": [round(float(x), 4) for x in dist],
                    "p_div": round(float(res["div"][i]), 4), "p_playoff": round(float(res["playoff"][i]), 4),
                    "p_seed1": round(float(res["seed1"][i]), 4), "p_conf": round(float(res["conf"][i]), 4),
                    "p_sb": round(float(res["sb"][i]), 4),
                    "qb": ratings_df.loc[t, "qb_expected"], "qb_adj": round(float(ratings_df.loc[t, "qb_adj"]), 2),
                    "qb_note": ratings_df.loc[t, "qb_note"]}
    return teams
