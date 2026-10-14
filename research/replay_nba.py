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
PO_MPG = os.environ.get("BT_PO_MPG") == "1"
PO_AVAIL = os.environ.get("BT_PO_AVAIL") == "1"   # role = minutes per game; star availability drawn per simulated season
PO_H = float(os.environ.get("BT_PO_H", "0.08"))   # chance a currently healthy player misses the playoffs, whole season ahead
AV_B = (-4.579, 1.992, 5.308)   # logistic: intercept, share of team games missed, share of the team's last 15 missed (2011-26)
N_SCEN = 400
PO_GAMES = os.environ.get("BT_PO_GAMES") == "1"
FULL = os.environ.get("BT_FULL") == "1"   # live roster step + RAPM preseason mix (with development) as in nba.build_data
_RAW = {}


def _raw(y):
    if y not in _RAW:
        _RAW[y] = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y}.csv"), low_memory=False)
    return _RAW[y]


def _season_extras(y):
    """Inputs for the live roster step and player mix, point in time: values from Y-1 and Y-2, last season's roster =
    each player's last team in Y-1, this season's roster = first team he plays for in Y (known by opening night)."""
    import nba_rapm as LR
    v1, v2 = N._player_values(_raw(y - 1)), N._player_values(_raw(y - 2))
    p1, p0 = _pbox(y - 1).sort_values("date"), _pbox(y).sort_values("date")
    prior_roster = p1.groupby("athlete_id").team_abbreviation.last().reset_index()
    cur_roster = p0.groupby("athlete_id").team_abbreviation.first().reset_index()
    if os.environ.get("BT_FULL_NOLEAK") == "1":   # players absent all season stay on last season's team (bounds the leak)
        gone = prior_roster[~prior_roster.athlete_id.isin(cur_roster.athlete_id)]
        cur_roster = pd.concat([cur_roster, gone], ignore_index=True)
    for r in (prior_roster, cur_roster):
        r["athlete_id"] = r.athlete_id.astype("int64").astype(str)
    rv = N._roster_values(v1, v2)
    return v1, v2, prior_roster, cur_roster, rv, LR   # count earlier seasons' playoff games in the team ratings
PO_LASTPO = os.environ.get("BT_PO_LASTPO") == "1"   # scale each player's minutes by last season's playoff/regular mpg ratio
PO_RATIO = {}


def _po_ratio(y):
    """athlete -> (playoff mpg / regular mpg) last season, players with 4+ playoff games, clipped to [0.5, 1.5]."""
    d = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y - 1}.csv"), low_memory=False,
                    usecols=["athlete_id", "minutes", "season_type", "game_id"])
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce")
    d["st"] = pd.to_numeric(d.season_type, errors="coerce")
    d = d[d.minutes > 0]
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    po = d[d.st == 3].groupby("athlete_id").minutes.agg(["mean", "size"])
    rs = d[d.st == 2].groupby("athlete_id").minutes.agg(["mean", "size"])
    j = po.join(rs, lsuffix="_po", rsuffix="_rs", how="inner")
    j = j[(j.size_po >= 4) & (j.size_rs >= 20)]
    return (j.mean_po / j.mean_rs).clip(0.5, 1.5).to_dict()   # rotation by minutes per game (role) rather than total minutes


def _player_ratings(y):
    sys.path.insert(0, os.path.join(ROOT, "research"))
    os.environ.setdefault("NP_KBOX", "2.5")
    os.environ.setdefault("NP_DEV", "1.0")
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_nba_rapm", os.path.join(ROOT, "research", "nba_rapm.py"))
    RA = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(RA)
    sys.modules["research_nba_rapm"] = RA
    import nba_player_replay as NP
    NP.RA = RA
    return NP.develop(RA.fit(y, lam=3000, w2=0.5, prior=NP.box_prior(y - 1)), y)


def _po_scen(pbox, rating, prev_assign, prev_mins, prev_info, rng):
    """Scenario matrix (N_SCEN x teams): role by minutes per game, availability drawn from the history-based model."""
    teams = {}
    if len(pbox):
        tg = pbox.groupby("team_abbreviation").game_date.nunique()
        dates = pbox.groupby("team_abbreviation").game_date.apply(lambda s: set(sorted(s.unique())[-15:]))
        g0 = pbox.groupby(["team_abbreviation", "athlete_id"]).agg(m=("minutes", "sum"), gp=("minutes", "size")).reset_index()
        late = pbox.groupby(["team_abbreviation", "athlete_id"]).game_date.apply(set)
        for r in g0.itertuples():
            t = r.team_abbreviation
            if r.gp < max(3, 0.3 * tg[t]):
                continue
            nl = min(15, tg[t])
            lm = 1 - len(late[(t, r.athlete_id)] & dates[t]) / nl
            teams.setdefault(t, []).append((r.athlete_id, r.m / r.gp, r.m, 1 - r.gp / tg[t], lm))
        rem = max(0.0, 1 - float(tg.mean()) / 82)
    else:
        for a, t in prev_assign.items():
            info = prev_info.get(a)
            if info:
                teams.setdefault(t, []).append((a, info[0], prev_mins.get(a, 0.0), info[1], 0.0))
        rem = 1.0
    out = np.zeros((N_SCEN, len(N.TEAMS)))
    for t, pl in teams.items():
        if t not in N.TIX:
            continue
        pl.sort(key=lambda x: -x[1])
        r = np.array([rating.get(int(a), -1.0) for a, *_ in pl])
        mpg = np.array([x[1] for x in pl])
        tot = np.array([x[2] for x in pl])
        reg = 5 * float(np.sum(tot / tot.sum() * r))
        z = AV_B[0] + AV_B[1] * np.array([x[3] for x in pl]) + AV_B[2] * np.array([x[4] for x in pl])
        pf = 1 / (1 + np.exp(-z))
        pout = 1 - (1 - pf) * (1 - PO_H * rem)
        avail = rng.random((N_SCEN, len(pl))) >= pout[None, :]
        for k in range(N_SCEN):
            idx = np.flatnonzero(avail[k])[:8]
            if len(idx) == 0:
                continue
            top = mpg[idx] ** PO_GAMMA
            top = top / top.sum()
            for _ in range(5):
                top = np.minimum(top, PO_CAP)
                top = top / top.sum()
            out[k, N.TIX[t]] = PO_K * (5 * float(np.sum(top * r[idx])) - reg)
    return out - out.mean(axis=1, keepdims=True)


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
        g = g.copy()
        r_all = np.array([rating.get(int(a), -1.0) for a in g.athlete_id])
        reg = 5 * float(np.sum(g.minutes.to_numpy(float) / g.minutes.sum() * r_all))
        if PO_LASTPO:
            g["minutes"] = g.minutes * np.array([PO_RATIO.get(a, 1.0) for a in g.athlete_id])
        g = g.sort_values("minutes", ascending=False)
        r = np.array([rating.get(int(a), -1.0) for a in g.athlete_id])
        sh = g.minutes.to_numpy(float) / g.minutes.sum()
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
    if FULL:
        v1, v2, prior_roster, cur_roster, rv, LR = _season_extras(y)
        prating = _player_ratings(y)
    if PO_K:
        rating = _player_ratings(y)
        p1 = _pbox(y - 1).sort_values("date")
        prev_mins = p1.groupby("athlete_id").minutes.sum().to_dict()
        gp1 = p1.groupby("athlete_id").minutes.size()
        PREV_MPG.clear()
        PREV_MPG.update((p1.groupby("athlete_id").minutes.sum() / gp1)[gp1 >= 20].to_dict())
        tg1 = p1.groupby("team_abbreviation").game_date.nunique()
        last_team = p1.groupby("athlete_id").team_abbreviation.last()
        prev_info = {a: (PREV_MPG[a], max(0.0, 1 - gp1[a] / tg1.get(last_team[a], 82))) for a in PREV_MPG}
        rng = np.random.default_rng(11)
        PO_RATIO.clear()
        if PO_LASTPO:
            PO_RATIO.update(_po_ratio(y))
        prev_assign = _pbox(y).sort_values("date").groupby("athlete_id").team_abbreviation.first().to_dict()
    for wk, cutoff in enumerate(cuts):
        if PO_K:
            cur = _pbox(y)
            if PO_AVAIL:
                N.PO_DELTA_SCEN = _po_scen(cur[cur.date <= cutoff], rating, prev_assign, prev_mins, prev_info, rng)
            else:
                N.PO_DELTA = _po_delta(cur[cur.date <= cutoff], rating, prev_assign, prev_mins)
        done = g[g.date <= cutoff]
        tr = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
        if PO_GAMES:
            tr = tr.copy()
            tr.loc[pd.to_numeric(tr.season_type, errors="coerce") == 3, "season_type"] = 2
        if len(done):
            tr = pd.concat([tr, boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & boxes.game_id.isin(set(done.gid))]])
        ratings, fit = N._fit_ratings(tr, y)
        N.HFA = float(fit["home_offense_points_per_100"]) if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
        N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).fillna(100.0).to_numpy(float)
        ratings["rating"] = ratings.raw_net - ratings.raw_net.mean()
        if FULL:
            gp = 2 * len(done) / 30
            ratings, _ = N._roster_adjustment(ratings, v1, prior_roster.copy(), cur_roster.copy(), v2, gp)
            share = LR.MIX * max(0.0, 1.0 - gp / LR.MIX_GAMES)
            if share > 0:
                P = LR.team_strength(cur_roster, rv, prating, N.TEAMS)
                ratings["rating"] = (1 - share) * ratings.rating + share * ratings.team.map(P).fillna(0)
                ratings["rating"] -= ratings.rating.mean()
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
