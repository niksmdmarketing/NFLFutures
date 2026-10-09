"""Stat pages. Ranked team tables carry every season from 2018 so the site can show year-to-year change.

Table page JSON: {"title", "intro", "columns": [...], "seasons": [...], "season": current,
                  "data": {"2026": [rows], "2025": [rows], ...}}
Column spec: key, label, fmt ("pct" | "num1" | "num2" | "num3" | "int" | "text"), dir ("high" | "low" | None = no
ranking color), group (optional header group), note (hover text). Ranks and shading are computed in the browser.
Completed seasons come from history/ (built by history.py); only the current season is computed on each run.
"""
import glob
import json
import os

import numpy as np

from common import FIX, NAMES, ROOT, TEAMS, scrimmage, write_json
import history  # noqa: E402
import team_season


def col(key, label, fmt="num2", dir="high", group=None, note=None):
    c = {"key": key, "label": label, "fmt": fmt, "dir": dir}
    if group:
        c["group"] = group
    if note:
        c["note"] = note
    return c


def _eff(d):
    lo = "low" if d == "high" else "high"
    return [col("games", "G", "int", None), col("ppg", "Points/G", "num1", d), col("epa", "EPA/play", "num3", d),
            col("succ", "Success", "pct", d), col("pass_epa", "Dropback EPA", "num3", d), col("rush_epa", "Rush EPA", "num3", d),
            col("early_epa", "Early-down EPA", "num3", d), col("early_succ", "Early-down success", "pct", d),
            col("expl", "Explosive plays", "pct", d), col("third", "3rd-down conv.", "pct", d), col("rz_td", "Red-zone TD", "pct", d),
            col("to_pg", "Turnovers/G", "num2", lo), col("sack_rate", "Sack rate", "pct", lo),
            col("press", "Pressure rate", "pct", lo), col("plays_pg", "Plays/G", "num1", None)]


NGS = "NFL Next Gen Stats tracking via nflverse; published for 2018–2025 so far, blank for this season until it is released"
SPECS = {
    "offense": {"title": "Offensive stats", "intro": "Per-play efficiency for every offense. EPA is expected points added; success means the play gained enough to stay on schedule. Explosive plays are passes of 15+ yards or runs of 10+. Pressure rate is pressures allowed per dropback.",
                "columns": _eff("high")},
    "defense": {"title": "Defensive stats", "intro": "The same measures, allowed by each defense. Lower EPA and success allowed is better. Pressure rate is pressures generated per opponent dropback; turnovers and sack rate are what the defense forced.",
                "columns": _eff("low")},
    "proe": {"title": "Pass rate over expected", "intro": "How often each team drops back to pass compared with what an average team would do in the same down, distance, field position, score and time. Positive means pass-happier than expected. Neutral situations are the first three quarters with neither team a heavy favorite.",
             "columns": [col("proe_neutral", "PROE (neutral)", "pct", None), col("proe_early_neutral", "PROE early downs", "pct", None),
                         col("proe_all", "PROE (all)", "pct", None), col("rate_neutral", "Pass rate (neutral)", "pct", None),
                         col("rate_all", "Pass rate (all)", "pct", None)]},
    "off_tendencies": {"title": "Offensive tendencies", "intro": "How each offense likes to play. Motion, play-action, screens, RPOs and QB out of pocket are FTN charting (2022 onward); shotgun, no-huddle and depth of target come from play-by-play. Play-action, screens and out of pocket are shares of dropbacks; the rest are shares of all plays.",
                       "columns": [col("motion", "Motion", "pct", None, note="Pre-snap motion, share of all plays (FTN, 2022+)"),
                                   col("play_action", "Play-action", "pct", None, note="Share of dropbacks (FTN, 2022+)"),
                                   col("adot", "Avg depth of target", "num1", None), col("shotgun", "Shotgun", "pct", None),
                                   col("no_huddle", "No-huddle", "pct", None), col("early_pass", "Early-down pass rate", "pct", None),
                                   col("screen", "Screens", "pct", None, note="Share of dropbacks (FTN, 2022+)"),
                                   col("rpo", "RPO", "pct", None, note="Share of all plays (FTN, 2022+)"),
                                   col("deep", "Deep throws (20+)", "pct", None),
                                   col("out_of_pocket", "QB out of pocket", "pct", None, note="Share of dropbacks (FTN, 2022+)")]},
    "def_tendencies": {"title": "Defensive tendencies", "intro": "How each defense plays: how often it blitzes, how many it rushes, how many it puts in the box against the run, and what it lets opponents do. Blitz and box counts are FTN charting (2022 onward); pressures from Pro Football Reference via nflverse.",
                       "columns": [col("blitz", "Blitz rate", "pct", None), col("rushers", "Avg pass rushers", "num2", None),
                                   col("box_run", "Avg box vs run", "num2", None), col("stacked", "8+ in box vs run", "pct", None),
                                   col("press", "Pressure rate", "pct", "high"), col("opp_adot", "Opp. depth of target", "num1", "low"),
                                   col("opp_early_pass", "Opp. early-down pass rate", "pct", None)]},
    "oline": {"title": "Offensive line stats", "intro": "Pass protection and run blocking. Pressure rate allowed is pressures per dropback from Pro Football Reference. No-blitz pressure rate counts only dropbacks where the defense rushed four or fewer, so it isolates the line from blitz pickup; it and time to throw come from " + NGS + ". Yards before contact is per running-back carry.",
              "columns": [col("press", "Pressure rate allowed", "pct", "low"),
                          col("nb_press", "No-blitz pressure", "pct", "low", note="Pressured on dropbacks vs 4 or fewer rushers (NGS, 2018–2025)"),
                          col("ttt", "Time to throw", "num2", None, note="Seconds from snap to throw (NGS, 2018–2025)"),
                          col("sack", "Sack rate allowed", "pct", "low"), col("hit", "QB hit rate allowed", "pct", "low"),
                          col("ybc", "YBC / RB rush", "num2", "high", note="Yards before contact per running-back carry (PFR)"),
                          col("stuff", "Run stuff rate", "pct", "low", note="Designed runs for no gain or a loss"),
                          col("rush_succ", "Rush success", "pct", "high"), col("expl_run", "10+ yard runs", "pct", "high")]},
    "dline": {"title": "Defensive line stats", "intro": "Pass rush and run defense up front. Pressure rate is pressures per opponent dropback from Pro Football Reference. No-blitz pressure rate counts only dropbacks where the defense rushed four or fewer, so it measures the front without help from blitzes; it comes from " + NGS + ". Yards before contact allowed is per running-back carry; stuffs are designed runs stopped for no gain or a loss.",
              "columns": [col("press", "Pressure rate", "pct", "high"),
                          col("nb_press", "No-blitz pressure rate", "pct", "high", note="Pressure on dropbacks with 4 or fewer rushers (NGS, 2018–2025)"),
                          col("ybc", "YBC allowed / RB rush", "num2", "low", note="Yards before contact allowed per running-back carry (PFR)"),
                          col("stuff", "Run stuff rate", "pct", "high"), col("sack", "Sack rate", "pct", "high"),
                          col("hits", "QB hit rate", "pct", "high"), col("pressures_pg", "Pressures/G", "num1", "high"),
                          col("rush_succ", "Opp. rush success", "pct", "low")]},
    "coverage": {"title": "Coverage by position", "intro": "What each defense allows when the ball is thrown at its cornerbacks, safeties and linebackers: targets, completion rate, yards per target and passer rating allowed. Charted coverage responsibility from Pro Football Reference via nflverse.",
                 "columns": [c for g, lab in (("CB", "Cornerbacks"), ("S", "Safeties"), ("LB", "Linebackers"))
                             for c in (col(f"{g}_tgt", "Targets", "int", None, lab), col(f"{g}_cmp", "Comp. %", "pct", "low", lab),
                                       col(f"{g}_ypt", "Yds/target", "num1", "low", lab), col(f"{g}_rate", "Rating allowed", "num1", "low", lab))]},
}


def rows_from(values, page):
    vals = values.get(page, {})
    return [{"team": t, "name": NAMES[t], **{k: v for k, v in vals.get(t, {}).items()}} for t in TEAMS]


def load_history():
    out, cubes = {}, {}
    for p in sorted(glob.glob(os.path.join(ROOT, "history", "*.json"))):
        name = os.path.basename(p)[:-5]
        d = json.load(open(p))
        if name.startswith("pace_"):
            cubes[int(name[5:])] = d
        else:
            out[int(name)] = d["values"]
    return out, cubes


def build_all(season, games, pbp, ratings, injuries):
    g = games[(games.season == season) & (games.game_type == "REG")]
    s = scrimmage(pbp)
    pages = {}

    # ---------- Season tables with history ----------
    hist, cubes = load_history()
    missing = [y for y in range(history.FIRST, season) if y not in hist]
    for y in missing:  # e.g. the season that just finished: build once, the workflow commits it
        history.build(y, games)
    if missing:
        hist, cubes = load_history()
    hist = {y: v for y, v in hist.items() if y < season}
    cubes = {y: c for y, c in cubes.items() if y < season}
    cur = history.values_json(team_season.season_values(season, games, pbp, current=True)) if len(s) else {}
    allv = {**hist, season: cur} if cur else dict(hist)
    seasons = sorted(allv)
    for page, spec in SPECS.items():
        pages[page] = {**spec, "seasons": seasons, "season": seasons[-1],
                       "data": {str(y): rows_from(allv[y], page) for y in seasons}}

    # ---------- Pace (clock used): one cube per season, filtered in the browser ----------
    cube = team_season.pace_cube(season, games, pbp) if len(s) else None
    if cube:
        cubes[season] = cube
    for y, c in cubes.items():
        write_json(f"pace_{y}.json", c)
    pages["pace"] = {"title": "Team pace", "seasons": sorted(cubes), "season": max(cubes) if cubes else season}

    # ---------- Strength of schedule ----------
    R = ratings.rating
    sos = []
    for t in TEAMS:
        mine = g[(g.home_team == t) | (g.away_team == t)]
        opp = np.where(mine.home_team == t, mine.away_team, mine.home_team)
        done = mine.result.notna().values
        r_opp = np.array([R.get(o, 0.0) for o in opp])
        sos.append({"team": t, "name": NAMES[t], "rating": float(R[t]),
                    "sos_played": float(r_opp[done].mean()) if done.any() else None,
                    "sos_remaining": float(r_opp[~done].mean()) if (~done).any() else None,
                    "sos_full": float(r_opp.mean()), "remaining": int((~done).sum()),
                    "next": ", ".join(f"{'@' if h != t else ''}{o}" for h, o in zip(mine.home_team[~done][:4], opp[~done][:4]))})
    pages["sos"] = {"title": "Strength of schedule", "intro": "Average strength of each team's opponents, using the model's current team ratings (points better or worse than an average team). Higher means a harder schedule; shading and ranks treat an easier schedule as better for the team (rank 1 = easiest). Remaining schedule matters most for futures.",
                    "columns": [col("rating", "Team rating", "num1", "high"), col("sos_played", "Played SOS", "num2", "low"),
                                col("sos_remaining", "Remaining SOS", "num2", "low"), col("sos_full", "Full-season SOS", "num2", "low"),
                                col("remaining", "Games left", "int", None), col("next", "Next four", "text", None)],
                    "seasons": [season], "season": season, "data": {str(season): sos}}

    # ---------- Box scores ----------
    box = []
    for _, r in g[g.result.notna()].sort_values(["week", "gameday"]).iterrows():
        gs = s[s.game_id == r.game_id]
        if gs.empty:
            continue
        teams = []
        for t, opp, pts in ((r.away_team, r.home_team, r.away_score), (r.home_team, r.away_team, r.home_score)):
            o = gs[gs.posteam == t]
            t3 = o[o.down == 3]
            conv = int(t3.third_down_converted.fillna(0).sum()); att3 = conv + int(t3.third_down_failed.fillna(0).sum())
            dr_ = o.groupby("fixed_drive").agg(minyd=("yardline_100", "min"), res=("fixed_drive_result", "first"))
            rz = dr_[dr_.minyd <= 20]
            teams.append({"team": t, "pts": int(pts), "plays": int(len(o)), "yards": int(o.yards_gained.sum()),
                          "epa": round(float(o.epa.mean()), 3) if len(o) else None,
                          "succ": round(float(o.success.mean()), 3) if len(o) else None,
                          "pass_epa": round(float(o[o.db == 1].epa.mean()), 3) if (o.db == 1).any() else None,
                          "rush_epa": round(float(o[o.dr == 1].epa.mean()), 3) if (o.dr == 1).any() else None,
                          "expl": int(o.expl.sum()), "early_succ": round(float(o[o.down.isin([1, 2])].success.mean()), 3) if len(o) else None,
                          "third": f"{conv}/{att3}", "rz": f"{int((rz.res == 'Touchdown').sum())}/{len(rz)}",
                          "to": int(o.interception.sum() + o.fumble_lost.sum()), "sacks": int(o.sack.sum())})
        box.append({"week": int(r.week), "date": r.gameday, "teams": teams})
    pages["boxscores"] = {"title": "Advanced box scores", "games": box}

    # ---------- Injuries ----------
    inj_rows = []
    if injuries is not None and not injuries.empty:
        wk = int(injuries.week.max())
        cur = injuries[(injuries.week == wk) & injuries.report_status.isin(["Out", "Doubtful", "Questionable"])].copy()
        cur["team"] = cur.team.replace(FIX)
        order = {"Out": 0, "Doubtful": 1, "Questionable": 2}
        cur = cur.sort_values(["team", "report_status"], key=lambda c: c.map(order) if c.name == "report_status" else c)
        for _, r in cur.iterrows():
            inj_rows.append({"team": r.team, "player": r.full_name, "pos": r.position, "status": r.report_status,
                             "injury": r.report_primary_injury if isinstance(r.report_primary_injury, str) else "",
                             "practice": r.practice_status if isinstance(r.practice_status, str) else ""})
        inj_week = wk
    else:
        inj_week = None
    qbs = [{"team": t, "starter": ratings.loc[t, "qb_expected"], "status": ratings.loc[t, "qb_expected_status"],
            "season_qb": ratings.loc[t, "qb_ref"], "adj": round(float(ratings.loc[t, "qb_adj"]), 2),
            "note": ratings.loc[t, "qb_note"]} for t in TEAMS]
    pages["injuries"] = {"title": "Injury report", "week": inj_week, "rows": inj_rows, "qbs": qbs}
    return pages
