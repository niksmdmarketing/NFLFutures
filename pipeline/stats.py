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
    "oline": {"title": "Offensive line stats", "intro": "Pass protection and run blocking. Pressure rate allowed is pressures per dropback from Pro Football Reference. No-blitz pressure rate counts only dropbacks where the defense rushed four or fewer, so it isolates the line from blitz pickup; it comes from " + NGS + ". Time to throw, rush yards over expected (RYOE) and 8+ box rate are NFL Next Gen Stats weekly tracking, current season included. Yards before contact is per running-back carry.",
              "columns": [col("press", "Pressure rate allowed", "pct", "low"),
                          col("nb_press", "No-blitz pressure", "pct", "low", note="Pressured on dropbacks vs 4 or fewer rushers (NGS, 2018–2025)"),
                          col("ttt", "Time to throw", "num2", None, note="Seconds from snap to throw (NGS weekly tracking)"),
                          col("sack", "Sack rate allowed", "pct", "low"), col("hit", "QB hit rate allowed", "pct", "low"),
                          col("ybc", "YBC / RB rush", "num2", "high", note="Yards before contact per running-back carry (PFR)"),
                          col("stuff", "Run stuff rate", "pct", "low", note="Designed runs for no gain or a loss"),
                          col("ryoe", "RYOE / RB carry", "num2", "high", note="Rush yards over expected per RB carry (NGS)"),
                          col("rush_succ", "Rush success", "pct", "high"), col("expl_run", "10+ yard runs", "pct", "high"),
                          col("box8", "8+ box faced", "pct", None, note="Share of RB carries against 8+ defenders (NGS)")]},
    "dline": {"title": "Defensive line stats", "intro": "Pass rush and run defense up front. Pressure rate is pressures per opponent dropback from Pro Football Reference. No-blitz pressure rate counts only dropbacks where the defense rushed four or fewer, so it measures the front without help from blitzes; it comes from " + NGS + ". Rush yards over expected and 8+ box rate are Next Gen Stats weekly tracking. Yards before contact allowed is per running-back carry; stuffs are designed runs stopped for no gain or a loss.",
              "columns": [col("press", "Pressure rate", "pct", "high"),
                          col("nb_press", "No-blitz pressure rate", "pct", "high", note="Pressure on dropbacks with 4 or fewer rushers (NGS, 2018–2025)"),
                          col("ybc", "YBC allowed / RB rush", "num2", "low", note="Yards before contact allowed per running-back carry (PFR)"),
                          col("stuff", "Run stuff rate", "pct", "high"), col("sack", "Sack rate", "pct", "high"),
                          col("hits", "QB hit rate", "pct", "high"), col("pressures_pg", "Pressures/G", "num1", "high"),
                          col("ryoe", "RYOE allowed / RB carry", "num2", "low", note="Rush yards over expected allowed per RB carry (NGS)"),
                          col("rush_succ", "Opp. rush success", "pct", "low"),
                          col("box8", "8+ box rate", "pct", None, note="Share of opponent RB carries with 8+ in the box (NGS)")]},
    "passing": {"title": "Passing", "intro": "How each team throws the ball and how it defends the pass. ANY/A is adjusted net yards per attempt (touchdowns +20, interceptions −45, sacks count). CPOE, time to throw, aggressiveness (throws into tight windows), intended air yards, air yards to the sticks, receiver separation, cushion and YAC over expected come from NFL Next Gen Stats tracking; bad throws and drops from Pro Football Reference.",
                "columns": [*(c for d, lab in (("high", "Offense"), ("low", "Defense")) for c in (
                    col(f"{'off' if lab == 'Offense' else 'def'}_epa", "EPA/dropback", "num3", d, lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_succ", "Success", "pct", d, lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_anya", "ANY/A", "num2", d, lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_cmp", "Comp. %", "pct", d, lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_cpoe", "CPOE", "pct", d, lab, "Completion % over expected (NGS), weighted by attempts"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_td", "TD rate", "pct", d, lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_int", "INT rate", "pct", "low" if d == "high" else "high", lab),
                    col(f"{'off' if lab == 'Offense' else 'def'}_expl", "20+ yd passes", "pct", d, lab, "Share of dropbacks gaining 20+ yards"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_iay", "Intended air yds", "num1", None, lab, "Average depth of throws (NGS)"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_sticks", "Air yds to sticks", "num1", None, lab, "Average throw depth past (or short of) the first-down marker (NGS)"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_aggr", "Aggressiveness", "pct", None, lab, "Share of throws into tight windows (NGS)"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_sep", "Separation", "num2", d, lab, "Yards between receiver and nearest defender at the catch or incompletion (NGS)"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_cushion", "Cushion", "num2", None, lab, "Yards between receiver and defender at the snap (NGS)"),
                    col(f"{'off' if lab == 'Offense' else 'def'}_yacoe", "YAC over expected", "num2", d, lab, "Yards after catch above expectation per reception (NGS)"))),
                    col("off_ttt", "Time to throw", "num2", None, "Offense", "Seconds from snap to throw (NGS)"),
                    col("off_bad", "Bad-throw %", "pct", "low", "Offense", "Pro Football Reference charting"),
                    col("off_drop", "Drop %", "pct", "low", "Offense", "Drops per attempt, Pro Football Reference charting")]},
    "rushing": {"title": "Rushing", "intro": "How each team runs the ball and how it stops the run. Designed runs only (no scrambles or kneels). Rush yards over expected, efficiency (yards travelled per rushing yard; lower is more north-south), time to the line and 8+ box rate come from NFL Next Gen Stats running-back tracking; yards before and after contact and broken tackles are Pro Football Reference charting of running-back carries.",
                "columns": [*(c for d, lab, pre in (("high", "Offense", "off"), ("low", "Defense", "def")) for c in (
                    col(f"{pre}_epa", "EPA/run", "num3", d, lab), col(f"{pre}_succ", "Success", "pct", d, lab),
                    col(f"{pre}_ypc", "Yards/carry", "num2", d, lab),
                    col(f"{pre}_ryoe", "RYOE/carry", "num2", d, lab, "Rush yards over expected per RB carry (NGS)"),
                    col(f"{pre}_ybc", "YBC/carry", "num2", d, lab, "Yards before contact per RB carry (PFR)"),
                    col(f"{pre}_yac", "YAC/carry", "num2", d, lab, "Yards after contact per RB carry (PFR)"),
                    col(f"{pre}_btk", "Broken tackles /100", "num1", d, lab, "Broken tackles per 100 RB carries (PFR)"),
                    col(f"{pre}_expl", "10+ yd runs", "pct", d, lab),
                    col(f"{pre}_stuff", "Stuffed", "pct", "low" if d == "high" else "high", lab, "Runs for no gain or a loss"),
                    col(f"{pre}_box8", "8+ in box", "pct", None, lab, "Share of RB carries against 8+ defenders (NGS)"),
                    col(f"{pre}_eff", "NGS efficiency", "num2", None, lab, "Distance travelled per rushing yard (NGS); lower is more north-south"))),
                    col("off_ttl", "Time to line", "num2", None, "Offense", "Seconds for the RB to reach the line of scrimmage (NGS)")]},
    "drives": {"title": "Drives", "intro": "Results per possession. Points per drive counts touchdowns with the try that followed, plus field goals. Three-and-outs are drives of three plays or fewer ending in a punt. Starting position is measured from the team's own goal line, so higher is better field position. End-of-half kneel drives are left out.",
               "columns": [*(c for d, lab, pre in (("high", "Offense", "off"), ("low", "Defense", "def")) for c in (
                   col(f"{pre}_pts", "Points/drive", "num2", d, lab), col(f"{pre}_td", "TD rate", "pct", d, lab),
                   col(f"{pre}_three_out", "Three-and-out", "pct", "low" if d == "high" else "high", lab),
                   col(f"{pre}_punt", "Punt rate", "pct", "low" if d == "high" else "high", lab),
                   col(f"{pre}_to", "Turnover rate", "pct", "low" if d == "high" else "high", lab),
                   col(f"{pre}_start", "Avg start (own yd)", "num1", d, lab),
                   col(f"{pre}_yds", "Yards/drive", "num1", d, lab), col(f"{pre}_plays", "Plays/drive", "num2", None, lab),
                   col(f"{pre}_sec", "Seconds/drive", "num1", None, lab), col(f"{pre}_n_pg", "Drives/G", "num1", None, lab)))]},
    "situational": {"title": "Situational", "intro": "Third down by distance (short 1–3 yards, medium 4–6, long 7+), fourth-down conversion, go-for-it rate on 4th-and-2 or shorter between the 30s, red-zone and goal-to-go touchdown rates per drive, and turnover margin per game.",
                    "columns": [*(c for d, lab, pre in (("high", "Offense", "off"), ("low", "Defense", "def")) for c in (
                        col(f"{pre}_3rd", "3rd-down conv.", "pct", d, lab), col(f"{pre}_3rd_short", "3rd & 1–3", "pct", d, lab),
                        col(f"{pre}_3rd_med", "3rd & 4–6", "pct", d, lab), col(f"{pre}_3rd_long", "3rd & 7+", "pct", d, lab),
                        col(f"{pre}_4th", "4th-down conv.", "pct", d, lab), col(f"{pre}_rz_td", "Red-zone TD", "pct", d, lab),
                        col(f"{pre}_gtg_td", "Goal-to-go TD", "pct", d, lab))),
                        col("off_go_short", "Go rate 4th & ≤2", "pct", None, "Coaching", "Share of 4th-and-2-or-shorter between the 30s where the offense went for it"),
                        col("to_margin_pg", "Turnover margin/G", "num2", "high", "Coaching")]},
    "special_teams": {"title": "Special teams", "intro": "Kicking, punting and returns. Net punt subtracts return yards and 20 yards for a touchback. Special-teams EPA per game is the expected points a team gained on kicks, punts and returns minus what opponents gained.",
                      "columns": [col("st_epa_pg", "ST EPA/G", "num2", "high"), col("fg", "FG %", "pct", "high"), col("fg40", "FG 40–49", "pct", "high"),
                                  col("fg50", "FG 50+", "pct", "high"), col("fga_pg", "FG att/G", "num1", None), col("xp", "XP %", "pct", "high"),
                                  col("punt_net", "Net punt", "num1", "high"), col("punt_in20", "Punts inside 20", "pct", "high"),
                                  col("ko_tb", "Kickoff touchbacks", "pct", None), col("kr", "Kick return avg", "num1", "high"),
                                  col("kr_allowed", "Kick return allowed", "num1", "low"), col("punt_ret", "Punt return avg", "num1", "high"),
                                  col("punt_ret_allowed", "Punt return allowed", "num1", "low")]},
    "discipline": {"title": "Discipline", "intro": "Accepted penalties against each team per game, split by offense and defense, pre-snap penalties (false starts, offside, delay of game and similar), defensive pass interference, penalties drawn from opponents, and missed tackles from Pro Football Reference charting.",
                   "columns": [col("pen_pg", "Penalties/G", "num1", "low"), col("pen_yds_pg", "Penalty yds/G", "num1", "low"),
                               col("off_pen_pg", "On offense/G", "num1", "low"), col("def_pen_pg", "On defense/G", "num1", "low"),
                               col("presnap_pg", "Pre-snap/G", "num1", "low"), col("fpd_pg", "DPI/G", "num2", "low"),
                               col("drawn_pg", "Drawn/G", "num1", "high"), col("missed_pg", "Missed tackles/G", "num1", "low"),
                               col("missed_rate", "Missed tackle rate", "pct", "low", note="Missed tackles / (missed + made), PFR")]},
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
