"""Offense-vs-defense matchup ranks (overall, passing, rushing, pressure, explosives) with weekly history.

Overall/passing/rushing: opponent-adjusted success rate (65%) and EPA (35%), last season at weight 0.2.
Pressure: real pressures from PFR advanced stats (pressures allowed / generated per dropback), blended with
last season by dropbacks. Explosives: opponent-adjusted explosive-play rate.
"""
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge

from common import FIX, NT, TEAMS, TIX, download, scrimmage

PRIOR_W, ALPHA, W_SUCC, W_EPA = 0.30, 60.0, 0.65, 0.35
CATS = ["overall", "passing", "rushing", "pressure", "explosives"]


def effects(d, y):
    n = len(d)
    rows = np.arange(n)
    X = sparse.hstack([
        sparse.csr_matrix((np.ones(n), (rows, d.posteam.map(TIX).values)), shape=(n, NT)),
        sparse.csr_matrix((np.ones(n), (rows, d.defteam.map(TIX).values)), shape=(n, NT)),
    ]).tocsr()
    yv = d[y].values.astype(float)
    mu = np.average(yv, weights=d.w.values)
    m = Ridge(alpha=ALPHA, fit_intercept=False).fit(X, yv - mu, sample_weight=d.w.values)
    return m.coef_[:NT], m.coef_[NT:]


def z(a):
    s = a.std()
    return (a - a.mean()) / (s if s > 0 else 1)


def pfr_pressure(season):
    out = {}
    for kind in ("pass", "def"):
        p = download(f"pfr_advstats/advstats_week_{kind}_{season}.csv", required=False)
        if p:
            d = pd.read_csv(p, low_memory=False)
            d["team"] = d.team.replace(FIX)
            out[kind] = d[d.game_type == "REG"] if "game_type" in d else d
    return out


def pressure_rates(pf_cur, pf_pri, s_cur, s_pri, cutoff):
    def side(pf, s, wk):
        db_off = s[(s.db == 1) & (s.week <= wk)].groupby("posteam").size().reindex(TEAMS).fillna(0)
        db_def = s[(s.db == 1) & (s.week <= wk)].groupby("defteam").size().reindex(TEAMS).fillna(0)
        allowed = pf.get("pass", pd.DataFrame(columns=["week", "team", "times_pressured"]))
        gen = pf.get("def", pd.DataFrame(columns=["week", "team", "def_pressures"]))
        a = allowed[allowed.week <= wk].groupby("team").times_pressured.sum().reindex(TEAMS).fillna(0)
        gnr = gen[gen.week <= wk].groupby("team").def_pressures.sum().reindex(TEAMS).fillna(0)
        return a.values, db_off.values, gnr.values, db_def.values

    a1, n1, g1, m1 = side(pf_cur, s_cur, cutoff)
    a0, n0, g0, m0 = side(pf_pri, s_pri, 99)
    r_off0 = np.where(n0 > 0, a0 / np.maximum(n0, 1), np.nan)
    r_def0 = np.where(m0 > 0, g0 / np.maximum(m0, 1), np.nan)
    lg_off, lg_def = np.nanmean(r_off0), np.nanmean(r_def0)
    r_off0 = np.nan_to_num(r_off0, nan=lg_off); r_def0 = np.nan_to_num(r_def0, nan=lg_def)
    k = 300.0
    off = (a1 + k * r_off0) / (n1 + k)
    dfn = (g1 + k * r_def0) / (m1 + k)
    return off, dfn


def compute(s_cur, s_pri, pf_cur, pf_pri, cutoff):
    cur = s_cur[s_cur.week <= cutoff].copy(); cur["w"] = 1.0
    pr = s_pri.copy(); pr["w"] = PRIOR_W
    d = pd.concat([pr, cur], ignore_index=True)
    res = {}
    for cat, sub in (("overall", d), ("passing", d[d.db == 1]), ("rushing", d[d.dr == 1])):
        so, sd = effects(sub, "success")
        eo, ed = effects(sub, "epa")
        res[cat] = (W_SUCC * z(so) + W_EPA * z(eo), -(W_SUCC * z(sd) + W_EPA * z(ed)))
    po, pdf = pressure_rates(pf_cur, pf_pri, s_cur, s_pri, cutoff)
    res["pressure"] = (-z(po), z(pdf))
    xo, xd = effects(d, "expl")
    res["explosives"] = (z(xo), -z(xd))
    out = {}
    for cat, (off, dfn) in res.items():
        ro = (-off).argsort().argsort() + 1
        rd = (-dfn).argsort().argsort() + 1
        for t in TEAMS:
            i = TIX[t]
            out.setdefault(t, {})[cat] = {"off_rank": int(ro[i]), "def_rank": int(rd[i]),
                                          "off_score": round(float(off[i]), 2), "def_score": round(float(dfn[i]), 2)}
    return out


def build(season, games, cur_pbp, pri_pbp):
    s_cur, s_pri = scrimmage(cur_pbp), scrimmage(pri_pbp)
    pf_cur, pf_pri = pfr_pressure(season), pfr_pressure(season - 1)
    last = int(s_cur.week.max()) if len(s_cur) else 0
    history = {w: compute(s_cur, s_pri, pf_cur, pf_pri, w) for w in range(0, last + 1)}
    g = games[(games.season == season) & (games.game_type == "REG")]
    sched = [{"week": int(r.week), "date": r.gameday, "time": r.gametime if isinstance(r.gametime, str) else "",
              "away": r.away_team, "home": r.home_team} for _, r in g.iterrows()]
    return {"season": season, "data_through_week": last, "teams": TEAMS, "current": history[last],
            "history": {str(w): h for w, h in history.items()}, "schedule": sched}
