"""Does "who is missing tonight" predict NHL results beyond team strength? (research, game level, walk-forward)

For every regular-season game 2015-2025 and each team (skipping its first 5 games of the season):
  skater term  = sum over tonight's skaters of usual hours x value  -  the team's average of the same over its earlier games
  goalie term  = tonight's starting goalie's value  -  the team's start-weighted average goalie value so far
Values come from earlier seasons only (pipeline/nhl_roster.player_values: skaters on-ice xG impact per 60, goalies GSAx per
60, shrunk for small samples). "Usual hours" = the player's average ice time in his earlier games for the team this season
(else 15 min F / 20 min D), scaled so a lineup totals 5 skater-hours.
Base = season-to-date goal difference per game shrunk toward half of last season's (k games), home minus away, plus home edge.
Stage 2, walk-forward: residual margin ~ b_s x skater diff + b_g x goalie diff, fitted on earlier seasons, scored on the next.
Usage: python research/nhl_absence_test.py   (env NA_MODE rel|abs|mix, NA_YEARS 1|2, NA_GSH goalie shrink hours)
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nhl_model as M  # noqa: E402
import nhl_roster as R  # noqa: E402

LIN = os.path.join(ROOT, "data", "research", "nhl_lineups")
MODE = os.environ.get("NA_MODE", "rel")
YEARS = int(os.environ.get("NA_YEARS", "2"))
GSH = float(os.environ.get("NA_GSH", "10"))
K = 30.0
SK = os.environ.get("NA_SK", "xg")      # xg (player_values) | pts (points per 60 vs position average) | none
FEATS = ["dgk"] if SK == "none" else ["dsk", "dgk"]
FIRST, LAST = int(os.environ.get("NA_FIRST", 2015)), int(os.environ.get("NA_LAST", 2025))


def values(y):
    """key -> value per 60 as of the start of season y (seasons y-1 and y-2 weighted 2:1 by hours)."""
    R.SHRINK_H = 10.0
    parts = []
    for k, w in ((1, 2.0), (2, 1.0 if YEARS > 1 else 0.0)):
        if w == 0:
            continue
        v = R.player_values(y - k, MODE)
        if v is None:
            continue
        v = v.copy()
        if GSH != 10:  # re-shrink goalies: undo the 10 h shrink, apply GSH
            g = v.g == 1
            raw = v.value[g] * (v.hours[g] + 10) / v.hours[g].clip(lower=1e-6)
            v.loc[g, "value"] = raw * v.hours[g] / (v.hours[g] + GSH)
        v["w"] = w * v.hours
        parts.append(v.reset_index())
    a = pd.concat(parts)
    if SK == "pts":
        sk = []
        for k, w in ((1, 2.0), (2, 1.0 if YEARS > 1 else 0.0)):
            d = R._load("skaters", y - k)
            if w == 0 or d is None:
                continue
            h = R._num(d, "toiTotal") / 3600
            p60 = R._num(d, "points") / h.clip(lower=0.1)
            grp = d.pos.map(lambda x: "D" if x == "D" else "F")
            dev = p60 - p60.where(h > 5).groupby(grp).transform("mean")
            sk.append(pd.DataFrame({"key": R._key(d, False), "value": (dev * h / (h + 20)).fillna(0), "hours": h.fillna(0), "w": w * h.fillna(0)}))
        a = pd.concat([a[a.key.str.endswith("|G")]] + sk)
    a["vw"] = a.value * a.w
    s = a.groupby("key").agg(vw=("vw", "sum"), w=("w", "sum"))
    return (s.vw / s.w.where(s.w > 0, 1)).fillna(0)


def key(name, pos):
    return name.str.strip().str.lower() + "|" + np.where(pos == "G", "G", np.where(pos == "D", "D", "F"))


def season_features(y):
    S = pd.read_csv(os.path.join(LIN, f"skaters_{y}.csv.gz"))
    G = pd.read_csv(os.path.join(LIN, f"goalies_{y}.csv.gz"))
    val = values(y)
    S["k"] = key(S.name, S.pos)
    G["k"] = key(G.name, pd.Series("G", index=G.index))
    S["v"] = S.k.map(val).fillna(0.0)
    G["v"] = G.k.map(val).fillna(0.0)
    order = S[["game_id", "date"]].drop_duplicates().sort_values(["date", "game_id"]).game_id.tolist()
    rank = {g: i for i, g in enumerate(order)}
    S["o"] = S.game_id.map(rank); G["o"] = G.game_id.map(rank)
    rows = []
    for team, st in S.groupby("team"):
        gt = G[G.team == team]
        games = sorted(st.o.unique())
        tot_toi, n_app, team_hv = {}, {}, []
        g_starts = {}
        for i, o in enumerate(games):
            lineup = st[st.o == o]
            # usual hours of tonight's skaters
            h = np.array([tot_toi[p] / n_app[p] / 3600 if p in n_app else (20 if d == "D" else 15) / 60
                          for p, d in zip(lineup.player_id, lineup.pos)])
            h = h * 5.0 / max(h.sum(), 1e-9)
            hv_tonight = float((h * lineup.v.to_numpy()).sum())
            gs = gt[(gt.o == o) & (gt.started == 1)]
            gv_tonight = float(gs.v.iloc[0]) if len(gs) else np.nan
            if i >= 5:
                usual_s = float(np.mean(team_hv))
                tot = sum(c for c, _ in g_starts.values())
                usual_g = sum(c * v for c, v in g_starts.values()) / tot if tot else np.nan
                rows.append({"o": o, "game_id": lineup.game_id.iloc[0], "team": team, "date": lineup.date.iloc[0],
                             "sk": hv_tonight - usual_s, "gk": gv_tonight - usual_g, "starter": gs.name.iloc[0] if len(gs) else None})
            team_hv.append(hv_tonight)
            for p, t in zip(lineup.player_id, lineup.toi):
                if pd.notna(t):
                    tot_toi[p] = tot_toi.get(p, 0) + float(t); n_app[p] = n_app.get(p, 0) + 1
            for _, r in gs.iterrows():
                c, _v = g_starts.get(r.player_id, (0, r.v))
                g_starts[r.player_id] = (c + 1, r.v)
    return pd.DataFrame(rows)


def base_margins(y):
    g = M.read_games(y).copy()
    g["gd"] = M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")
    g = g.sort_values(["date", "team"])
    prev = M.read_games(y - 1)
    pr = ((M.numcol(prev, "goalsFor") - M.numcol(prev, "goalsAgainst")).groupby(prev.team).mean() * 0.5)
    g["cum_gd"] = g.groupby("team").gd.cumsum() - g.gd
    g["n"] = g.groupby("team").cumcount()
    g["rating"] = (g.cum_gd + K * g.team.map(pr).fillna(0)) / (g.n + K)
    return g


def main():
    allrows = []
    for y in range(FIRST, LAST + 1):
        if not os.path.exists(os.path.join(LIN, f"skaters_{y}.csv.gz")):
            continue
        F = season_features(y)
        g = base_margins(y)
        g["date"] = g.date.astype(str).str[:10]
        F["date"] = F.date.astype(str).str[:10]
        g = g.merge(F[["date", "team", "sk", "gk"]], on=["date", "team"], how="left")
        h = g[g.ha == "H"]
        a = g[g.ha == "R"][["date", "team", "rating", "sk", "gk"]].rename(columns={"team": "opp"})
        m = h.merge(a, on=["date", "opp"], suffixes=("", "_a"))
        m["season"] = y
        allrows.append(m[["season", "date", "team", "opp", "gd", "res", "rating", "rating_a", "sk", "sk_a", "gk", "gk_a"]])
        print(y, len(m), "games; feature coverage", round(m.sk.notna().mean(), 3), round(m.gk.notna().mean(), 3), flush=True)
    D = pd.concat(allrows, ignore_index=True)
    D = D.dropna(subset=["sk", "sk_a", "gk", "gk_a"])
    D["base"] = D.rating - D.rating_a
    D["dsk"] = D.sk - D.sk_a
    D["dgk"] = D.gk - D.gk_a
    D["win"] = (D.res == "W").astype(float)
    hfa = 0.0
    out = []
    for t in range(FIRST + 2, LAST + 1):
        tr, te = D[D.season < t], D[D.season == t]
        hfa = float((tr.gd - tr.base).mean())
        X = tr[FEATS].to_numpy(); r = (tr.gd - tr.base - hfa).to_numpy()
        b = np.linalg.lstsq(X, r, rcond=None)[0]
        res = r - X @ b
        se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * res.var())
        p0 = te.base + hfa
        p1 = p0 + te[FEATS].to_numpy() @ b
        # win probability from the margin: scale fitted on training games
        sc = float(np.std(tr.gd - tr.base - hfa))
        def ll(p, s):
            q = norm.cdf(p / s * 1.25).clip(1e-4, 1 - 1e-4)  # 1.25: a goal margin of m -> win chance including OT/SO
            return float(-np.mean(te.win * np.log(q) + (1 - te.win) * np.log(1 - q)))
        bb = dict(zip(FEATS, b)); ss = dict(zip(FEATS, se))
        out.append(dict(season=t, b_sk=bb.get("dsk", 0), se_sk=ss.get("dsk", 0), b_gk=bb["dgk"], se_gk=ss["dgk"], n=len(te), ll0=ll(p0, sc), ll1=ll(p1, sc),
                        sd_dsk=float(te.dsk.std()), sd_dgk=float(te.dgk.std())))
    O = pd.DataFrame(out)
    print(O.round(4).to_string(index=False))
    d = O.ll0 - O.ll1
    print(f"sk={SK} mode={MODE} years={YEARS} gsh={GSH}: log loss gain {d.mean():.5f}, better {(d > 0).sum()}/{len(O)}")
    X = D[FEATS].to_numpy(); r = (D.gd - D.base - (D.gd - D.base).mean()).to_numpy()
    b = np.linalg.lstsq(X, r, rcond=None)[0]; res = r - X @ b
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * res.var())
    print("all seasons:", {f: (round(float(x), 3), round(float(e), 3)) for f, x, e in zip(FEATS, b, se)}, "n", len(D))
    D.to_csv(os.path.join(os.environ.get("NA_OUT", "/tmp"), f"nhl_absence_{SK}_{MODE}_{YEARS}_{int(GSH)}.csv"), index=False)


if __name__ == "__main__":
    main()
