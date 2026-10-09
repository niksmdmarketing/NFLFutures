"""Monte Carlo of the rest of the season and playoffs (v4).

Each run draws every team's strength once, N(rating, tau), plays every unplayed game with margin
N(diff + hfa, sigma_game), applies the NFL tiebreaking procedures and plays the 7-seed bracket.
Tau and sigma_game were tuned jointly on 2022-2025 final win totals (total per-game error held at the observed
level), replacing the earlier setup that added team uncertainty on top of an error already containing it.

Tiebreakers (NFL procedure, simplified only at the very end):
  division, 2 clubs: head-to-head, division record, common games, conference record, strength of victory,
                     strength of schedule, net points, coin
  division, 3+ clubs: same steps (head-to-head = record in games among the tied clubs); when a step removes some
                     clubs the procedure restarts from step 1 for the remaining clubs
  wild card / seeding: first keep only the best club from each division (division tiebreakers); then
                     head-to-head (2 clubs if they played; 3+ clubs only a sweep), conference record,
                     common games (minimum 4), strength of victory, strength of schedule, net points, coin
Played ties count as half a win. Net points stands in for the NFL's later points-ranking steps.
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
    """g: this season's regular-season games (with result where played). Returns probabilities + wins."""
    rng = np.random.default_rng(seed)
    g = g.sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
    hi, ai = g.home_team.map(TIX).values, g.away_team.map(TIX).values
    nG = len(g)
    played = g.result.notna().values
    Rs = R[None, :] + rng.normal(0, tau, (N, NT))
    margin = (Rs[:, hi] - Rs[:, ai] + hfa + rng.normal(0, sigma, (N, nG))).astype(np.float32)
    margin[:, played] = g.result.values[played][None, :]
    hwv = (margin > 0).astype(np.float32) + 0.5 * (margin == 0)  # home win value (ties = half)
    awv = 1.0 - hwv
    Ho = np.zeros((nG, NT), np.float32); Ho[np.arange(nG), hi] = 1
    Ao = np.zeros((nG, NT), np.float32); Ao[np.arange(nG), ai] = 1
    W = hwv @ Ho + awv @ Ao
    dmask = (DIV_OF[hi] == DIV_OF[ai]).astype(np.float32)
    cmask = (CONF_OF[hi] == CONF_OF[ai]).astype(np.float32)
    DW = (hwv * dmask) @ Ho + (awv * dmask) @ Ao
    CW = (hwv * cmask) @ Ho + (awv * cmask) @ Ao
    n_games = Ho.sum(0) + Ao.sum(0)
    n_div = dmask @ Ho + dmask @ Ao
    n_conf = cmask @ Ho + cmask @ Ao
    PD = margin @ Ho - margin @ Ao
    Wa, Wh = W[:, ai], W[:, hi]
    SOV = ((hwv * Wa) @ Ho + (awv * Wh) @ Ao) / np.maximum(W, 0.5)
    SOS = Wa @ Ho + Wh @ Ao
    del Wa, Wh
    # per-team game lists for head-to-head and common games
    games_of = {t: [] for t in range(NT)}
    for k in range(nG):
        games_of[hi[k]].append((k, ai[k], True))
        games_of[ai[k]].append((k, hi[k], False))
    opps_of = {t: {o for _, o, _ in v} for t, v in games_of.items()}
    rnd = rng.random((N, NT))
    rnd2 = rng.random((N, 16))

    def record_vs(t, opps, s):
        w = n = 0.0
        for k, o, home in games_of[t]:
            if o in opps:
                w += hwv[s, k] if home else awv[s, k]
                n += 1
        return w, n

    def keep_best(group, vals):
        best = max(vals)
        return [t for t, v in zip(group, vals) if v >= best - 1e-9]

    def div_break(group, s):
        """Division tiebreak among clubs of one division; returns the top club."""
        while len(group) > 1:
            gs = set(group)
            steps = []
            h = [record_vs(t, gs - {t}, s) for t in group]
            steps.append([w / n if n else 0.5 for w, n in h])
            steps.append([DW[s, t] / max(n_div[t], 1) for t in group])
            common = set.intersection(*(opps_of[t] for t in group)) - gs
            if common:
                c = [record_vs(t, common, s) for t in group]
                steps.append([w / n if n else 0.5 for w, n in c])
            steps.append([CW[s, t] / max(n_conf[t], 1) for t in group])
            steps.append([SOV[s, t] for t in group])
            steps.append([SOS[s, t] for t in group])
            steps.append([PD[s, t] for t in group])
            steps.append([rnd[s, t] for t in group])
            for vals in steps:
                kept = keep_best(group, vals)
                if len(kept) < len(group):
                    group = kept
                    break
        return group[0]

    def wc_break(group, s):
        """Tiebreak among clubs from different divisions (wild card / seeding); returns the top club."""
        while len(group) > 1:
            gs = set(group)
            reduced = False
            if len(group) == 2:
                a, b = group
                w, n = record_vs(a, {b}, s)
                if n and abs(w - (n - w)) > 1e-9:
                    return a if w > n - w else b
            else:
                allplayed = all(len(opps_of[t] & (gs - {t})) == len(group) - 1 for t in group)
                if allplayed:
                    rec = {t: record_vs(t, gs - {t}, s) for t in group}
                    sweep = [t for t in group if rec[t][0] == rec[t][1]]
                    if len(sweep) == 1:
                        return sweep[0]
                    swept = [t for t in group if rec[t][0] == 0]
                    if 0 < len(swept) < len(group):
                        group = [t for t in group if t not in swept]
                        continue
            steps = [[CW[s, t] / max(n_conf[t], 1) for t in group]]
            common = set.intersection(*(opps_of[t] for t in group)) - gs
            if common:
                c = [record_vs(t, common, s) for t in group]
                if min(n for _, n in c) >= 4:
                    steps.append([w / n for w, n in c])
            steps += [[SOV[s, t] for t in group], [SOS[s, t] for t in group], [PD[s, t] for t in group], [rnd[s, t] for t in group]]
            for vals in steps:
                kept = keep_best(group, vals)
                if len(kept) < len(group):
                    group = kept
                    reduced = True
                    break
            if not reduced:
                return group[0]
        return group[0]

    def pick(cands, s):
        """Top club among candidates (any divisions), by record then tiebreakers."""
        best = max(W[s, t] for t in cands)
        tied = [t for t in cands if W[s, t] >= best - 1e-9]
        if len(tied) == 1:
            return tied[0]
        by_div = {}
        for t in tied:
            by_div.setdefault(DIV_OF[t], []).append(t)
        tops = [div_break(v, s) if len(v) > 1 else v[0] for v in by_div.values()]
        return tops[0] if len(tops) == 1 else wc_break(tops, s)

    def order(cands, s, k):
        out, rest = [], list(cands)
        while rest and len(out) < k:
            t = pick(rest, s)
            out.append(t)
            rest.remove(t)
        return out

    cnt = {k: np.zeros(NT) for k in ("div", "playoff", "seed1", "conf", "sb")}
    seeds_count = np.zeros((NT, 7))

    for s in range(N):
        gi = 0
        champs = []
        for c in (0, 1):
            winners = []
            for d in CONF_DIVS[c]:
                ts = DIV_TEAMS[d]
                best = max(W[s, t] for t in ts)
                tied = [t for t in ts if W[s, t] >= best - 1e-9]
                winners.append(tied[0] if len(tied) == 1 else div_break(tied, s))
            top4 = order(winners, s, 4)
            rest = [t for d in CONF_DIVS[c] for t in DIV_TEAMS[d] if t not in winners]
            seeds = top4 + order(rest, s, 3)
            for i, t in enumerate(seeds):
                seeds_count[t, i] += 1
            for t in winners:
                cnt["div"][t] += 1
            for t in seeds:
                cnt["playoff"][t] += 1
            cnt["seed1"][seeds[0]] += 1
            rank = {t: i for i, t in enumerate(seeds)}
            alive = [seeds[0]]
            for h, a in ((1, 6), (2, 5), (3, 4)):
                x, y = seeds[h], seeds[a]
                p = norm.cdf((Rs[s, x] - Rs[s, y] + hfa) / sigma)
                alive.append(x if rnd2[s, gi] < p else y); gi += 1
            alive.sort(key=lambda t: rank[t])
            r2 = []
            while alive:
                x, y = alive.pop(0), alive.pop(-1)
                p = norm.cdf((Rs[s, x] - Rs[s, y] + hfa) / sigma)
                r2.append(x if rnd2[s, gi] < p else y); gi += 1
            r2.sort(key=lambda t: rank[t])
            x, y = r2
            p = norm.cdf((Rs[s, x] - Rs[s, y] + hfa) / sigma)
            champ = x if rnd2[s, gi] < p else y; gi += 1
            cnt["conf"][champ] += 1
            champs.append(champ)
        x, y = champs
        p = norm.cdf((Rs[s, x] - Rs[s, y]) / sigma)
        cnt["sb"][x if rnd2[s, gi] < p else y] += 1
    out = {k: v / N for k, v in cnt.items()}
    out["seed_dist"] = seeds_count / N
    out["wins"] = W
    out["games_per_team"] = n_games.astype(int)
    return out


def futures_table(res, R, ratings_df):
    W = res["wins"]
    teams = {}
    half = np.round(W * 2).astype(int)  # half-win grid (ties)
    for t in TEAMS:
        i = TIX[t]
        whole = np.floor(W[:, i] + 1e-9).astype(int)
        dist = np.bincount(np.clip(whole, 0, 17), minlength=18)[:18] / W.shape[0]
        teams[t] = {"rating": round(float(R[i]), 2), "mean_wins": round(float(W[:, i].mean()), 2),
                    "win_dist": [round(float(x), 4) for x in dist],
                    "has_tie": bool((half[:, i] % 2).any()),
                    "p_div": round(float(res["div"][i]), 4), "p_playoff": round(float(res["playoff"][i]), 4),
                    "p_seed1": round(float(res["seed1"][i]), 4), "p_conf": round(float(res["conf"][i]), 4),
                    "p_sb": round(float(res["sb"][i]), 4),
                    "seed_dist": [round(float(x), 4) for x in res["seed_dist"][i]],
                    "qb": ratings_df.loc[t, "qb_expected"], "qb_adj": round(float(ratings_df.loc[t, "qb_adj"]), 2),
                    "qb_note": ratings_df.loc[t, "qb_note"],
                    "press_adj": round(float(ratings_df.loc[t, "press_adj"]), 2) if "press_adj" in ratings_df else 0.0}
    return teams
