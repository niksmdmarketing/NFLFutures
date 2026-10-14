"""Weekly point-in-time replay of the NBA futures model (research / archive builder).

For each past season and each weekly checkpoint (preseason, then every 7 days of the regular season) the ratings are fitted
with nba._fit_ratings on games before the checkpoint only, the real schedule is replayed with later results hidden and
nba._simulate gives the same probabilities as the Futures page. Roster/availability adjustments are not included (no
historical rosters), so these are *replayed* numbers, not what the site showed at the time.

Outputs per season: model/replay/nba_<season>.csv with one row per team per checkpoint:
  season, week, date, gp_avg, team, p_title, p_conf (reach Finals), p_div, p_seed1, p_playoff, mean_wins, then 0/1 outcomes
  y_title, y_finals, y_div, y_seed1, y_playoff.
Usage: python research/replay_nba.py [first_season] [last_season]   (env BT_SIMS, default 2000)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402
import nba_backtest as B  # noqa: E402
import nba_title_backtest as T  # noqa: E402

_DECAY = float(os.environ.get("BT_DECAY", "0.2"))
_CW = float(os.environ.get("BT_CW", "8"))   # live setting since 13 Oct 2026 (was 4)
_orig_fit = N._fit_ratings
N._fit_ratings = lambda boxes, end_year: _orig_fit(boxes, end_year, decay=_DECAY, current_weight=_CW)
N.TAU_FADE = float(os.environ.get("BT_TAUFADE", "0"))
N.TAU_FADE_START = float(os.environ.get("BT_TAUFADE_START", "0"))
N.PO_SCALE = float(os.environ.get("BT_PO_SCALE", "1"))
if os.environ.get("BT_SIGMA"):
    N.GAME_SIGMA = float(os.environ["BT_SIGMA"])
if os.environ.get("BT_TEAM_TAU"):
    N.TEAM_TAU = float(os.environ["BT_TEAM_TAU"])
SIMS = int(os.environ.get("BT_SIMS", "2000"))
PO_K = float(os.environ.get("BT_PO_K", "0"))         # playoff rotation term: k x (top-8 playoff-minutes strength - regular strength)
PO_GAMMA = float(os.environ.get("BT_PO_GAMMA", "1.5"))  # concentration of playoff minutes among the top 8 (1 = drop depth only)
PO_CAP = 42 / 240
PO_MPG = os.environ.get("BT_PO_MPG") == "1"   # rotation by minutes per game (role) rather than total minutes


def _player_ratings(y):
    sys.path.insert(0, os.path.join(ROOT, "research"))
    os.environ.setdefault("NP_KBOX", "2.5")
    os.environ.setdefault("NP_DEV", "1.0")
    import nba_player_replay as NP
    import nba_rapm as RA
    return NP.develop(RA.fit(y, lam=3000, w2=0.5, prior=NP.box_prior(y - 1)), y)


def _po_delta(pbox, rating, prev_assign, prev_mins):
    """Per-team (playoff rotation strength - regular rotation strength), points per 100."""
    if len(pbox) and PO_MPG:
        g0 = pbox.groupby(["team_abbreviation", "athlete_id"]).agg(minutes=("minutes", "sum"), gp=("minutes", "size")).reset_index()
        tg = pbox.groupby("team_abbreviation").game_date.nunique()
        g0 = g0[g0.gp >= np.maximum(3, 0.3 * g0.team_abbreviation.map(tg))]
        g0["minutes"] = g0.minutes / g0.gp
        m = g0[["team_abbreviation", "athlete_id", "minutes"]]
    elif len(pbox):
        m = pbox.groupby(["team_abbreviation", "athlete_id"]).minutes.sum().reset_index()
    else:
        m = pd.DataFrame([(t, a, prev_mins.get(a, 0.0)) for a, t in prev_assign.items()], columns=["team_abbreviation", "athlete_id", "minutes"])
        if PO_MPG:
            m["minutes"] = [PREV_MPG.get(a, 0.0) for a in m.athlete_id]
    out = np.zeros(len(N.TEAMS))
    for t, g in m.groupby("team_abbreviation"):
        if t not in N.TIX or g.minutes.sum() <= 0:
            continue
        g = g.sort_values("minutes", ascending=False)
        r = np.array([rating.get(int(a), -1.0) for a in g.athlete_id])
        sh = g.minutes.to_numpy(float) / g.minutes.sum()
        reg = 5 * float(np.sum(sh * r))
        top = sh[:8] ** PO_GAMMA
        top = top / top.sum()
        for _ in range(5):
            top = np.minimum(top, PO_CAP)
            top = top / top.sum()
        po = 5 * float(np.sum(top * r[:8]))
        out[N.TIX[t]] = PO_K * (po - reg)
    return out - out.mean()


_PB = {}
PREV_MPG = {}


def _pbox(y):
    if y not in _PB:
        d = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y}.csv"), low_memory=False,
                        usecols=["athlete_id", "team_abbreviation", "minutes", "season_type", "game_date"])
        d = d[(pd.to_numeric(d.season_type, errors="coerce") == 2) & (pd.to_numeric(d.minutes, errors="coerce") > 0)].copy()
        d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
        d["minutes"] = pd.to_numeric(d.minutes, errors="coerce")
        d["date"] = pd.to_datetime(d.game_date.astype(str).str[:10])
        _PB[y] = d.dropna(subset=["athlete_id"])
    return _PB[y]
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")


def labels(g):
    """Division winners and conference No.1 seeds from the regular-season results (wins, then point differential)."""
    w, pdiff = {t: 0 for t in N.TEAMS}, {t: 0.0 for t in N.TEAMS}
    for h, a, m in zip(g.home, g.away, g.margin):
        win = h if m > 0 else a
        w[win] += 1
        pdiff[h] += m
        pdiff[a] -= m
    key = {t: (w[t], pdiff[t]) for t in N.TEAMS}
    div = {d: max(ts, key=lambda t: key[t]) for d, ts in N.DIVS.items()}
    seed1 = {"E": max(N.EAST, key=lambda t: key[t]), "W": max(N.WEST, key=lambda t: key[t])}
    return set(div.values()), set(seed1.values())


def run_season(boxes, y):
    out = T.outcomes(boxes, y)
    if out is None:
        return None
    p = N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365, required=False)
    if not p:
        return None
    sched = N._schedule(N._csv(p))
    g = B.season_games(boxes, y)
    div_w, seed1 = labels(g)
    first, last = g.date.min(), g.date.max()
    cuts = [first - pd.Timedelta(days=1)]
    d = first + pd.Timedelta(days=6)
    while d < last - pd.Timedelta(days=6):
        cuts.append(d)
        d += pd.Timedelta(days=7)
    rows = []
    if PO_K:
        rating = _player_ratings(y)
        p1 = _pbox(y - 1).sort_values("date")
        prev_mins = p1.groupby("athlete_id").minutes.sum().to_dict()
        gp1 = p1.groupby("athlete_id").minutes.size()
        PREV_MPG.clear()
        PREV_MPG.update((p1.groupby("athlete_id").minutes.sum() / gp1)[gp1 >= 20].to_dict())
        prev_assign = _pbox(y).sort_values("date").groupby("athlete_id").team_abbreviation.first().to_dict()
    for wk, cutoff in enumerate(cuts):
        if PO_K:
            cur = _pbox(y)
            N.PO_DELTA = _po_delta(cur[cur.date <= cutoff], rating, prev_assign, prev_mins)
        done = g[g.date <= cutoff]
        tr = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
        if len(done):
            tr = pd.concat([tr, boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & boxes.game_id.isin(set(done.gid))]])
        ratings, fit = N._fit_ratings(tr, y)
        N.HFA = float(fit["home_offense_points_per_100"]) if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
        N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).fillna(100.0).to_numpy(float)
        ratings["rating"] = ratings.raw_net - ratings.raw_net.mean()
        s = sched.copy()
        s["completed"] = s.completed & (pd.to_datetime(s.game_date) <= cutoff)
        res = N._simulate(s, ratings, SIMS)
        for t, v in res.items():
            rows.append(dict(season=y, week=wk, date=str(cutoff.date()), gp_avg=round(2 * len(done) / 30, 1), team=t,
                             p_title=v["p_title"], p_conf=v["p_conf"], p_div=v["p_div"], p_seed1=v["p_seed1"], p_playoff=v["p_playoff"],
                             mean_wins=v["mean_wins"], y_title=int(t == out["champ"]), y_finals=int(t in out["finalists"]),
                             y_div=int(t in div_w), y_seed1=int(t in seed1), y_playoff=int(t in out["playoffs"])))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cur = N.season_end_year()
    first = int(sys.argv[1]) if len(sys.argv) > 1 else cur - 5
    last = int(sys.argv[2]) if len(sys.argv) > 2 else cur - 1
    os.makedirs(OUT, exist_ok=True)
    boxes = B.load_boxes(last)
    for y in range(first, last + 1):
        D = run_season(boxes, y)
        if D is None:
            print("skip", y)
            continue
        D.to_csv(os.path.join(OUT, f"nba_{y}.csv"), index=False)
        print("season", y, "weeks", D.week.nunique(), flush=True)
