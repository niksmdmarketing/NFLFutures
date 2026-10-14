"""Weekly point-in-time replay of the NHL futures model (research / archive builder).

Same settings as nhl_model.backtest (params_before: earlier seasons only), but a checkpoint every 7 days from the season
start, one league-wide date per checkpoint, regulation wins counted from the opponent's OTL. No injuries (not in the model).
Outputs model/replay/nhl_<season>.csv: season, week, date, gp_avg, team, p_playoff, p_div, p_pres, p_r2, p_r3, p_conf
(= wins the conference, reaches the Final), p_title, then 0/1 outcomes y_playoff, y_div, y_pres, y_conf, y_title.
'p_conf' is mapped to the replay score's 'finals' market (y_finals = y_conf).
Usage: python research/replay_nhl.py <published nhl/data dir> [first] [last]    (env BT_SIMS, default 2000)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nhl  # noqa: E402
import nhl_model as M  # noqa: E402

nhl.NHL_OUT = M.nhl.NHL_OUT = sys.argv[1]
SIMS = int(os.environ.get("BT_SIMS", "2000"))
# Research knobs: NHL_TAU_PRE (preseason widening), NHL_PRIOR_SCALE (stretch preseason prior), NHL_PO_SCALE (playoff gaps).
if os.environ.get("NHL_TAU_PRE"):
    M.TAU_PRE = float(os.environ["NHL_TAU_PRE"])
PRIOR_SCALE = float(os.environ.get("NHL_PRIOR_SCALE", "1"))
PO_SCALE = float(os.environ.get("NHL_PO_SCALE", "1"))
PO_FADE = float(os.environ.get("NHL_PO_FADE", "0"))   # extra playoff-gap multiplier at season start, fading to 0 by game 82
SHOT_W = float(os.environ.get("NHL_SHOT_W", "0"))
SHOT_PO = os.environ.get("NHL_SHOT_PO") == "1"   # use the shot-blended rate only in playoff series (regular season on goals)   # share of the in-season rate from shot differential (x league shooting %)
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")


def alignment(y, teams):
    """Divisions as they stood in season y (start year). 2013-16: 30 teams; 2017-18: 31 teams (VGK). 2021+: the current map."""
    if y >= 2021:
        return {t: M.ALIGN[t] for t in teams}
    if y > 2018 or y < 2014:
        return None
    a = {t: M.ALIGN[t] for t in teams if t in M.ALIGN}
    a["ARI"] = "Pacific"
    a["WPG"] = "Central"
    return a if all(t in a for t in teams) else None


def playoff_outcomes(y, teams):
    path = os.path.join(sys.argv[1], f"games_{y}p.json")
    if not os.path.exists(path):
        return None
    pg = M.read_games(f"{y}p")
    if pg.empty:
        return None
    pg = pg.copy()
    pg["date"] = pd.to_datetime(pg.date)
    last = pg[pg.date == pg.date.max()]
    final_pair = set(last.team) | set(last.opp)
    fin = pg[pg.team.isin(final_pair) & pg.opp.isin(final_pair)]
    wins = fin[fin.res == "W"].groupby("team").size()
    return {"po": set(pg.team), "finalists": final_pair, "champ": wins.idxmax()}


def run_season(TT, GG, fit_years, done, y):
    beta_y, k, tau, total, hfa = M.params_before(TT, GG, fit_years, done, y)
    T = TT[y]
    teams = sorted(T.index)
    align = alignment(y, teams)
    if align is None:
        return None
    out = playoff_outcomes(y, teams)
    if out is None:
        return None
    g = GG[y].copy()
    g["date"] = pd.to_datetime(g.date)
    g["gd"] = M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")
    shots = g.set_index(["date", "team"]).shots if "shots" in g else None
    if SHOT_W and shots is not None:
        g["sa"] = [shots.get((d_, o), np.nan) for d_, o in zip(g.date, g.opp)]
        sh_pct = M.numcol(g, "goalsFor").sum() / pd.to_numeric(g.shots, errors="coerce").sum()
        g["sd"] = (pd.to_numeric(g.shots, errors="coerce") - g.sa) * sh_pct
        g["rate"] = (1 - SHOT_W) * g.gd + SHOT_W * g.sd.fillna(g.gd)
    else:
        g["rate"] = g.gd
    g["pts"] = g.res.map({"W": 2, "OTL": 1, "L": 0}).fillna(0)
    opp_res = g.set_index(["date", "team"]).res
    g["opp_otl"] = [opp_res.get((d_, o)) == "OTL" for d_, o in zip(g.date, g.opp)]
    fin = g.groupby("team").agg(pts=("pts", "sum"), wins=("res", lambda r: (r == "W").sum()), gd=("gd", "sum"))
    comp = fin.pts * 1e6 + fin.wins * 1e3 + fin.gd
    divwin = {d: max([t for t in teams if align[t] == d], key=lambda t: comp[t]) for d in set(align.values())}
    pres = comp.idxmax()
    prior = PRIOR_SCALE * pd.Series(M.prior_features(y, TT).reindex(teams).fillna(0).values @ beta_y, index=teams)
    first, last = g.date.min(), g.date.max()
    cuts = [first]
    d = first + pd.Timedelta(days=7)
    while d < last - pd.Timedelta(days=6):
        cuts.append(d)
        d += pd.Timedelta(days=7)
    rows = []
    for wk, cut in enumerate(cuts):
        pl = g[g.date < cut]
        rm = g[(g.date >= cut) & (g.ha == "H")]
        gp = pl.groupby("team").size().reindex(teams).fillna(0)
        cur = pl.groupby("team").rate.mean().reindex(teams).fillna(0) if len(pl) else pd.Series(0.0, index=teams)
        cur = cur - cur.mean()
        rating = (gp * cur + k * prior) / (gp + k)
        rating = rating - rating.mean()
        po_delta = None
        if SHOT_PO:
            curg = pl.groupby("team").gd.mean().reindex(teams).fillna(0) if len(pl) else pd.Series(0.0, index=teams)
            curg = curg - curg.mean()
            rg = (gp * curg + k * prior) / (gp + k)
            rg = rg - rg.mean()
            po_delta = (rating - rg).reindex(teams).to_numpy(float)
            rating = rg
        win = pl.res == "W"
        state = pd.DataFrame({"points": pl.groupby("team").pts.sum().reindex(teams).fillna(0),
                              "rw": pl.assign(x=(win & ~pl.opp_otl).astype(float)).groupby("team").x.sum().reindex(teams).fillna(0),
                              "gd": pl.groupby("team").gd.sum().reindex(teams).fillna(0)}, index=teams)
        state["row"] = pl.assign(x=win.astype(float)).groupby("team").x.sum().reindex(teams).fillna(0)
        n_avg = float(gp.mean())
        sim = M.simulate(teams, state, list(zip(rm.team, rm.opp)), rating.to_dict(), M.tau_at(tau, n_avg), total, hfa, SIMS, seed=3, div_map=align, po_scale=PO_SCALE + PO_FADE * max(0.0, 1 - n_avg / 82), po_delta=po_delta)
        for i, t in enumerate(teams):
            rows.append(dict(season=y, week=wk, date=str(cut.date()), gp_avg=round(n_avg, 1), team=t, p_playoff=sim["playoffs"][i],
                             p_div=sim["div"][i], p_pres=sim["pres"][i], p_r2=sim["r2"][i], p_r3=sim["r3"][i], p_conf=sim["final"][i],
                             p_title=sim["cup"][i], y_playoff=int(t in out["po"]), y_div=int(divwin[align[t]] == t), y_pres=int(t == pres),
                             y_finals=int(t in out["finalists"]), y_title=int(t == out["champ"])))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cur = nhl.start_year()
    TT, GG = {}, {}
    for y in range(nhl.FIRST, cur + 1):
        t = M.read_team(y)
        if not t.empty:
            TT[y] = t
        gg = M.read_games(y)
        if not gg.empty:
            GG[y] = gg
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    fit_years = [y for y in done if y - 1 in TT]
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 2014
    last = int(sys.argv[3]) if len(sys.argv) > 3 else max(done)
    os.makedirs(OUT, exist_ok=True)
    for y in [z for z in done if first <= z <= last]:
        D = run_season(TT, GG, fit_years, done, y)
        if D is None:
            print("skip", y)
            continue
        D.to_csv(os.path.join(OUT, f"nhl_{y}.csv"), index=False)
        print("season", y, "weeks", D.week.nunique(), flush=True)
