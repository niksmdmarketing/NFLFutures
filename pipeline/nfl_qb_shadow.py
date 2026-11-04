"""NFL shadow: an injured starting QB is replaced only for the games he is expected to miss (research/NFL_QB_ESPN_SHADOW_RULE.md).

Live v4 gives the backup every remaining game once the starter is listed Out/Doubtful for the next game. This shadow keeps
v4 identical except for injury-driven QB changes, which it applies game by game:
  * episode: the team's reference QB (most dropbacks this season, as in v4) is Out / Doubtful / IR / PUP / suspended on
    ESPN's NFL injuries feed, or Out / Doubtful on the latest official report (nflverse);
  * replacement: the highest-ranked other QB on the latest depth chart (value from ratings.qb_values, as in v4);
  * games missed, one draw per simulated season: season-ending -> all; ESPN return date -> lognormal around it (sigma 0.45);
    no date -> historical incumbent absence runs (research/qb_news/absence_runs.csv) longer than games already missed.
Live futures are not changed. Only derived numbers are published (no raw ESPN fields such as dates or injury text).
"""
import datetime as dt
import json
import os
import re
import urllib.request

import numpy as np
import pandas as pd

from common import DATA, NT, ROOT, TEAMS, TIX, download, log, scrimmage

URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
RETURN_SIGMA = 0.45     # lognormal spread around ESPN's date (the NBA layer's value, reused, not fitted)
SEED = 11
RUNS = os.path.join(ROOT, "research", "qb_news", "absence_runs.csv")
OUT_STATUS = re.compile(r"^(out|doubtful|injured reserve|ir|physically unable to perform|pup|suspension|suspended)", re.I)
RES_STATUS = re.compile(r"injured reserve|^ir\b|physically unable|^pup\b", re.I)
SEASON_TXT = re.compile(r"(out for|miss) (the )?(rest of the )?season|season[- ]ending", re.I)
LONG_TXT = re.compile(r"\bacl\b|achilles", re.I)
NAMES = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
         "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
         "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
         "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
         "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
         "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
         "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
         "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}


def norm(s):
    s = re.sub(r"[^a-z ]", "", str(s).lower().replace("-", " "))
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def espn_rows(j):
    """ESPN injuries JSON -> rows (team, name, pos, status, return_date, text). Kept in memory / the ignored data cache only."""
    rows = []
    for t in j.get("injuries") or []:
        team = NAMES.get(t.get("displayName"))
        for i in t.get("injuries") or []:
            a = i.get("athlete") or {}
            det = i.get("details") or {}
            pos = ((a.get("position") or {}).get("abbreviation") or "").upper()
            text = " ".join(str(x) for x in (det.get("type"), det.get("detail"), det.get("side"),
                                              i.get("shortComment"), i.get("longComment")) if x)
            rows.append(dict(team=team, name=a.get("displayName"), pos=pos, status=str(i.get("status") or ""),
                             return_date=det.get("returnDate"), text=text))
    return rows


def fetch_espn():
    """Latest feed (6 h cache in the ignored data folder). Returns (rows, ok)."""
    path = os.path.join(DATA, "espn_nfl_injuries.json")
    try:
        if not os.path.exists(path) or (dt.datetime.now().timestamp() - os.path.getmtime(path)) > 6 * 3600:
            req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (futures model)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
            with open(path, "w") as f:
                json.dump(j, f)
        with open(path) as f:
            return espn_rows(json.load(f)), True
    except Exception as e:  # noqa: BLE001
        log("[qb shadow] ESPN feed unavailable:", repr(e)[:160])
        return [], False


def missed_so_far(cur_pbp, ref):
    """Consecutive latest team games (this season) in which the reference QB had no dropback."""
    s = scrimmage(cur_pbp)
    if not len(s):
        return {}
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id))
    out = {}
    for t, d in s.groupby("posteam"):
        q = d.groupby(["week", "game_id"]).qb.apply(set).sort_index()
        m = 0
        for qs in reversed(list(q)):
            if ref.get(t) in qs:
                break
            m += 1
        out[t] = m
    return out


def reference(cur_pbp, pri_pbp):
    """Reference QB per team: most dropbacks this season (last season before any games), exactly as ratings.team_ratings."""
    cur = scrimmage(cur_pbp)
    cur = cur[cur.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id))
    src = cur if len(cur) else scrimmage(pri_pbp).assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id))
    return src.groupby("posteam").qb.agg(lambda x: x.value_counts().index[0]).to_dict()


def episodes(season, cur_pbp, ref, injuries, espn):
    """Teams whose reference QB is out now -> dict(team, ref, repl, kind, date, m, res)."""
    dep_path = download(f"depth_charts/depth_charts_{season}.csv", required=False)
    depth = pd.read_csv(dep_path, low_memory=False) if dep_path else pd.DataFrame()
    known = {}   # (team, normalised full name) -> gsis_id
    qb_depth = {}
    if len(depth):
        d = depth[depth.pos_abb == "QB"].copy()
        d["team"] = d.team.replace({"LAR": "LA", "JAC": "JAX", "OAK": "LV", "SD": "LAC"})
        latest = d.groupby("team").dt.transform("max")
        d = d[d.dt == latest].sort_values(["team", "pos_rank"]).drop_duplicates(["team", "gsis_id"])
        for t, g in d.groupby("team"):
            qb_depth[t] = list(g.gsis_id)
            known.update({(t, norm(n)): i for n, i in zip(g.player_name, g.gsis_id)})
    off = {}
    if injuries is not None and len(injuries):
        wk = injuries.week.max()
        cur = injuries[injuries.week == wk].copy()
        cur["team"] = cur.team.replace({"LAR": "LA", "JAC": "JAX", "OAK": "LV", "SD": "LAC"})
        for t, n, i, st in zip(cur.team, cur.full_name, cur.gsis_id, cur.report_status.fillna("")):
            known.setdefault((t, norm(n)), i)
            if st in ("Out", "Doubtful"):
                off[i] = st
    esp = {}
    for r in espn:
        if not r["team"] or (r["pos"] and r["pos"] != "QB"):
            continue
        i = known.get((r["team"], norm(r["name"])))
        if i and OUT_STATUS.search(r["status"].strip()):
            esp[i] = r
    m_now = missed_so_far(cur_pbp, ref)
    eps = []
    for t in TEAMS:
        q = ref.get(t)
        if not q or (q not in esp and q not in off):
            continue
        r = esp.get(q)
        repl = next((x for x in qb_depth.get(t, []) if x != q), None)
        if repl is None:
            continue
        kind, date, res = "nodate", None, False
        if r is not None:
            res = bool(RES_STATUS.search(r["status"]))
            date = None
            if r.get("return_date"):
                try:
                    date = dt.date.fromisoformat(str(r["return_date"])[:10])
                except ValueError:
                    date = None
            if SEASON_TXT.search(r["text"]) or (date is None and LONG_TXT.search(r["text"])):
                kind, date = "season", None
            elif date is not None and date > dt.date.today():
                kind = "date"
            else:
                date = None
        eps.append(dict(team=t, ref=q, repl=repl, kind=kind, date=date, m=int(m_now.get(t, 0)), res=res,
                        source="espn" if r is not None else "official"))
    return eps


def draw_missed(ep, team_days, N, rng, runs):
    """(N,) number of the team's remaining games missed in each simulated season."""
    n = len(team_days)
    if ep["kind"] == "season":
        return np.full(N, n)
    if ep["kind"] == "date":
        today = dt.date.today()
        k = max(1, (ep["date"] - today).days)
        days = np.exp(np.log(k) + RETURN_SIGMA * rng.standard_normal(N))       # return day, days from today
        gd = np.array([(d - today).days for d in team_days], float)           # kickoff day of each remaining game
        return (gd[None, :] < days[:, None]).sum(1)
    lo = max(ep["m"] + 1, 4 if ep["res"] else 1)
    pool = runs[runs.L >= lo].L.to_numpy()
    if not len(pool):
        return np.full(N, n)
    return np.clip(rng.choice(pool, N) - ep["m"], 1, n)


def build(season, greg, cur_pbp, pri_pbp, pri2_pbp, R, injuries, N):
    """Returns (ratings vector, adj_sims (N, games) or None, summary list, feed ok)."""
    import ratings
    vals, low_val, names = ratings.qb_values(cur_pbp, pri_pbp, pri2_pbp)
    scale, lam = ratings.S["sim"].get("rating_scale", 1.0), ratings.S["qb"]["lambda"]
    espn, ok = fetch_espn()
    eps = episodes(season, cur_pbp, reference(cur_pbp, pri_pbp), injuries, espn)
    g = greg.sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
    left = g.result.isna().values
    gday = pd.to_datetime(g.gameday).dt.date.values
    base = R.base.reindex(TEAMS).values.copy()
    qb = R.qb_adj.reindex(TEAMS).fillna(0).values.copy()
    adj = np.zeros((N, len(g)), np.float32)
    rng = np.random.default_rng(SEED)
    runs = pd.read_csv(RUNS)
    summ = []
    for ep in eps:
        t = ep["team"]
        qb[TIX[t]] = 0.0                                            # no whole-season replacement for this team
        idx = [i for i in range(len(g)) if left[i] and t in (g.home_team[i], g.away_team[i])]
        if not idx:
            continue
        miss = draw_missed(ep, [gday[i] for i in idx], N, rng, runs)
        delta = scale * lam * (vals.get(ep["repl"], low_val) - vals.get(ep["ref"], low_val))
        for j, i in enumerate(idx):
            sign = 1.0 if g.home_team[i] == t else -1.0
            adj[:, i] += np.where(miss > j, sign * delta, 0.0)
        summ.append({"team": t, "qb_out": names.get(ep["ref"], ep["ref"]), "replacement": names.get(ep["repl"], ep["repl"]), "basis": ep["kind"], "source": ep["source"],
                     "already_missed": ep["m"], "median_games_missed": float(np.median(miss)),
                     "games_left": len(idx), "points_per_game": round(float(delta), 2)})
    rating = scale * (base + qb) + R.press_adj.reindex(TEAMS).fillna(0).values
    rating = rating - rating.mean()
    log("[qb shadow] feed ok" if ok else "[qb shadow] feed missing", "episodes", len(summ),
        "with ESPN date", sum(s["basis"] == "date" for s in summ))
    return rating, (adj if summ else None), summ, ok
