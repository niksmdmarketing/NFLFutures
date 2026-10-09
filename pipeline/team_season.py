"""Team stat tables for one season, plus the clock-used cube for the pace page.

season_values(season, games, pbp) -> {page: DataFrame indexed by team}. The pages' titles, intros and columns
live in stats.SPECS; this module only computes numbers so completed seasons can be stored in history/ and
reused without downloading their play-by-play again.

Sources by season: play-by-play 2018+, Pro Football Reference advanced stats 2018+, FTN charting 2022+,
NFL participation (true pressure, pass rushers, time to throw) 2018 to the latest season nflverse has published.
"""
import numpy as np
import pandas as pd

from common import FIX, TEAMS, TIX, download, scrimmage

PART_COLS = ["nflverse_game_id", "play_id", "was_pressure", "number_of_pass_rushers", "time_to_throw"]


def _read(rel, season, current):
    p = download(rel, required=False, max_age_h=2.0 if current else 24 * 365)
    return pd.read_csv(p, low_memory=False) if p else None


def pfr(season, kind, current):
    d = _read(f"pfr_advstats/advstats_week_{kind}_{season}.csv", season, current)
    if d is None or d.empty:
        return pd.DataFrame()
    for c in ("team", "opponent"):
        if c in d:
            d[c] = d[c].replace(FIX)
    if "game_type" in d:
        d = d[d.game_type == "REG"]
    return d


def ftn(season, current):
    f = _read(f"ftn_charting/ftn_charting_{season}.csv", season, current)
    if f is None:
        return None
    f = f.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
    for c in f.columns:
        if c.startswith("is_"):
            f[c] = f[c].astype(str).str.upper().eq("TRUE").astype(float)
    keep = ["game_id", "play_id", "is_no_huddle", "is_motion", "is_play_action", "is_screen_pass", "is_rpo",
            "is_qb_out_of_pocket", "n_blitzers", "n_pass_rushers", "n_defense_box"]
    return f[[c for c in keep if c in f.columns]].drop_duplicates(["game_id", "play_id"])


def participation(season, current):
    p = _read(f"pbp_participation/pbp_participation_{season}.csv", season, current)
    if p is None:
        return None
    p = p[[c for c in PART_COLS if c in p.columns]].rename(columns={"nflverse_game_id": "game_id"})
    if "was_pressure" in p:
        p["was_pressure"] = p.was_pressure.map({True: 1.0, False: 0.0, "TRUE": 1.0, "FALSE": 0.0, "True": 1.0, "False": 0.0, 1: 1.0, 0: 0.0})
    return p.drop_duplicates(["game_id", "play_id"])


def rb_ids(season, current, pp):
    """PFR ids of running backs (roster position RB/FB); unknown ids count unless they threw passes."""
    r = _read(f"rosters/roster_{season}.csv", season, current)
    pos = {}
    if r is not None and "pfr_id" in r:
        pos = dict(zip(r.pfr_id.dropna(), r.loc[r.pfr_id.notna(), "position"]))
    passers = set(pp.pfr_player_id) if len(pp) else set()
    return lambda pid: pos.get(pid) in ("RB", "FB") if pid in pos else pid not in passers


def per(num, den):
    num, den = np.asarray(num, float), np.asarray(den, float)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def team_games(g):
    rows = []
    for _, r in g[g.result.notna()].iterrows():
        rows.append({"team": r.home_team, "pf": r.home_score, "pa": r.away_score, "week": r.week})
        rows.append({"team": r.away_team, "pf": r.away_score, "pa": r.home_score, "week": r.week})
    return pd.DataFrame(rows, columns=["team", "pf", "pa", "week"])


def side_stats(s, side, gp):
    by = s.groupby(side)
    db, dr = s[s.db == 1].groupby(side), s[s.dr == 1].groupby(side)
    early = s[s.down.isin([1, 2])].groupby(side)
    t3 = s[s.down == 3]
    t3 = t3.assign(conv=t3.third_down_converted.fillna(0), fail=t3.third_down_failed.fillna(0)).groupby(side)
    drives = s.groupby(["game_id", "fixed_drive", side]).agg(minyd=("yardline_100", "min"), res=("fixed_drive_result", "first")).reset_index()
    rz = drives[drives.minyd <= 20].groupby(side).agg(trips=("res", "size"), tds=("res", lambda x: (x == "Touchdown").sum()))
    out = pd.DataFrame(index=TEAMS)
    out["games"] = gp
    out["plays_pg"] = by.size().reindex(TEAMS) / gp
    out["epa"] = by.epa.mean().reindex(TEAMS)
    out["succ"] = by.success.mean().reindex(TEAMS)
    out["pass_epa"] = db.epa.mean().reindex(TEAMS)
    out["rush_epa"] = dr.epa.mean().reindex(TEAMS)
    out["early_epa"] = early.epa.mean().reindex(TEAMS)
    out["early_succ"] = early.success.mean().reindex(TEAMS)
    out["expl"] = by.expl.mean().reindex(TEAMS)
    c3, f3 = t3.conv.sum().reindex(TEAMS), t3.fail.sum().reindex(TEAMS)
    out["third"] = c3 / (c3 + f3)
    out["rz_td"] = (rz.tds / rz.trips).reindex(TEAMS)
    out["to_pg"] = (by.interception.sum() + by.fumble_lost.sum()).reindex(TEAMS) / gp
    out["sack_rate"] = db.sack.mean().reindex(TEAMS)
    return out


def season_values(season, games, pbp, current=False):
    g = games[(games.season == season) & (games.game_type == "REG")]
    tg = team_games(g)
    gp = tg.groupby("team").size().reindex(TEAMS)
    s = scrimmage(pbp)
    f = ftn(season, current)
    sf = s.merge(f, on=["game_id", "play_id"], how="left") if f is not None else None
    part = participation(season, current)
    sp = s.merge(part, on=["game_id", "play_id"], how="left") if part is not None else None
    pp, pr, pdf = pfr(season, "pass", current), pfr(season, "rush", current), pfr(season, "def", current)
    V = {}
    nan = pd.Series(np.nan, index=TEAMS)
    dbo = s[s.db == 1].groupby("posteam").size().reindex(TEAMS)
    dbd = s[s.db == 1].groupby("defteam").size().reindex(TEAMS)

    # ---- offense / defense ----
    off, dfn = side_stats(s, "posteam", gp), side_stats(s, "defteam", gp)
    press_allowed = pp.groupby("team").times_pressured.sum().reindex(TEAMS) / dbo if len(pp) else nan
    press_gen = pdf.groupby("team").def_pressures.sum().reindex(TEAMS) / dbd if len(pdf) else nan
    V["offense"] = off.assign(ppg=tg.groupby("team").pf.mean().reindex(TEAMS), press=press_allowed)
    V["defense"] = dfn.assign(ppg=tg.groupby("team").pa.mean().reindex(TEAMS), press=press_gen)

    # ---- pass rate over expected ----
    x = s[s.xpass.notna()].copy()
    x["neutral"] = (x.qtr <= 3) & x.wp.between(0.2, 0.8)
    pr_ = pd.DataFrame(index=TEAMS)
    for name, sub in (("all", x), ("neutral", x[x.neutral]), ("early_neutral", x[x.neutral & x.down.isin([1, 2])])):
        gb = sub.groupby("posteam")
        pr_[f"rate_{name}"] = gb["db"].mean().reindex(TEAMS)
        pr_[f"proe_{name}"] = (gb["db"].mean() - gb.xpass.mean()).reindex(TEAMS)
    V["proe"] = pr_

    # ---- offensive tendencies ----
    ot = pd.DataFrame(index=TEAMS)
    ot["shotgun"] = s.groupby("posteam").shotgun.mean().reindex(TEAMS)
    ot["no_huddle"] = s.groupby("posteam").no_huddle.mean().reindex(TEAMS)
    att = s[(s.db == 1) & s.air_yards.notna()]
    ot["adot"] = att.groupby("posteam").air_yards.mean().reindex(TEAMS)
    ot["deep"] = att.assign(d=(att.air_yards >= 20).astype(float)).groupby("posteam").d.mean().reindex(TEAMS)
    ot["early_pass"] = s[s.down.isin([1, 2])].groupby("posteam").db.mean().reindex(TEAMS)
    for c in ("play_action", "screen", "out_of_pocket", "motion", "rpo"):
        ot[c] = np.nan
    if sf is not None and "is_play_action" in sf and sf.is_play_action.notna().any():
        dbf = sf[(sf.db == 1) & sf.is_play_action.notna()]
        ok = sf[sf.is_motion.notna()]
        ot["play_action"] = dbf.groupby("posteam").is_play_action.mean().reindex(TEAMS)
        ot["screen"] = dbf.groupby("posteam").is_screen_pass.mean().reindex(TEAMS)
        ot["out_of_pocket"] = dbf.groupby("posteam").is_qb_out_of_pocket.mean().reindex(TEAMS)
        ot["motion"] = ok.groupby("posteam").is_motion.mean().reindex(TEAMS)
        ot["rpo"] = ok.groupby("posteam").is_rpo.mean().reindex(TEAMS)
    V["off_tendencies"] = ot

    # ---- defensive tendencies ----
    dt_ = pd.DataFrame(index=TEAMS, columns=["blitz", "rushers", "box_run", "stacked"], dtype=float)
    if sf is not None and "n_blitzers" in sf and sf.n_blitzers.notna().any():
        dbf = sf[(sf.db == 1) & sf.n_blitzers.notna()]
        dt_["blitz"] = dbf.assign(b=(dbf.n_blitzers > 0).astype(float)).groupby("defteam").b.mean().reindex(TEAMS)
        dt_["rushers"] = dbf[dbf.n_pass_rushers > 0].groupby("defteam").n_pass_rushers.mean().reindex(TEAMS)
        drf = sf[(sf.dr == 1) & (sf.n_defense_box > 0)]
        dt_["box_run"] = drf.groupby("defteam").n_defense_box.mean().reindex(TEAMS)
        dt_["stacked"] = drf.assign(st=(drf.n_defense_box >= 8).astype(float)).groupby("defteam").st.mean().reindex(TEAMS)
    dt_["press"] = press_gen
    dt_["opp_adot"] = att.groupby("defteam").air_yards.mean().reindex(TEAMS)
    dt_["opp_early_pass"] = s[s.down.isin([1, 2])].groupby("defteam").db.mean().reindex(TEAMS)
    V["def_tendencies"] = dt_

    # ---- shared line inputs ----
    is_rb = rb_ids(season, current, pp)
    ybc_for = ybc_against = nan
    if len(pr):
        r = pr[pr.pfr_player_id.map(is_rb)].copy()
        for c in ("carries", "rushing_yards_before_contact"):
            r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0)
        a = r.groupby("team")[["rushing_yards_before_contact", "carries"]].sum().reindex(TEAMS)
        ybc_for = pd.Series(per(a.rushing_yards_before_contact, a.carries), index=TEAMS)
        if "opponent" in r:
            b = r.groupby("opponent")[["rushing_yards_before_contact", "carries"]].sum().reindex(TEAMS)
            ybc_against = pd.Series(per(b.rushing_yards_before_contact, b.carries), index=TEAMS)
    runs = s[s.dr == 1].assign(stuff=lambda d: (d.yards_gained <= 0).astype(float), big=lambda d: (d.yards_gained >= 10).astype(float))
    nb_for = nb_against = ttt = nan
    if sp is not None and "was_pressure" in sp:
        d = sp[(sp.db == 1) & sp.was_pressure.notna() & (sp.number_of_pass_rushers > 0)]
        if len(d) > 500:
            nb = d[d.number_of_pass_rushers <= 4]
            nb_for = nb.groupby("posteam").was_pressure.mean().reindex(TEAMS)
            nb_against = nb.groupby("defteam").was_pressure.mean().reindex(TEAMS)
        t = sp[(sp.db == 1) & (pd.to_numeric(sp.get("time_to_throw"), errors="coerce") > 0)]
        if len(t) > 500:
            ttt = t.assign(tt=pd.to_numeric(t.time_to_throw, errors="coerce")).groupby("posteam").tt.mean().reindex(TEAMS)

    # ---- offensive line ----
    ol = pd.DataFrame(index=TEAMS)
    ol["press"] = press_allowed
    ol["nb_press"] = nb_for
    ol["ttt"] = ttt
    ol["sack"] = off.sack_rate
    ol["hit"] = s[s.db == 1].groupby("posteam").qb_hit.mean().reindex(TEAMS)
    ol["ybc"] = ybc_for
    ol["stuff"] = runs.groupby("posteam").stuff.mean().reindex(TEAMS)
    ol["rush_succ"] = runs.groupby("posteam").success.mean().reindex(TEAMS)
    ol["expl_run"] = runs.groupby("posteam").big.mean().reindex(TEAMS)
    V["oline"] = ol

    # ---- defensive line ----
    dl = pd.DataFrame(index=TEAMS)
    dl["press"] = press_gen
    dl["nb_press"] = nb_against
    dl["ybc"] = ybc_against
    dl["stuff"] = runs.groupby("defteam").stuff.mean().reindex(TEAMS)
    dl["sack"] = dfn.sack_rate
    dl["hits"] = s[s.db == 1].groupby("defteam").qb_hit.mean().reindex(TEAMS)
    dl["pressures_pg"] = pdf.groupby("team").def_pressures.sum().reindex(TEAMS) / gp if len(pdf) else nan
    dl["rush_succ"] = runs.groupby("defteam").success.mean().reindex(TEAMS)
    V["dline"] = dl

    # ---- coverage by position group ----
    cov = pd.DataFrame(index=TEAMS)
    if len(pdf):
        r = _read(f"rosters/roster_{season}.csv", season, current)
        posmap = dict(zip(r.pfr_id, r.position)) if r is not None and "pfr_id" in r else {}
        grp = {"CB": "CB", "S": "S", "FS": "S", "SS": "S", "DB": "S", "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB"}
        d = pdf.copy()
        d["grp"] = d.pfr_player_id.map(posmap).map(grp)
        d = d[d.grp.notna()]
        cs = ["def_targets", "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed", "def_ints"]
        for c in cs:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
        a = d.groupby(["team", "grp"])[cs].sum()
        for gname in ("CB", "S", "LB"):
            sub = a.xs(gname, level="grp").reindex(TEAMS) if gname in a.index.get_level_values("grp") else pd.DataFrame(index=TEAMS, columns=cs, dtype=float)
            att_ = sub.def_targets
            cov[f"{gname}_tgt"] = att_
            cov[f"{gname}_cmp"] = per(sub.def_completions_allowed, att_)
            cov[f"{gname}_ypt"] = per(sub.def_yards_allowed, att_)
            ca = np.clip((per(sub.def_completions_allowed, att_) - 0.3) * 5, 0, 2.375)
            cb = np.clip((per(sub.def_yards_allowed, att_) - 3) * 0.25, 0, 2.375)
            cc = np.clip(per(sub.def_receiving_td_allowed, att_) * 20, 0, 2.375)
            cd = np.clip(2.375 - per(sub.def_ints, att_) * 25, 0, 2.375)
            cov[f"{gname}_rate"] = (ca + cb + cc + cd) / 6 * 100
    V["coverage"] = cov
    return V


# ---------------- clock used ----------------
CUBE_KEYS = ["t", "w", "h", "q", "d", "nh", "neu"]


def pace_cube(season, games, pbp):
    """Plays aggregated by team, week, home/away, quarter, down, no-huddle and neutral situation.

    Clock used = seconds between the end of the previous play (whistle) and this snap, when the previous play was
    a run or pass by the same offense on the same drive with no penalty, timeout or other stoppage between them
    and the gap fits the 40-second play clock.
    """
    d = pbp.copy()
    if "end_clock_time" not in d or d.end_clock_time.isna().all():  # whistle times exist from 2022
        return None
    d = d.sort_values(["game_id", "play_id"])
    snap = pd.to_datetime(d.time_of_day, errors="coerce", utc=True, format="ISO8601")
    end = pd.to_datetime(d.end_clock_time, errors="coerce", utc=True, format="ISO8601")
    prev_end = end.groupby(d.game_id).shift(1)
    same = lambda c: d[c].eq(d.groupby("game_id")[c].shift(1))  # noqa: E731
    prev = d.groupby("game_id")
    prev_ok = prev.play_type.shift(1).isin(["run", "pass"]) & prev.penalty.shift(1).fillna(0).eq(0)
    if "timeout" in d:
        prev_ok &= prev.timeout.shift(1).fillna(0).eq(0)
    gap = (snap - prev_end).dt.total_seconds()
    d["gap"] = np.where(prev_ok & same("posteam") & same("fixed_drive") & same("qtr") & gap.between(1.0, 40.5), gap, np.nan)
    s = scrimmage(d)
    s = s[s.posteam.isin(TIX)]
    if s.empty:
        return None
    home = s.posteam.eq(s.home_team)
    neu = ((s.qtr <= 3) & s.wp.between(0.2, 0.8)).astype(int)
    k = pd.DataFrame({"t": s.posteam.map(TIX), "w": s.week.astype(int), "h": home.astype(int), "q": s.qtr.clip(upper=5).astype(int),
                      "d": s.down.fillna(0).astype(int), "nh": s.no_huddle.fillna(0).astype(int), "neu": neu,
                      "n": 1, "p": s.db.astype(int), "g": s.gap.notna().astype(int), "s": (s.gap.fillna(0) * 10).round().astype(int)})
    a = k.groupby(CUBE_KEYS, as_index=False)[["n", "p", "g", "s"]].sum()
    return {"season": int(season), "teams": TEAMS, "cols": {c: a[c].astype(int).tolist() for c in a.columns}}
