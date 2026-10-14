"""Game-level test of changes to the NFL team-rating inputs (research; v4 stays frozen).

For every regular-season game 2010-2025 the opponent-adjusted components are rebuilt point-in-time from play-by-play before
that week (as research/nfl_walkforward_weights.py does for v4), with options:
  H      within-season recency: current-season plays weighted 0.5 ** (weeks ago / H)   (0 = equal, as v4)
  WP     drop plays with win probability outside [WP, 1 - WP] (garbage time)              (0 = keep all, as v4)
  EXTRA  add early-down (1st/2nd down) EPA and pass-rate-over-expected components
The home-minus-away feature difference is regressed on the final margin with ridge (alpha from settings, standardised
columns), walk-forward: test season s uses seasons 2010..s-1 only. Scored on game-margin RMSE and win log loss.
Usage: python research/nfl_rating_engine.py <tag> [H] [WP] [EXTRA]   -> data/research/nfl_eng_<tag>.npz, prints scores
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import norm
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
from common import FIX, NT, TIX, games, load_pbp, scrimmage, special  # noqa: E402

P = ratings.P
EFF_ALPHA = float(os.environ.get("ENG_ALPHA", "20"))
PRI2 = os.environ.get("ENG_PRI2") == "1"   # add the season before last as extra (learned) components
OUTDIR = os.path.join(ROOT, "data", "research")


def effects(d, y, w=None, alpha=None):
    alpha = EFF_ALPHA if alpha is None else alpha
    if len(d) < 50:
        return np.zeros(NT), np.zeros(NT)
    n = len(d)
    rows = np.arange(n)
    X = sparse.hstack([sparse.csr_matrix((np.ones(n), (rows, d.posteam.map(TIX).values)), shape=(n, NT)),
                       sparse.csr_matrix((np.ones(n), (rows, d.defteam.map(TIX).values)), shape=(n, NT))]).tocsr()
    v = d[y].values.astype(float)
    sw = None if w is None else w
    mu = np.average(v, weights=sw) if sw is not None else v.mean()
    m = Ridge(alpha=alpha, fit_intercept=False).fit(X, v - mu, sample_weight=sw)
    return m.coef_[:NT], m.coef_[NT:]


COMPS = ratings.COMPS
EXTRA_COMPS = [("early_epa", "s", lambda d: d[d.down <= 2], "epa")]


def block(s, st, tag, wcol, extra):
    out = {}
    comps = COMPS + (EXTRA_COMPS if extra else [])
    for name, frame, filt, col in comps:
        d = filt(s if frame == "s" else st)
        o, df = effects(d, col, d[wcol].values if wcol else None)
        out[f"{tag}_{name}_off"], out[f"{tag}_{name}_def"] = o, df
    if extra:   # pass rate over expected on early downs (offense tendency; not opponent-adjusted)
        e = s[(s.down <= 2) & s.pass_oe.notna()]
        pr = e.groupby("posteam").pass_oe.mean().reindex(list(TIX)).fillna(0).to_numpy() / 100
        out[f"{tag}_proe_off"], out[f"{tag}_proe_def"] = pr, np.zeros(NT)
    return out


def team_features(cur, pri, g, season, week, H, WP, extra, pri2=None):
    cs, cst = scrimmage(cur), special(cur)
    ps, pst = scrimmage(pri), special(pri)
    if WP:
        cs = cs[cs.wp.between(WP, 1 - WP) | cs.wp.isna()]
        ps = ps[ps.wp.between(WP, 1 - WP) | ps.wp.isna()]
    wcol = None
    if H:
        for d in (cs, cst):
            d["rw"] = 0.5 ** ((week - 1 - d.week.astype(float)).clip(lower=0) / H)
        wcol = "rw"
    F = {}
    F.update(block(ps, pst, "pri", None, extra))
    F.update(block(cs, cst, "cur", wcol, extra))
    F["pri_srs"] = ratings.srs(g[(g.season == season - 1) & (g.game_type == "REG")])
    F["cur_srs"] = ratings.srs(g[(g.season == season) & (g.game_type == "REG")])
    F.update(ratings.counts(scrimmage(cur), special(cur), g[(g.season == season) & (g.game_type == "REG")]))
    k = P["k"]
    feats = {}
    groups = dict(P["groups"])
    for grp, comps in groups.items():
        n_off, n_def = P["count_cols"][grp]
        for side, ncol in (("off", n_off), ("def", n_def)):
            n = F[ncol]
            wc, wp_ = n / (n + k[grp]), k[grp] / (n + k[grp])
            for c in comps:
                feats[f"c_{c}_{side}"] = wc * F[f"cur_{c}_{side}"]
                feats[f"p_{c}_{side}"] = wp_ * F[f"pri_{c}_{side}"]
    if extra:
        n_off, n_def = P["count_cols"]["pass"] if "pass" in P["count_cols"] else list(P["count_cols"].values())[0]
        for c in ("early_epa", "proe"):
            for side, ncol in (("off", n_off), ("def", n_def)):
                n = F[ncol]
                kk = list(k.values())[0]
                feats[f"c_{c}_{side}"] = n / (n + kk) * F[f"cur_{c}_{side}"]
                feats[f"p_{c}_{side}"] = kk / (n + kk) * F[f"pri_{c}_{side}"]
    n = F["n_games"]
    feats["c_srs"] = n / (n + k["srs"]) * F["cur_srs"]
    feats["p_srs"] = k["srs"] / (n + k["srs"]) * F["pri_srs"]
    if pri2 is not None and len(pri2):
        p2s, p2st = scrimmage(pri2), special(pri2)
        B2 = block(p2s, p2st, "pr2", None, False)
        for c_, v in B2.items():
            feats["q_" + c_[4:]] = v
    cols = sorted(feats)
    return cols, np.column_stack([feats[c] for c in cols])


def build(tag, H, WP, extra, first=2010, last=2025):
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows_X, rows_y, rows_s, rows_w = [], [], [], []
    cols = None
    for y in range(first, last + 1):
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        pri2 = load_pbp(y - 2) if PRI2 and y - 2 >= 2006 else None
        reg = g[(g.season == y) & (g.game_type == "REG")]
        for w in sorted(reg.week.unique()):
            gg = g.copy()
            m = (gg.season == y) & (gg.game_type == "REG") & (gg.week >= w)
            gg.loc[m, "result"] = np.nan
            cols, X = team_features(cur_all[cur_all.week < w], pri, gg, y, int(w), H, WP, extra, pri2)
            for r in reg[reg.week == w].itertuples():
                if pd.isna(r.result):
                    continue
                rows_X.append(X[TIX[r.home_team]] - X[TIX[r.away_team]])
                rows_y.append(float(r.result))
                rows_s.append(y)
                rows_w.append(int(w))
        print(tag, y, len(rows_y), flush=True)
    path = os.path.join(OUTDIR, f"nfl_eng_{tag}.npz")
    np.savez_compressed(path, X=np.array(rows_X), y=np.array(rows_y), s=np.array(rows_s), w=np.array(rows_w), cols=np.array(cols))
    return path


def score(path, first_test=2013, last_test=2025):
    d = np.load(path, allow_pickle=True)
    X, y, s, w = d["X"], d["y"], d["s"], d["w"]
    sd = X[s < first_test].std(0)
    sd[sd == 0] = 1
    Xs = X / sd
    out = []
    for t in range(first_test, last_test + 1):
        tr, te = s < t, s == t
        m = Ridge(alpha=P["alpha"], fit_intercept=True).fit(Xs[tr], y[tr])
        p = m.predict(Xs[te])
        resid = y[tr] - m.predict(Xs[tr])
        sig = resid.std()
        pw = norm.cdf(p / sig)
        yw = (y[te] > 0).astype(float)
        keep = y[te] != 0
        ll = -np.mean(yw[keep] * np.log(pw[keep]) + (1 - yw[keep]) * np.log(1 - pw[keep]))
        out.append(dict(season=t, rmse=float(np.sqrt(np.mean((y[te] - p) ** 2))), ll=ll, n=int(te.sum()),
                        rmse_late=float(np.sqrt(np.mean(((y[te] - p)[w[te] >= 10]) ** 2)))))
    return pd.DataFrame(out)


if __name__ == "__main__":
    tag = sys.argv[1]
    H = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    WP = float(sys.argv[3]) if len(sys.argv) > 3 else 0
    EX = len(sys.argv) > 4 and sys.argv[4] == "1"
    path = os.path.join(OUTDIR, f"nfl_eng_{tag}.npz")
    if not os.path.exists(path):
        build(tag, H, WP, EX)
    R = score(path)
    R.to_csv(os.path.join(OUTDIR, f"nfl_eng_{tag}.csv"), index=False)
    print(tag, "RMSE %.3f  late %.3f  logloss %.4f" % (R.rmse.mean(), R.rmse_late.mean(), R.ll.mean()))
