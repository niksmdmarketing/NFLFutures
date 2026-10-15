"""Preseason test: player-based (RAPM) team ratings vs the live team-results rating with roster step (research).

For each season Y (2014-2026): RAPM from stints before Y (research/nba_rapm.py); projected minutes from season Y-1 (players
back from a near-lost season use Y-2); team = first team played for in Y. Player strength P = sum(rapm x minutes) / (82 x 48)
over a 12-man rotation scaled to 82 x 240 minutes. Compared, against the actual season net rating per 100:
  base  = live team rating before the roster step (research/nba_roster_replay.py, c = 0 rows)
  live  = base + roster step as deployed (c 1.5, plus-minus 0.09, two seasons, returning fix)
  rapm_step = base + c x (P_new - P_old)            (roster step with RAPM values)
  combo = a x base + b x P_new                      (weights fitted leave-one-season-out)
Usage: python research/nba_player_replay.py <roster replay csv for live settings> [lam] [w2]
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nba as N  # noqa: E402
N.OVERRIDES_PATH = ""   # judgement overrides apply to the live season only, never to replays
import nba_rapm as RA  # noqa: E402

D = N.NBA_DATA
ROOKIE = float(os.environ.get("NP_ROOKIE", "-1.0"))
K_BOX = float(os.environ.get("NP_KBOX", "0"))   # ridge prior = K_BOX x box-score impact (live roster-step values)
W3 = float(os.environ.get("NP_W3", "0"))
DEV_YOUNG = float(os.environ.get("NP_DEV", "0"))     # points per 100 added per year below 4 years of experience
DEV_OLD = float(os.environ.get("NP_DECL", "0"))
YLAM = float(os.environ.get("NP_YLAM", "1"))      # ridge multiplier for players with at most YSEAS seasons before the fit
YSEAS = int(os.environ.get("NP_YSEAS", "2"))
YKBOX = float(os.environ.get("NP_YKBOX", "-1"))   # box-prior multiplier for young players (-1 = same as K_BOX)      # points per 100 removed per year above 11 years of experience
_first = None


def first_season():
    global _first
    if _first is None:
        fs = {}
        for y in range(2002, 2028):
            p = os.path.join(D, f"player_box_{y}.csv")
            if not os.path.exists(p):
                continue
            b = pd.read_csv(p, usecols=["athlete_id", "minutes"], low_memory=False)
            b = b[pd.to_numeric(b.minutes, errors="coerce") > 0]
            for a in pd.to_numeric(b.athlete_id, errors="coerce").dropna().astype(int).unique():
                fs.setdefault(int(a), y)
        _first = fs
    return _first


def develop(rating, y):
    if not DEV_YOUNG and not DEV_OLD:
        return rating
    fs = first_season()
    out = {}
    for a, v in rating.items():
        exp = y - fs.get(int(a), y)          # seasons already played before season y
        out[a] = v + DEV_YOUNG * max(0, 4 - exp) - DEV_OLD * max(0, exp - 11)
    return out
_raw = {}


def box_prior(y):
    if K_BOX <= 0:
        return None
    if y not in _raw:
        _raw[y] = pd.read_csv(os.path.join(D, f"player_box_{y}.csv"), low_memory=False)
    v1 = N._player_values(_raw[y])
    y2 = y - 1
    if y2 not in _raw:
        _raw[y2] = pd.read_csv(os.path.join(D, f"player_box_{y2}.csv"), low_memory=False)
    v = N._roster_values(v1, N._player_values(_raw[y2]))
    return {int(float(a)): K_BOX * float(i) for a, i in zip(v.athlete_id, v.impact)}


def pbox(y):
    p = os.path.join(D, f"player_box_{y}.csv")
    d = pd.read_csv(p, low_memory=False, usecols=["athlete_id", "team_abbreviation", "minutes", "season_type", "game_date"])
    d = d[(pd.to_numeric(d.season_type, errors="coerce") == 2) & (pd.to_numeric(d.minutes, errors="coerce") > 0)].copy()
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce").astype("Int64")
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce")
    return d.dropna(subset=["athlete_id"]).sort_values("game_date")


def team_strength(assign, mins, mins2, rating):
    rows = []
    for a, t in assign.items():
        m = float(mins.get(a, 0.0))
        m2 = float(mins2.get(a, 0.0))
        if m < 500 and m2 >= 1000:
            m = m2
        rows.append((t, min(m, 2600.0), rating.get(int(a), ROOKIE)))
    r = pd.DataFrame(rows, columns=["team", "m", "v"]).sort_values(["team", "m"], ascending=[True, False]).groupby("team").head(12)

    def one(g):
        mm = g.m.to_numpy(float)
        if mm.sum() > 0:
            mm = mm * (82 * 240) / mm.sum() if mm.sum() > 82 * 240 else mm
        return float(np.sum(g.v.to_numpy(float) * mm) / (82 * 48))
    return r.groupby("team").apply(one, include_groups=False)


def main(live_csv, lam, w2, first=2014, last=2026):
    L = pd.read_csv(live_csv)
    base = L[(L.ret) & (L.c == 0.0)].set_index(["season", "team"]).pred
    live = L[(L.ret) & (L.c == float(os.environ.get("NP_LIVE_C", "1.5")))].set_index(["season", "team"]).pred
    net = L[(L.ret) & (L.c == 0.0)].set_index(["season", "team"]).net
    pb = {y: pbox(y) for y in range(first - 2, last + 1)}
    out = []
    for y in range(first, last + 1):
        lm = None
        if YLAM != 1:
            fs = first_season()
            lm = {a: YLAM for a, f in fs.items() if (y - 1) - f + 1 <= YSEAS}
        pri = box_prior(y - 1)
        if YKBOX >= 0 and pri:
            fs = first_season()
            pri = {a: (v * YKBOX / K_BOX if (y - 1) - fs.get(a, y) + 1 <= YSEAS else v) for a, v in pri.items()}
        rating = develop(RA.fit(y, lam=lam, w2=w2, w3=W3, prior=pri, lam_mult=lm), y)
        p1, p2 = pb[y - 1], pb[y - 2]
        mins = p1.groupby("athlete_id").minutes.sum()
        mins2 = p2.groupby("athlete_id").minutes.sum()
        old = p1.groupby("athlete_id").team_abbreviation.last().to_dict()
        new = pb[y].groupby("athlete_id").team_abbreviation.first().to_dict()
        Po = team_strength(old, mins, mins2, rating).reindex(N.TEAMS).fillna(0)
        Pn = team_strength(new, mins, mins2, rating).reindex(N.TEAMS).fillna(0)
        for t in N.TEAMS:
            if (y, t) not in base.index:
                continue
            out.append(dict(season=y, team=t, base=base[(y, t)], live=live[(y, t)], net=net[(y, t)],
                            p_new=Pn[t] - Pn.mean(), p_old=Po[t] - Po.mean()))
    return pd.DataFrame(out)


def score(R):
    res = {}
    R = R.copy()
    for c in (0.5, 1.0, 1.5):
        R[f"step{c}"] = R.base + c * (R.p_new - R.p_old)
    # combo weights leave-one-season-out
    pred = pd.Series(index=R.index, dtype=float)
    for y in R.season.unique():
        tr = R[R.season != y]
        X = np.c_[tr.base, tr.p_new]
        w = np.linalg.lstsq(X, tr.net, rcond=None)[0]
        te = R.season == y
        pred[te] = np.c_[R.base[te], R.p_new[te]] @ w
    R["combo"] = pred
    X = np.c_[R.base, R.p_new]
    res["combo_weights_all"] = np.linalg.lstsq(X, R.net, rcond=None)[0].round(3).tolist()
    for k in ["base", "live", "step0.5", "step1.0", "step1.5", "combo", "p_new"]:
        e = (R[k] - R.net).abs().groupby(R.season).mean()
        res[k] = e
    return res


if __name__ == "__main__":
    lam = float(sys.argv[2]) if len(sys.argv) > 2 else 3000
    w2 = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    R = main(sys.argv[1], lam, w2)
    R.to_csv(os.environ.get("NP_OUT", f"/tmp/nba_player_replay_{int(lam)}_{w2}.csv"), index=False)
    s = score(R)
    live = s["live"]
    print("lam", lam, "w2", w2, "combo weights (base, player)", s["combo_weights_all"])
    for k in ["base", "live", "step0.5", "step1.0", "step1.5", "combo", "p_new"]:
        d = live - s[k]
        print(f"{k:8s} MAE {s[k].mean():.3f}  vs live {d.mean():+.3f}  better {int((d > 0).sum())}/{len(d)}")
