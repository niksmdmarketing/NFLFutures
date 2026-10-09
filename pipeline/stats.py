"""Team stats pages. Each page = {"title", "intro", "columns": [...], "rows": [...]} rendered by the site's table.

Column spec: key, label, fmt ("pct" | "num1" | "num2" | "num3" | "int" | "text"), dir ("high" | "low" | None = no
ranking color), group (optional header group). Ranking colors are computed in the browser.
"""
import numpy as np
import pandas as pd

from common import FIX, NAMES, TEAMS, TIX, download, scrimmage


def col(key, label, fmt="num2", dir="high", group=None, note=None):
    c = {"key": key, "label": label, "fmt": fmt, "dir": dir}
    if group:
        c["group"] = group
    if note:
        c["note"] = note
    return c


def ftn(season, pbp):
    p = download(f"ftn_charting/ftn_charting_{season}.csv", required=False)
    if not p:
        return None
    f = pd.read_csv(p, low_memory=False)
    f = f.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
    for c in f.columns:
        if c.startswith("is_"):
            f[c] = f[c].astype(str).str.upper().eq("TRUE").astype(float)
    keep = ["game_id", "play_id", "is_no_huddle", "is_motion", "is_play_action", "is_screen_pass", "is_rpo",
            "is_qb_out_of_pocket", "n_blitzers", "n_pass_rushers", "n_defense_box"]
    return pbp.merge(f[[c for c in keep if c in f.columns]], on=["game_id", "play_id"], how="left")


def pfr(season, kind):
    p = download(f"pfr_advstats/advstats_week_{kind}_{season}.csv", required=False)
    if not p:
        return pd.DataFrame()
    d = pd.read_csv(p, low_memory=False)
    d["team"] = d.team.replace(FIX)
    if "game_type" in d:
        d = d[d.game_type == "REG"]
    return d


def team_games(g):
    rows = []
    for _, r in g[g.result.notna()].iterrows():
        rows.append({"team": r.home_team, "pf": r.home_score, "pa": r.away_score, "opp": r.away_team, "week": r.week})
        rows.append({"team": r.away_team, "pf": r.away_score, "pa": r.home_score, "opp": r.home_team, "week": r.week})
    return pd.DataFrame(rows)


def per(num, den):
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)


def side_stats(s, side, tg):
    """Efficiency for offense (side='posteam') or allowed by defense (side='defteam')."""
    by = s.groupby(side)
    db, dr = s[s.db == 1].groupby(side), s[s.dr == 1].groupby(side)
    early = s[s.down.isin([1, 2])].groupby(side)
    t3 = s[(s.down == 3)]
    t3 = t3.assign(conv=t3.third_down_converted.fillna(0), fail=t3.third_down_failed.fillna(0)).groupby(side)
    drives = s.groupby(["game_id", "fixed_drive", side]).agg(minyd=("yardline_100", "min"),
                                                           res=("fixed_drive_result", "first")).reset_index()
    rz = drives[drives.minyd <= 20].groupby(side).agg(trips=("res", "size"), tds=("res", lambda x: (x == "Touchdown").sum()))
    out = pd.DataFrame(index=TEAMS)
    gp = tg.groupby("team").size().reindex(TEAMS)
    out["games"] = gp
    out["plays_pg"] = by.size().reindex(TEAMS) / gp
    out["epa"] = by.epa.mean().reindex(TEAMS)
    out["succ"] = by.success.mean().reindex(TEAMS)
    out["pass_epa"] = db.epa.mean().reindex(TEAMS)
    out["rush_epa"] = dr.epa.mean().reindex(TEAMS)
    out["early_epa"] = early.epa.mean().reindex(TEAMS)
    out["early_succ"] = early.success.mean().reindex(TEAMS)
    out["expl"] = by.expl.mean().reindex(TEAMS)
    c3 = t3.conv.sum().reindex(TEAMS); f3 = t3.fail.sum().reindex(TEAMS)
    out["third"] = c3 / (c3 + f3)
    out["rz_td"] = (rz.tds / rz.trips).reindex(TEAMS)
    out["to_pg"] = (by.interception.sum() + by.fumble_lost.sum()).reindex(TEAMS) / gp
    out["sack_rate"] = db.sack.mean().reindex(TEAMS)
    return out


def build_all(season, games, pbp, ratings, injuries):
    g = games[(games.season == season) & (games.game_type == "REG")]
    tg = team_games(g)
    s = scrimmage(pbp)
    s = s.merge(pbp[["game_id", "play_id"]].drop_duplicates(), on=["game_id", "play_id"], how="left")
    sf = ftn(season, s)
    pp, pr, pdf = pfr(season, "pass"), pfr(season, "rush"), pfr(season, "def")
    pages = {}

    # ---------- Offense / Defense ----------
    off = side_stats(s, "posteam", tg)
    dfn = side_stats(s, "defteam", tg)
    pf = tg.groupby("team").pf.mean().reindex(TEAMS); pa = tg.groupby("team").pa.mean().reindex(TEAMS)
    dbo = s[s.db == 1].groupby("posteam").size().reindex(TEAMS); dbd = s[s.db == 1].groupby("defteam").size().reindex(TEAMS)
    press_allowed = pp.groupby("team").times_pressured.sum().reindex(TEAMS) / dbo if len(pp) else pd.Series(np.nan, TEAMS)
    press_gen = pdf.groupby("team").def_pressures.sum().reindex(TEAMS) / dbd if len(pdf) else pd.Series(np.nan, TEAMS)

    def rows(df, extra):
        out = []
        for t in TEAMS:
            r = {"team": t, "name": NAMES[t]}
            r.update({k: (None if pd.isna(v) else float(v)) for k, v in df.loc[t].items()})
            r.update({k: (None if pd.isna(v[t]) else float(v[t])) for k, v in extra.items()})
            out.append(r)
        return out

    eff_cols = lambda d: [  # noqa: E731
        col("games", "G", "int", None), col("ppg", "Points/G", "num1", d), col("epa", "EPA/play", "num3", d),
        col("succ", "Success", "pct", d), col("pass_epa", "Dropback EPA", "num3", d), col("rush_epa", "Rush EPA", "num3", d),
        col("early_epa", "Early-down EPA", "num3", d), col("early_succ", "Early-down success", "pct", d),
        col("expl", "Explosive plays", "pct", d), col("third", "3rd-down conv.", "pct", d), col("rz_td", "Red-zone TD", "pct", d),
        col("to_pg", "Turnovers/G", "num2", "low" if d == "high" else "high"),
        col("sack_rate", "Sack rate", "pct", "low" if d == "high" else "high"),
        col("press", "Pressure rate", "pct", "low" if d == "high" else "high"), col("plays_pg", "Plays/G", "num1", None)]
    pages["offense"] = {"title": "Offensive stats", "intro": "Per-play efficiency for every offense this season. EPA is expected points added; success means the play gained enough to stay on schedule. Explosive plays are passes of 15+ yards or runs of 10+. Pressure rate is pressures allowed per dropback.",
                        "columns": eff_cols("high"), "rows": rows(off, {"ppg": pf, "press": press_allowed})}
    pages["defense"] = {"title": "Defensive stats", "intro": "The same measures, allowed by each defense. Lower EPA and success allowed is better. Pressure rate is pressures generated per opponent dropback; turnovers and sack rate are what the defense forced.",
                        "columns": eff_cols("low"), "rows": rows(dfn, {"ppg": pa, "press": press_gen})}

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
                    "rows": sos}

    # ---------- Pace ----------
    sp = s.sort_values(["game_id", "play_id"]).copy()
    sp["dt"] = sp.groupby(["game_id", "fixed_drive"]).game_seconds_remaining.shift(1) - sp.game_seconds_remaining
    sp = sp[(sp.dt > 0) & (sp.dt <= 60)]
    neutral = sp[(sp.qtr <= 3) & (sp.wp.between(0.2, 0.8))]
    pace = pd.DataFrame(index=TEAMS)
    pace["plays_pg"] = off.plays_pg
    pace["sec_play"] = sp.groupby("posteam").dt.mean().reindex(TEAMS)
    pace["sec_play_neutral"] = neutral.groupby("posteam").dt.mean().reindex(TEAMS)
    pace["no_huddle"] = s.groupby("posteam").no_huddle.mean().reindex(TEAMS)
    pace["opp_plays_pg"] = dfn.plays_pg
    pages["pace"] = {"title": "Team pace", "intro": "How fast each offense plays. Seconds per play is the time between snaps within a drive; neutral situations are the first three quarters with neither team a heavy favorite to win, which removes hurry-up and clock-killing.",
                     "columns": [col("sec_play_neutral", "Sec/play (neutral)", "num1", "low"), col("sec_play", "Sec/play (all)", "num1", "low"),
                                 col("plays_pg", "Plays/G", "num1", "high"), col("no_huddle", "No-huddle", "pct", "high"),
                                 col("opp_plays_pg", "Opponent plays/G", "num1", None)],
                     "rows": rows(pace, {})}

    # ---------- Pass rate over expected ----------
    x = s[s.xpass.notna()].copy()
    x["neutral"] = (x.qtr <= 3) & x.wp.between(0.2, 0.8)
    pr_ = pd.DataFrame(index=TEAMS)
    for name, sub in (("all", x), ("neutral", x[x.neutral]), ("early_neutral", x[x.neutral & x.down.isin([1, 2])])):
        gb = sub.groupby("posteam")
        pr_[f"rate_{name}"] = gb["db"].mean().reindex(TEAMS)
        pr_[f"proe_{name}"] = (gb["db"].mean() - gb.xpass.mean()).reindex(TEAMS)
    pages["proe"] = {"title": "Pass rate over expected", "intro": "How often each team drops back to pass compared with what an average team would do in the same down, distance, field position, score and time. Positive means pass-happier than expected. Neutral situations remove garbage time and late-game clock management.",
                     "columns": [col("proe_neutral", "PROE (neutral)", "pct", None), col("proe_early_neutral", "PROE early downs", "pct", None),
                                 col("proe_all", "PROE (all)", "pct", None), col("rate_neutral", "Pass rate (neutral)", "pct", None),
                                 col("rate_all", "Pass rate (all)", "pct", None)],
                     "rows": rows(pr_, {})}

    # ---------- Offensive tendencies ----------
    ot = pd.DataFrame(index=TEAMS)
    ot["shotgun"] = s.groupby("posteam").shotgun.mean().reindex(TEAMS)
    att = s[(s.db == 1) & s.air_yards.notna()]
    ot["adot"] = att.groupby("posteam").air_yards.mean().reindex(TEAMS)
    ot["deep"] = att.assign(d=(att.air_yards >= 20).astype(float)).groupby("posteam").d.mean().reindex(TEAMS)
    if sf is not None and "is_play_action" in sf:
        dbf = sf[sf.db == 1]
        ot["play_action"] = dbf.groupby("posteam").is_play_action.mean().reindex(TEAMS)
        ot["screen"] = dbf.groupby("posteam").is_screen_pass.mean().reindex(TEAMS)
        ot["out_of_pocket"] = dbf.groupby("posteam").is_qb_out_of_pocket.mean().reindex(TEAMS)
        ot["motion"] = sf.groupby("posteam").is_motion.mean().reindex(TEAMS)
        ot["rpo"] = sf.groupby("posteam").is_rpo.mean().reindex(TEAMS)
    ot["early_pass"] = s[s.down.isin([1, 2])].groupby("posteam").db.mean().reindex(TEAMS)
    pages["off_tendencies"] = {"title": "Offensive tendencies", "intro": "How each offense likes to play: formation, play-action, motion, screens, RPOs and how far downfield it throws. Shares of dropbacks unless noted. Charting data from FTN via nflverse.",
                               "columns": [col("early_pass", "Early-down pass rate", "pct", None), col("shotgun", "Shotgun (all plays)", "pct", None),
                                           col("play_action", "Play-action", "pct", None), col("motion", "Motion (all plays)", "pct", None),
                                           col("screen", "Screens", "pct", None), col("rpo", "RPO (all plays)", "pct", None),
                                           col("adot", "Avg depth of target", "num1", None), col("deep", "Deep throws (20+)", "pct", None),
                                           col("out_of_pocket", "QB out of pocket", "pct", None)],
                               "rows": rows(ot, {})}

    # ---------- Defensive tendencies ----------
    dt_ = pd.DataFrame(index=TEAMS)
    if sf is not None and "n_blitzers" in sf:
        dbf = sf[sf.db == 1]
        dt_["blitz"] = dbf.assign(b=(dbf.n_blitzers > 0).astype(float)).groupby("defteam").b.mean().reindex(TEAMS)
        dt_["rushers"] = dbf[dbf.n_pass_rushers > 0].groupby("defteam").n_pass_rushers.mean().reindex(TEAMS)
        drf = sf[(sf.dr == 1) & (sf.n_defense_box > 0)]
        dt_["box_run"] = drf.groupby("defteam").n_defense_box.mean().reindex(TEAMS)
        dt_["stacked"] = drf.assign(st=(drf.n_defense_box >= 8).astype(float)).groupby("defteam").st.mean().reindex(TEAMS)
    dt_["press"] = press_gen
    att_d = s[(s.db == 1) & s.air_yards.notna()]
    dt_["opp_adot"] = att_d.groupby("defteam").air_yards.mean().reindex(TEAMS)
    dt_["opp_early_pass"] = s[s.down.isin([1, 2])].groupby("defteam").db.mean().reindex(TEAMS)
    pages["def_tendencies"] = {"title": "Defensive tendencies", "intro": "How each defense plays: how often it blitzes, how many it rushes, how many it puts in the box against the run, and what it lets opponents do. Charting data from FTN; pressures from Pro Football Reference via nflverse.",
                               "columns": [col("blitz", "Blitz rate", "pct", None), col("rushers", "Avg pass rushers", "num2", None),
                                           col("box_run", "Avg box vs run", "num2", None), col("stacked", "8+ in box vs run", "pct", None),
                                           col("press", "Pressure rate", "pct", "high"), col("opp_adot", "Opp. depth of target", "num1", "low"),
                                           col("opp_early_pass", "Opp. early-down pass rate", "pct", None)],
                               "rows": rows(dt_, {})}

    # ---------- Offensive line ----------
    ol = pd.DataFrame(index=TEAMS)
    ol["press"] = press_allowed
    ol["sack"] = off.sack_rate
    ol["hit"] = s[s.db == 1].groupby("posteam").qb_hit.mean().reindex(TEAMS)
    if len(pr):
        rb = pr.groupby("team")[["rushing_yards_before_contact", "carries"]].sum().reindex(TEAMS)
        ol["ybc"] = rb.rushing_yards_before_contact / rb.carries
    runs = s[s.dr == 1]
    ol["stuff"] = runs.assign(x=(runs.yards_gained <= 0).astype(float)).groupby("posteam").x.mean().reindex(TEAMS)
    ol["rush_succ"] = runs.groupby("posteam").success.mean().reindex(TEAMS)
    ol["expl_run"] = runs.assign(x=(runs.yards_gained >= 10).astype(float)).groupby("posteam").x.mean().reindex(TEAMS)
    pages["oline"] = {"title": "Offensive line stats", "intro": "Pass protection and run blocking. Pressure rate is pressures allowed per dropback (Pro Football Reference via nflverse). Yards before contact per carry is the best public measure of run blocking; stuffs are designed runs for no gain or a loss.",
                      "columns": [col("press", "Pressure rate allowed", "pct", "low"), col("sack", "Sack rate allowed", "pct", "low"),
                                  col("hit", "QB hit rate allowed", "pct", "low"), col("ybc", "Yards before contact", "num2", "high"),
                                  col("stuff", "Run stuff rate", "pct", "low"), col("rush_succ", "Rush success", "pct", "high"),
                                  col("expl_run", "10+ yard runs", "pct", "high")],
                      "rows": rows(ol, {})}

    # ---------- Defensive line / pass rush ----------
    dl = pd.DataFrame(index=TEAMS)
    if len(pdf):
        agg = pdf.groupby("team")[["def_pressures", "def_times_hurried", "def_times_hitqb", "def_times_blitzed"]].sum().reindex(TEAMS)
        gp = tg.groupby("team").size().reindex(TEAMS)
        dl["pressures_pg"] = agg.def_pressures / gp
        dl["press"] = agg.def_pressures / dbd
        dl["hurry"] = agg.def_times_hurried / dbd
        dl["hits"] = agg.def_times_hitqb / dbd
        dl["blitz_pfr"] = agg.def_times_blitzed / dbd
    dl["sack"] = dfn.sack_rate
    runs_d = s[s.dr == 1]
    dl["stuff"] = runs_d.assign(x=(runs_d.yards_gained <= 0).astype(float)).groupby("defteam").x.mean().reindex(TEAMS)
    dl["rush_succ"] = runs_d.groupby("defteam").success.mean().reindex(TEAMS)
    pages["dline"] = {"title": "Defensive line stats", "intro": "Pass rush and run defense up front. Pressures, hurries and QB hits per opponent dropback come from Pro Football Reference via nflverse; stuffs are opponent designed runs stopped for no gain or a loss.",
                      "columns": [col("press", "Pressure rate", "pct", "high"), col("pressures_pg", "Pressures/G", "num1", "high"),
                                  col("sack", "Sack rate", "pct", "high"), col("hurry", "Hurry rate", "pct", "high"),
                                  col("hits", "QB hit rate", "pct", "high"), col("blitz_pfr", "Blitz rate", "pct", None),
                                  col("stuff", "Run stuff rate", "pct", "high"), col("rush_succ", "Opp. rush success", "pct", "low")],
                      "rows": rows(dl, {})}

    # ---------- Coverage by position group ----------
    cov_rows, cov_cols = [], []
    if len(pdf):
        rp = download(f"rosters/roster_{season}.csv", required=False)
        posmap = {}
        if rp:
            ro = pd.read_csv(rp, low_memory=False)
            if "pfr_id" in ro:
                posmap = dict(zip(ro.pfr_id, ro.position))
        grp = {"CB": "CB", "S": "S", "FS": "S", "SS": "S", "DB": "S", "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB"}
        d = pdf.copy()
        d["grp"] = d.pfr_player_id.map(posmap).map(grp)
        d = d[d.grp.notna()]
        for c in ("def_targets", "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed", "def_ints"):
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
        a = d.groupby(["team", "grp"])[["def_targets", "def_completions_allowed", "def_yards_allowed",
                                        "def_receiving_td_allowed", "def_ints"]].sum()

        def rating(att, cmp_, yds, td, ints):
            if att <= 0:
                return None
            a_ = min(max((cmp_ / att - 0.3) * 5, 0), 2.375); b_ = min(max((yds / att - 3) * 0.25, 0), 2.375)
            c_ = min(max(td / att * 20, 0), 2.375); d_ = min(max(2.375 - ints / att * 25, 0), 2.375)
            return (a_ + b_ + c_ + d_) / 6 * 100

        for t in TEAMS:
            r = {"team": t, "name": NAMES[t]}
            for gname in ("CB", "S", "LB"):
                if (t, gname) in a.index:
                    v = a.loc[(t, gname)]
                    tg_ = v.def_targets
                    r[f"{gname}_tgt"] = float(tg_)
                    r[f"{gname}_ypt"] = float(v.def_yards_allowed / tg_) if tg_ else None
                    r[f"{gname}_cmp"] = float(v.def_completions_allowed / tg_) if tg_ else None
                    r[f"{gname}_rate"] = rating(tg_, v.def_completions_allowed, v.def_yards_allowed, v.def_receiving_td_allowed, v.def_ints)
            cov_rows.append(r)
        for gname, label in (("CB", "Cornerbacks"), ("S", "Safeties"), ("LB", "Linebackers")):
            cov_cols += [col(f"{gname}_tgt", "Targets", "int", None, label), col(f"{gname}_cmp", "Comp. %", "pct", "low", label),
                         col(f"{gname}_ypt", "Yds/target", "num1", "low", label), col(f"{gname}_rate", "Rating allowed", "num1", "low", label)]
    pages["coverage"] = {"title": "Coverage by position", "intro": "What each defense allows when the ball is thrown at its cornerbacks, safeties and linebackers: targets, completion rate, yards per target and passer rating allowed. Charted coverage responsibility from Pro Football Reference via nflverse.",
                         "columns": cov_cols, "rows": cov_rows}

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
