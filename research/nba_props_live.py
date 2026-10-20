"""NBA props forward test: live forecaster and archiver (research/NBA_MINUTES_M2B_RULE.md, forward-test protocol).

Every run (GitHub Actions, every 15 minutes in the US game window):
- reads the 2026-27 schedule; for each regular-season game and horizon (60 and 360 minutes before tip-off) whose cutoff lies within
  the next 45 minutes (cutoff - 45 min <= now <= cutoff), produces a forecast from inputs retrieved now;
- inputs: completed box scores (SportsDataverse release; ESPN game summaries fill completed games the release does not yet have),
  the latest official NBA injury report published at or before now, archived official reports for earlier games;
- frozen method and parameters: model/nba_props_live_params_2027.json (2026 rows use ..._2026.json, as in the research);
- writes one gzipped JSON per game and horizon to <archive>/nba/props_forward/<date>/, with versions v2 (M2 minutes) and v3 (M2b),
  complete distributions, input timestamps and hashes, and the code commit; the run log goes to <archive>/nba/props_forward/runs/.
Usage: python research/nba_props_live.py <archive_dir> [--now ISO] [--force-game GAME_ID --horizon 60]
"""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402
import nba_minutes_test as M  # noqa: E402
import nba_props_live_core as C  # noqa: E402

SEASON = int(os.environ.get("NBA_PROPS_SEASON", "2027"))
REPLAY = os.environ.get("NBA_PROPS_REPLAY_REPORTS")   # local report files for an offline replay check (never used live)
HORIZONS = (60, 360)
WINDOW_MIN = 45
SUP = {"pts": 100, "reb": 45, "ast": 35}
MD_REPORTS = ["research/nba_official_reports_2023_2025.csv.gz", "research/nba_official_reports_2026_2026.csv.gz"]
RAW_MD = "https://raw.githubusercontent.com/niksmdmarketing/NFLFutures/market-data/"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={}"
UA = {"User-Agent": "SportsFuturesResearch/1.0"}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def now_utc(args):
    return pd.Timestamp(args.now).tz_convert("UTC") if args.now else pd.Timestamp.now(tz="UTC")


# ---------------------------------------------------------------- schedule and targets
def schedule():
    p = N._download("espn_nba_schedules", f"nba_schedule_{SEASON}.csv", 0.2)
    s = pd.read_csv(p, low_memory=False)
    s = s[(pd.to_numeric(s.season_type, errors="coerce") == 2) & s.home_abbreviation.isin(N.TEAMS) & s.away_abbreviation.isin(N.TEAMS)].copy()
    s["tip"] = pd.to_datetime(s.game_date_time, utc=True, errors="coerce", format="ISO8601")
    s["completed"] = s.status_type_completed.astype(str).str.lower().eq("true")
    return s.dropna(subset=["tip"]), sha(open(p, "rb").read())


def targets(s, now):
    out = []
    for g in s.itertuples():
        if g.completed or g.tip <= now:
            continue
        for h in HORIZONS:
            cut = g.tip - pd.Timedelta(minutes=h)
            if cut - pd.Timedelta(minutes=WINDOW_MIN) <= now <= cut:
                out.append((int(g.game_id), h, cut))
    return out


# ---------------------------------------------------------------- box scores
def espn_box(gid):
    """completed game from ESPN's summary: (player rows, team rows) in the SportsDataverse column names used here."""
    js = json.loads(get(ESPN_SUMMARY.format(gid)))
    comp = js["header"]["competitions"][0]
    if not comp["status"]["type"].get("completed"):
        return None, None
    tip = comp["date"]
    teams = {c["team"]["id"]: c for c in comp["competitors"]}
    prow, trow = [], []
    for tb in js["boxscore"]["players"]:
        team = tb["team"]
        c = teams[team["id"]]
        opp = [x for x in comp["competitors"] if x["team"]["id"] != team["id"]][0]
        st = tb["statistics"][0]
        keys = [k.lower() for k in st.get("keys", st.get("names", []))]
        for a in st["athletes"]:
            vals = dict(zip(keys, a.get("stats", [])))
            mins = vals.get("minutes", vals.get("min", "0")) or "0"
            def num(k):
                try:
                    return float(str(vals.get(k, "0")).split("-")[0])
                except ValueError:
                    return 0.0
            prow.append(dict(game_id=int(gid), season=SEASON, season_type=2, game_date_time=tip, athlete_id=int(a["athlete"]["id"]),
                             athlete_display_name=a["athlete"]["displayName"], team_abbreviation=team["abbreviation"],
                             team_display_name=team["displayName"], minutes=float(mins) if str(mins).replace(".", "").isdigit() else 0.0,
                             starter=bool(a.get("starter")), athlete_position_abbreviation=(a["athlete"].get("position") or {}).get("abbreviation", ""),
                             points=num("points"), rebounds=num("rebounds"), assists=num("assists"),
                             did_not_play=bool(a.get("didNotPlay")), opponent_team_abbreviation=opp["team"]["abbreviation"],
                             home_away=c["homeAway"], team_score=float(c.get("score", 0) or 0)))
    for t in js["boxscore"]["teams"]:
        vals = {x["name"]: x.get("displayValue") for x in t["statistics"]}
        c = teams[t["team"]["id"]]
        opp = [x for x in comp["competitors"] if x["team"]["id"] != t["team"]["id"]][0]
        def pair(name):
            v = str(vals.get(name, "0-0"))
            return [float(x) for x in v.split("-")] if "-" in v else [float(v or 0), 0.0]
        fg, ft = pair("fieldGoalsMade-fieldGoalsAttempted"), pair("freeThrowsMade-freeThrowsAttempted")
        trow.append(dict(game_id=int(gid), season=SEASON, season_type=2, game_date=tip[:10], team_abbreviation=t["team"]["abbreviation"],
                         opponent_team_abbreviation=opp["team"]["abbreviation"], team_home_away=c["homeAway"],
                         team_score=float(c.get("score", 0) or 0), opponent_team_score=float(opp.get("score", 0) or 0),
                         field_goals_attempted=fg[1], offensive_rebounds=float(vals.get("offensiveRebounds", 0) or 0),
                         total_turnovers=float(vals.get("totalTurnovers", vals.get("turnovers", 0)) or 0),
                         turnovers=float(vals.get("turnovers", 0) or 0), free_throws_attempted=ft[1]))
    return pd.DataFrame(prow), pd.DataFrame(trow)


def boxes(s, log):
    """player and team boxes for seasons 2025-2027; completed 2027 games missing from the release are filled from ESPN."""
    pf, tf = [], []
    for y in (SEASON - 2, SEASON - 1, SEASON):
        age = 0.2 if y == SEASON else 24 * 365
        pp = N._download("espn_nba_player_boxscores", f"player_box_{y}.csv", age, required=(y != SEASON))
        tp = N._download("espn_nba_team_boxscores", f"team_box_{y}.csv", age, required=(y != SEASON))
        if pp and os.path.exists(pp):
            pf.append(pd.read_csv(pp, low_memory=False))
        if tp and os.path.exists(tp):
            tf.append(pd.read_csv(tp, low_memory=False))
    P = pd.concat(pf, ignore_index=True)
    T = pd.concat(tf, ignore_index=True)
    if REPLAY:   # offline replay: only games completed before the replay time, no ESPN
        P = P[pd.to_datetime(P.game_date_time, utc=True, format="ISO8601") < s.attrs["now"] - pd.Timedelta(hours=3)]
        T = T[pd.to_numeric(T.game_id, errors="coerce").isin(set(pd.to_numeric(P.game_id, errors="coerce")))]
        log["box"] = dict(replay=True)
        return P, T
    have = set(pd.to_numeric(P[P.season == SEASON].game_id, errors="coerce").dropna().astype(int)) if len(P) else set()
    done = s[s.completed & ~s.game_id.astype(int).isin(have)]
    filled, failed = [], []
    for gid in done.game_id.astype(int):
        try:
            p_, t_ = espn_box(gid)
            if p_ is not None and len(p_):
                P = pd.concat([P, p_], ignore_index=True)
                T = pd.concat([T, t_], ignore_index=True)
                filled.append(gid)
        except Exception as e:  # noqa: BLE001
            failed.append([gid, repr(e)[:200]])
    log["box"] = dict(release_games_2027=len(have), espn_filled=filled, espn_failed=failed)
    return P, T


# ---------------------------------------------------------------- official reports
def reports(now, archive, log):
    import nba_official as O
    frames = []
    if REPLAY:
        R = _prep_reports(pd.concat([pd.read_csv(f) for f in REPLAY.split(",")], ignore_index=True))
        log["report"] = dict(replay=True)
        return R[R.status.isin(["Out", "Doubtful", "Questionable", "Probable", "Available"]) & (R.rtime <= now)]
    for f in MD_REPORTS:
        try:
            frames.append(pd.read_csv(io.BytesIO(get(RAW_MD + f, timeout=60)), compression="gzip"))
        except Exception as e:  # noqa: BLE001
            log.setdefault("report_errors", []).append([f, repr(e)[:200]])
    store = os.path.join(archive, "nba", "props_forward", "reports")
    os.makedirs(store, exist_ok=True)
    url, pdf, et = O.latest(now.to_pydatetime(), hours_back=30)
    meta = None
    if pdf:
        label = et.strftime("%Y-%m-%d %I_%M%p")
        rows = pd.DataFrame(O.parse(pdf))
        rows["report"] = label
        rows["season"] = SEASON
        rows.to_csv(os.path.join(store, et.strftime("%Y%m%dT%H%M") + ".csv.gz"), index=False, compression="gzip")
        meta = dict(url=url, label=label, sha256=sha(pdf), rows=len(rows), retrieved_utc=pd.Timestamp.now(tz="UTC").isoformat())
    for f in sorted(os.listdir(store)):
        if f.endswith(".csv.gz"):
            frames.append(pd.read_csv(os.path.join(store, f)))
    R = _prep_reports(pd.concat(frames, ignore_index=True))
    R = R[R.status.isin(["Out", "Doubtful", "Questionable", "Probable", "Available"]) & (R.rtime <= now)]    # published at or before now
    log["report"] = meta
    return R


# ---------------------------------------------------------------- features and forecasts
def run(args):
    now = now_utc(args)
    if REPLAY:
        N._download = lambda tag, name, age, required=True: (os.path.join(N.NBA_DATA, name) if os.path.exists(os.path.join(N.NBA_DATA, name)) else None)
    log = {"run_utc": now.isoformat(), "generated_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    s, sched_hash = schedule()
    s.attrs["now"] = now
    if REPLAY:
        s["completed"] = s.tip < now - pd.Timedelta(hours=3)
    T = targets(s, now)
    if args.force_game:
        g = s[s.game_id.astype(int) == int(args.force_game)].iloc[0]
        T = [(int(g.game_id), int(args.horizon), g.tip - pd.Timedelta(minutes=int(args.horizon)))]
    log["targets"] = [[g, h, c.isoformat()] for g, h, c in T]
    runs = os.path.join(args.archive, "nba", "props_forward", "runs")
    os.makedirs(runs, exist_ok=True)
    if not T:
        print("no targets", now)
        return log
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    params = {y: json.load(open(os.path.join(ROOT, "model", f"nba_props_live_params_{y}.json"))) for y in (SEASON - 1, SEASON)}
    phash = sha(open(os.path.join(ROOT, "model", f"nba_props_live_params_{SEASON}.json"), "rb").read())
    P, TB = boxes(s, log)
    R = reports(now, args.archive, log)
    # stage-one candidate rows: research build over 2025-2027 boxes plus one placeholder row per target team
    d = P[pd.to_numeric(P.season_type, errors="coerce") == 2].copy()
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0.0)
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    d = d.dropna(subset=["athlete_id"])
    d["athlete_id"] = d.athlete_id.astype(int)
    d["game_id"] = pd.to_numeric(d.game_id, errors="coerce").astype(int)
    d["season"] = pd.to_numeric(d.season, errors="coerce").astype(int)
    d = d[d.game_id.isin(set(s[s.completed | s.game_id.astype(int).isin([t[0] for t in T])].game_id.astype(int))) | (d.season < SEASON)]
    tgt_ids = sorted({t[0] for t in T})
    ph = []
    for gid in tgt_ids:
        g = s[s.game_id.astype(int) == gid].iloc[0]
        for side in ("home", "away"):
            ph.append(dict(game_id=gid, season=SEASON, season_type=2, game_date_time=g.game_date_time, athlete_id=-1, athlete_display_name="",
                           team_abbreviation=getattr(g, f"{side}_abbreviation"), team_display_name=getattr(g, f"{side}_display_name"),
                           minutes=0.0, starter=False, athlete_position_abbreviation=""))
    d = pd.concat([d[~d.game_id.isin(tgt_ids)], pd.DataFrame(ph)], ignore_index=True)
    d["tip"] = pd.to_datetime(d.game_date_time, utc=True, errors="coerce", format="ISO8601")
    d["starter"] = d.starter.astype(str).str.lower().eq("true")
    d["grp"] = d.athlete_position_abbreviation.map(M.GROUP).fillna("W")
    d = d.sort_values(["tip", "game_id"])
    # name -> athlete id uses the report's season (as in the research). Early in a season a listed player may have no box row yet this
    # season; such rows are matched through last season's names instead (unique matches only) by relabelling their season.
    keys = d.assign(k=d.athlete_display_name.map(M.name_key)).groupby(["season", "k"]).athlete_id.nunique()
    R = R.copy()
    rk = R.player.map(M.player_key)
    cur_ok = np.array([keys.get((int(y), k), 0) == 1 for y, k in zip(R.season, rk)])
    prev_ok = np.array([keys.get((int(y) - 1, k), 0) == 1 for y, k in zip(R.season, rk)])
    fix = ~cur_ok & prev_ok & (R.season == SEASON).to_numpy()          # current season only; earlier seasons exactly as in the research
    R.loc[fix, "season"] = SEASON - 1
    log["report_rows_matched_via_last_season"] = int(fix.sum())
    tmp = tempfile.mkdtemp()
    M.ROWS = os.path.join(tmp, "rows.csv.gz")
    M.load_box = lambda: d
    M.load_reports = lambda src: R
    M.build(tmp)
    rows = pd.read_csv(M.ROWS, low_memory=False)
    # stage-one projections for 2026 and 2027 rows (each season with its own frozen parameters, as in the research)
    Dp = C.prep(rows[(rows.fallback.fillna(0) == 0) & (rows.aid != -1)].copy())
    proj = []
    for y in (SEASON - 1, SEASON):
        Z = Dp[Dp.season == y]
        for tag in ("1", "6"):
            pa, mu, sd = C.predict_stage1(Z, params[y]["stage1"][tag], tag)
            q = M.disc_normal(mu, sd)
            proj.append(pd.DataFrame(dict(tag=tag, season=y, game_id=Z.game_id.to_numpy(), team=Z.team.to_numpy(), aid=Z.aid.to_numpy().astype(int),
                                          pa=pa, emin_app=q @ np.arange(1, M.MAXM + 1), mu=mu, sd=sd)))
    proj = pd.concat(proj, ignore_index=True)
    # games table: ratings fitted on completed games before now (pace and expected margin; no injury term - pre-specified)
    TB2 = TB.copy()
    TB2["game_date"] = pd.to_datetime(TB2.game_date, errors="coerce")
    Rt, fit = N._fit_ratings(TB2[TB2.game_date < now.tz_convert(None).normalize()], SEASON)
    hca = fit["home_offense_points_per_100"] if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
    r = Rt.set_index("team")
    allg = pd.concat([s[["game_id", "game_date", "home_abbreviation", "away_abbreviation"]].rename(
        columns={"game_id": "gid", "game_date": "date", "home_abbreviation": "home", "away_abbreviation": "away"})])
    hist_g = TB[TB.team_home_away.astype(str) == "home"][["game_id", "game_date", "team_abbreviation", "opponent_team_abbreviation"]].rename(
        columns={"game_id": "gid", "game_date": "date", "team_abbreviation": "home", "opponent_team_abbreviation": "away"})
    G = pd.concat([hist_g, allg], ignore_index=True)
    G["gid"] = pd.to_numeric(G.gid, errors="coerce").astype(int)
    G = G.drop_duplicates("gid")
    G = G[G.home.isin(r.index) & G.away.isin(r.index)]
    G["date"] = pd.to_datetime(G.date.astype(str).str[:10])
    G["pace_h"] = G.home.map(r.pace)
    G["pace_a"] = G.away.map(r.pace)
    G["m_L"] = (G.home.map(r.off) + G.home.map(r["def"]) - G.away.map(r.off) - G.away.map(r["def"]) + hca) * (G.pace_h + G.pace_a) / 200
    # prop features (research build) on these rows
    import nba_props_simple_test as PS
    import nba_minutes_tail_test as TT
    PS.W = tmp
    G.to_csv(os.path.join(tmp, "games.csv.gz"), index=False, compression="gzip")
    proj.to_csv(os.path.join(tmp, "proj_minutes.csv.gz"), index=False, compression="gzip")
    pb = d[d.athlete_id != -1].copy()
    pbx = P.copy()
    PS.player_box = lambda: _pb(pbx, d)
    TBr = N._regular_boxes(TB)
    PS.game_poss = lambda: TBr.groupby(TBr.game_id.astype(int)).poss.first()
    PS.build()
    F = pd.read_parquet(os.path.join(tmp, "props_rows.parquet"))
    F = F[F.fallback == 0].reset_index(drop=True)
    # opponent factors for the target games (research/nba_props_simple_test.opponent_factors computes them only for games in the box):
    # opponent's season-to-date allowed per 100 possessions vs the league's season-to-date rate, shrunk to last season (prior 10 games)
    pbt = _pb(pbx, d)
    pbt["poss"] = pbt.game_id.map(PS.game_poss())
    tg = pbt.groupby(["game_id", "season", "team", "opp"]).agg(pts=("pts", "sum"), reb=("reb", "sum"), ast=("ast", "sum"),
                                                                  poss=("poss", "first")).reset_index().dropna(subset=["poss"])
    cur, prv = tg[tg.season == SEASON], tg[tg.season == SEASON - 1]
    for i in F.index[F.game_id.isin(tgt_ids)]:
        o = F.at[i, "opp"]
        for st in C.STATS:
            lg = cur[st].sum() / cur.poss.sum() if len(cur) else prv[st].sum() / prv.poss.sum()
            X = cur[cur.opp == o]
            raw = (X[st].sum() / X.poss.sum()) / lg if len(X) else 1.0
            Xp = prv[prv.opp == o]
            last = (Xp[st].sum() / Xp.poss.sum()) / (prv[st].sum() / prv.poss.sum()) if len(Xp) else 1.0
            F.at[i, f"opp_{st}"] = (len(X) * raw + 10 * last) / (len(X) + 10)
    TT.E.load_games = lambda: G[["gid", "date", "home", "away", "m_L"]]
    F = TT.features(F)
    # short-night share over the player's last 20 appearances before the target game (the definition the pi model was fitted on:
    # appearance rows in the research). research/nba_minutes_tail_test.features carries the value forward to non-appearance rows,
    # which omits the latest appearance; target rows are recomputed here.
    A = F[F.app].sort_values("tip")
    for i in F.index[F.game_id.isin(tgt_ids)]:
        prior = A[(A.aid == F.at[i, "aid"]) & (A.tip < F.at[i, "tip"])].tail(20)
        F.at[i, "s_sum"] = float(prior.short.sum())
        F.at[i, "s_cnt"] = float(len(prior))
    os.makedirs(os.path.join(args.archive, "nba", "props_forward"), exist_ok=True)
    if os.environ.get("NBA_PROPS_DUMP"):
        F[F.game_id.isin(tgt_ids)].to_csv(os.environ["NBA_PROPS_DUMP"], index=False)
    written = []
    names = dict(zip(pb.athlete_id, pb.athlete_display_name))
    for gid, h, cut in T:
        Z = F[F.game_id == gid].reset_index(drop=True)
        rec = dict(game_id=gid, horizon_min=h, cutoff_utc=cut.isoformat(), generated_utc=pd.Timestamp.now(tz="UTC").isoformat(),
                   run_utc=now.isoformat(), valid_window=bool(cut - pd.Timedelta(minutes=WINDOW_MIN) <= now <= cut), code_commit=commit,
                   params_sha256=phash, schedule_sha256=sched_hash, report=log.get("report"), box=log.get("box"),
                   method="research/NBA_MINUTES_M2B_RULE.md forward-test protocol; v2 = M2 minutes, v3 = M2b minutes; pts reported only",
                   players=[])
        if len(Z) == 0:
            rec["error"] = "no candidate rows"
        else:
            tag = "1" if h == 60 else "6"
            Zt = Z.copy()
            if tag == "6":
                for a, b in (("st1", "st6"), ("mu1", "mu6"), ("sd1", "sd6"), ("pa1", "pa6"), ("emin_app1", "emin_app6"), ("vac_same1", "vac_same6"),
                             ("vac_other1", "vac_other6"), ("V_now1_pts", "V_now6_pts"), ("V_now1_reb", "V_now6_reb"), ("V_now1_ast", "V_now6_ast")):
                    Zt[a] = Z[b]
            pa = np.clip(Zt.pa1.to_numpy(), 1e-3, 1 - 1e-3)
            q1 = M.disc_normal(Zt.mu1.to_numpy(), Zt.sd1.to_numpy())
            q2, pi2 = C.q_m2(Zt, params[SEASON]["m2"], False)
            q3, pi3 = C.q_m2(Zt, params[SEASON]["m2"], True)
            dists = {}
            for st in C.STATS:
                rate, rr = C.prop_rate(Zt, st, params[SEASON]["props"])
                for vn, q in (("v2", q2), ("v3", q3)):
                    cond = PS.mixture_pmf(rate, q, rr, SUP[st])
                    unc = pa[:, None] * cond
                    unc[:, 0] += 1 - pa
                    dists[(vn, st)] = unc
            for i, row in Zt.iterrows():
                rec["players"].append(dict(
                    aid=int(row.aid), name=names.get(int(row.aid), ""), team=row.team, status=row.st1, p_appear=round(float(pa[i]), 6),
                    stage1_mu=round(float(row.mu1), 4), stage1_sd=round(float(row.sd1), 4),
                    risk_group_v2=bool(q2[i, :14].sum() >= 0.2), p_under15_stage1=round(float(q1[i, :14].sum()), 6),
                    minutes_v2=[round(float(x), 6) for x in q2[i]], minutes_v3=[round(float(x), 6) for x in q3[i]],
                    pi_short=round(float(pi2[i]), 6),
                    **{f"{st}_{vn}": [round(float(x), 7) for x in dists[(vn, st)][i]] for vn in ("v2", "v3") for st in C.STATS}))
        day = pd.Timestamp(cut).tz_convert("America/New_York").strftime("%Y-%m-%d")
        out = os.path.join(args.archive, "nba", "props_forward", "tests" if args.force_game else day)
        os.makedirs(out, exist_ok=True)
        fn = os.path.join(out, f"{gid}_{h}_{now.strftime('%Y%m%dT%H%MZ')}.json.gz")
        with gzip.open(fn, "wt") as fh:
            json.dump(rec, fh)
        written.append(fn)
    log["written"] = [os.path.relpath(w, args.archive) for w in written]
    return log


def _prep_reports(R):
    """report time from its label 'YYYY-MM-DD HH_MM(AM|PM)' (US Eastern); same fields as research/nba_minutes_test.load_reports."""
    R = R.copy()
    if "team_code" not in R:
        R["team_code"] = None
    lab = R.report.astype(str)
    hm = lab.str[11:].str.replace("PM", "").str.replace("AM", "").str.split("_")
    hour = hm.str[0].astype(int)
    pm = lab.str.endswith("PM")
    hour = np.where(pm & (hour != 12), hour + 12, np.where(~pm & (hour == 12), 0, hour))
    minute = hm.str[1].fillna("0").astype(int)
    R["rtime"] = (pd.to_datetime(lab.str[:10]) + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m")).dt.tz_localize(
        "America/New_York").dt.tz_convert("UTC")
    R["pkey"] = R.player.map(M.player_key)
    return R.drop_duplicates(["game_date", "team", "player", "report"])


def _pb(P, d):
    """player box in the form research/nba_props_simple_test.player_box returns (2025-2027 only)."""
    x = P[pd.to_numeric(P.season_type, errors="coerce") == 2].copy()
    for c in ("minutes", "points", "rebounds", "assists"):
        x[c] = pd.to_numeric(x[c], errors="coerce").fillna(0.0)
    x["athlete_id"] = pd.to_numeric(x.athlete_id, errors="coerce")
    x = x.dropna(subset=["athlete_id"])
    x["aid"] = x.athlete_id.astype(int)
    x["game_id"] = pd.to_numeric(x.game_id, errors="coerce").astype(int)
    x["season"] = pd.to_numeric(x.season, errors="coerce").astype(int)
    x["tip"] = pd.to_datetime(x.game_date_time, utc=True, errors="coerce", format="ISO8601")
    x = x.rename(columns={"points": "pts", "rebounds": "reb", "assists": "ast", "team_abbreviation": "team", "opponent_team_abbreviation": "opp"})
    x["grp"] = x.athlete_position_abbreviation.map(M.GROUP).fillna("W")
    return x


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--now")
    ap.add_argument("--force-game")
    ap.add_argument("--horizon", default="60")
    a = ap.parse_args()
    t0 = pd.Timestamp.now(tz="UTC")
    try:
        lg = run(a)
    except Exception:  # noqa: BLE001
        lg = {"run_utc": t0.isoformat(), "error": traceback.format_exc()[-3000:]}
        print(lg["error"])
    lg["seconds"] = (pd.Timestamp.now(tz="UTC") - t0).total_seconds()
    runs = os.path.join(a.archive, "nba", "props_forward", "runs")
    os.makedirs(runs, exist_ok=True)
    if lg.get("targets") or lg.get("error"):
        with open(os.path.join(runs, t0.strftime("%Y%m%dT%H%M%SZ") + ".json"), "w") as fh:
            json.dump(lg, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in lg.items() if k in ("targets", "written", "error", "seconds", "box", "report")}, default=str)[:3000])
