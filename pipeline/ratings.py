"""Team ratings (points vs average) from the frozen v3 model, plus the starting-quarterback adjustment.

1. Opponent-adjusted components (ridge on offense + defense team effects) for the current season so far and
   the whole previous season.
2. Blend current vs prior by opportunity counts with the learned pseudo-counts, scale, apply learned weights.
3. QB layer: value of the expected starter for the next game (depth chart, demoted if listed Out/Doubtful)
   minus the QB who took most of this season's dropbacks, times lambda.
"""
import json
import os

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge

from common import FIX, MODEL, NT, TEAMS, TIX, download, log, scrimmage, special

S = json.load(open(os.path.join(MODEL, "settings.json")))
P = S["ratings"]

COMPS = [
    ("pass_epa", "s", lambda d: d[(d.db == 1) & (d.to == 0)], "epa"),
    ("pass_succ", "s", lambda d: d[d.db == 1], "success"),
    ("sack", "s", lambda d: d[d.db == 1], "sack"),
    ("rush_epa", "s", lambda d: d[d.dr == 1], "epa"),
    ("rush_succ", "s", lambda d: d[d.dr == 1], "success"),
    ("st_epa", "st", lambda d: d, "epa"),
]


def effects(d, y, alpha=20.0):
    if len(d) < 50:
        return np.zeros(NT), np.zeros(NT)
    n = len(d)
    rows = np.arange(n)
    X = sparse.hstack([
        sparse.csr_matrix((np.ones(n), (rows, d.posteam.map(TIX).values)), shape=(n, NT)),
        sparse.csr_matrix((np.ones(n), (rows, d.defteam.map(TIX).values)), shape=(n, NT)),
    ]).tocsr()
    v = d[y].values.astype(float)
    m = Ridge(alpha=alpha, fit_intercept=False).fit(X, v - v.mean())
    return m.coef_[:NT], m.coef_[NT:]


def block(s, st, tag):
    out = {}
    for name, frame, filt, col in COMPS:
        o, df = effects(filt(s if frame == "s" else st), col)
        out[f"{tag}_{name}_off"], out[f"{tag}_{name}_def"] = o, df
    return out


def srs(g):
    g = g[g.result.notna()]
    if len(g) < 8:
        return np.zeros(NT)
    X = np.zeros((len(g), NT))
    X[np.arange(len(g)), g.home_team.map(TIX).values] = 1
    X[np.arange(len(g)), g.away_team.map(TIX).values] = -1
    m = Ridge(alpha=1.0, fit_intercept=True).fit(X, g.result.values)
    return m.coef_ - m.coef_.mean()


def counts(s, st, g):
    c = {
        "n_db_off": s[s.db == 1].groupby("posteam").size(), "n_db_def": s[s.db == 1].groupby("defteam").size(),
        "n_dr_off": s[s.dr == 1].groupby("posteam").size(), "n_dr_def": s[s.dr == 1].groupby("defteam").size(),
        "n_st": st.groupby("posteam").size(),
        "n_games": pd.concat([g[g.result.notna()].home_team, g[g.result.notna()].away_team]).value_counts(),
    }
    return {k: v.reindex(TEAMS).fillna(0).values.astype(float) for k, v in c.items()}


def base_ratings(cur_pbp, pri_pbp, games, season):
    cs, cst = scrimmage(cur_pbp), special(cur_pbp)
    ps, pst = scrimmage(pri_pbp), special(pri_pbp)
    F = {}
    F.update(block(ps, pst, "pri"))
    F.update(block(cs, cst, "cur"))
    F["pri_srs"] = srs(games[(games.season == season - 1) & (games.game_type == "REG")])
    F["cur_srs"] = srs(games[(games.season == season) & (games.game_type == "REG")])
    F.update(counts(cs, cst, games[(games.season == season) & (games.game_type == "REG")]))
    k = P["k"]
    feats = {}
    for g, comps in P["groups"].items():
        n_off, n_def = P["count_cols"][g]
        for side, ncol in (("off", n_off), ("def", n_def)):
            n = F[ncol]
            wc, wp = n / (n + k[g]), k[g] / (n + k[g])
            for c in comps:
                feats[f"c_{c}_{side}"] = wc * F[f"cur_{c}_{side}"]
                feats[f"p_{c}_{side}"] = wp * F[f"pri_{c}_{side}"]
    n = F["n_games"]
    feats["c_srs"] = n / (n + k["srs"]) * F["cur_srs"]
    feats["p_srs"] = k["srs"] / (n + k["srs"]) * F["pri_srs"]
    r = np.zeros(NT)
    for c in P["cols"]:
        x = feats[c] / P["sd"][c]
        if not c.endswith("srs"):
            x = x * P["r"]
        r += P["coef"][c] * x
    r = r - r.mean()
    comp_table = pd.DataFrame({k_: v for k_, v in F.items() if k_.startswith("cur_") or k_.startswith("n_")}, index=TEAMS)
    return r, comp_table


# ---------------- Quarterback layer ----------------
def _qb_frame(pbp, w, tag):
    s = scrimmage(pbp)
    db = s.qb_dropback == 1
    s["qb"] = np.where(db, s.passer_player_id.fillna(s.rusher_player_id), None)
    s["qbname"] = np.where(db, s.passer_player_name.fillna(s.rusher_player_name), None)
    s["w"], s["tag"] = w, tag
    return s[["week", "posteam", "defteam", "epa", "qb", "qbname", "w", "tag"]]


def qb_values(cur_pbp, pri_pbp, pri2_pbp):
    cfg = S["qb"]["cfg"]
    parts = [_qb_frame(cur_pbp, 1.0, 0), _qb_frame(pri_pbp, cfg["w1"], 0)]
    if pri2_pbp is not None and cfg["w2"] > 0:
        parts.append(_qb_frame(pri2_pbp, cfg["w2"], 1))
    d = pd.concat(parts, ignore_index=True)
    n = len(d)
    rows = np.arange(n)
    off_col = d.posteam.map(TIX).values + 64 * d.tag.values
    def_col = 32 + d.defteam.map(TIX).values + 64 * d.tag.values
    X = sparse.csr_matrix((np.ones(n), (rows, off_col)), shape=(n, 128)) + \
        sparse.csr_matrix((np.ones(n), (rows, def_col)), shape=(n, 128))
    qm = d.qb.notna().values
    vc = d.qb[qm].value_counts()
    qbs = list(vc.index)
    low = set(vc[vc < cfg["low_n"]].index)
    qix = {q: i for i, q in enumerate(qbs)}
    r = rows[qm]
    Q = sparse.csr_matrix((np.full(len(r), cfg["qscale"]), (r, [qix[q] for q in d.qb.values[qm]])), shape=(n, len(qbs)))
    lowv = np.array([10.0 if q in low else 0.0 for q in d.qb.values[qm]])
    L = sparse.csr_matrix((lowv, (r, np.zeros(len(r), int))), shape=(n, 1))
    X = sparse.hstack([X, Q, L]).tocsr()
    y = d.epa.values
    mu = np.average(y, weights=d.w.values)
    m = Ridge(alpha=cfg["alpha"], fit_intercept=False).fit(X, y - mu, sample_weight=d.w.values)
    qe = m.coef_[128:128 + len(qbs)] * cfg["qscale"]
    lowe = m.coef_[128 + len(qbs)] * 10.0
    dbg = S["qb"]["dropbacks_per_game"]
    vals = {q: dbg * (qe[i] + (lowe if q in low else 0.0)) for i, q in enumerate(qbs)}
    names = d[qm].drop_duplicates("qb").set_index("qb").qbname.to_dict()
    return vals, dbg * lowe, names


def expected_starters(season, injuries, depth):
    """QB1 from the latest depth chart, demoted to QB2 if listed Out or Doubtful on the latest injury report."""
    out = {}
    if depth is None or depth.empty:
        return out
    d = depth.copy()
    d["team"] = d.team.replace({"LAR": "LA", "JAC": "JAX", "OAK": "LV", "SD": "LAC"})
    d = d[d.pos_abb == "QB"]
    latest = d.groupby("team").dt.transform("max")
    d = d[d.dt == latest].sort_values(["team", "pos_rank"]).drop_duplicates(["team", "gsis_id"])
    inj = {}
    if injuries is not None and not injuries.empty:
        wk = injuries.week.max()
        cur = injuries[injuries.week == wk]
        inj = dict(zip(cur.gsis_id, cur.report_status.fillna("")))
    for t, g in d.groupby("team"):
        qbs = list(zip(g.gsis_id, g.player_name))
        if not qbs:
            continue
        starter, note = qbs[0], ""
        status = inj.get(starter[0], "")
        if status in ("Out", "Doubtful") and len(qbs) > 1:
            note = f"{starter[1]} listed {status}"
            starter = qbs[1]
        out[t] = {"id": starter[0], "name": starter[1], "note": note,
                  "status": inj.get(starter[0], "") or "Active"}
    return out


def team_ratings(season, games, cur_pbp, pri_pbp, pri2_pbp):
    base, comp = base_ratings(cur_pbp, pri_pbp, games, season)
    log("base ratings done")
    vals, low_val, names = qb_values(cur_pbp, pri_pbp, pri2_pbp)
    log("qb values done", len(vals))
    inj_path = download(f"injuries/injuries_{season}.csv", required=False)
    dep_path = download(f"depth_charts/depth_charts_{season}.csv", required=False)
    injuries = pd.read_csv(inj_path) if inj_path else None
    depth = pd.read_csv(dep_path, low_memory=False) if dep_path else None
    exp = expected_starters(season, injuries, depth)
    cur = scrimmage(cur_pbp)
    cur = cur[cur.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id))
    src = cur if len(cur) else scrimmage(pri_pbp).assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id))
    ref = src.groupby("posteam").qb.agg(lambda x: x.value_counts().index[0]).to_dict()
    lam = S["qb"]["lambda"]
    rows = []
    for i, t in enumerate(TEAMS):
        r_id = ref.get(t)
        e = exp.get(t, {})
        e_id = e.get("id", r_id)
        adj = 0.0
        if r_id and e_id and r_id != e_id:
            adj = lam * (vals.get(e_id, low_val) - vals.get(r_id, low_val))
        rows.append({"team": t, "base": float(base[i]), "qb_adj": float(adj),
                     "qb_ref": names.get(r_id, r_id), "qb_expected": e.get("name", names.get(r_id, "")),
                     "qb_expected_status": e.get("status", ""), "qb_note": e.get("note", ""),
                     "qb_value_expected": round(float(vals.get(e_id, low_val)), 2) if e_id else None})
    R = pd.DataFrame(rows).set_index("team")
    R["press_rate"], R["press_adj"] = pressure_adj(season, games, cur_pbp, pri_pbp)
    scale = S["sim"].get("rating_scale", 1.0)
    R["rating"] = scale * (R.base + R.qb_adj) + R.press_adj
    R["rating"] = R.rating - R.rating.mean()
    return R, comp, injuries


def pressure_adj(season, games, cur_pbp, pri_pbp):
    """Points adjustment from pressure rate allowed (PFR pressures per dropback), blended with last season."""
    P = S.get("pressure")
    if not P:
        return pd.Series(np.nan, index=TEAMS), pd.Series(0.0, index=TEAMS)

    def rate(pbp, yr):
        p = download(f"pfr_advstats/advstats_week_pass_{yr}.csv", required=False,
                     max_age_h=2.0 if yr == season else 24 * 365)
        if not p or not len(pbp):
            return pd.Series(np.nan, index=TEAMS), pd.Series(0.0, index=TEAMS)
        d = pd.read_csv(p, low_memory=False)
        d = d[d.game_type == "REG"] if "game_type" in d else d
        d["team"] = d.team.replace(FIX)
        s = scrimmage(pbp)
        db = s[s.db == 1].groupby("posteam").size().reindex(TEAMS)
        pr = d.groupby("team").times_pressured.sum().reindex(TEAMS)
        gp = s.groupby("posteam").game_id.nunique().reindex(TEAMS).fillna(0)
        return pr / db.where(db > 0), gp

    cur, n = rate(cur_pbp, season)
    pri, _ = rate(pri_pbp, season - 1)
    pri = pri.fillna(pri.mean()) if pri.notna().any() else pd.Series(0.22, index=TEAMS)
    k = P["k_games"]
    blend = ((n * cur.fillna(0) + k * pri) / (n + k)).where(n > 0, pri)
    adj = P["points_per_rate"] * (blend - blend.mean())
    return blend, adj.fillna(0.0)
