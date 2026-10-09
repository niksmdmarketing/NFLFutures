"""More team stats: passing, rushing, drives, situational, special teams, discipline, plus Next Gen Stats.

extra_values(season, games, pbp, s, pfr_tables, current) -> {page: DataFrame indexed by team, columns named
"off_*" / "def_*" for pages that show offense and defense side by side}, and NGS columns for O-line / D-line.

Sources: NFL play-by-play (nflverse), NFL Next Gen Stats weekly player tracking (nflverse, 2016+),
Pro Football Reference advanced stats (2018+).
"""
import numpy as np
import pandas as pd

from common import FIX, TEAMS, TIX, download

NAN = pd.Series(np.nan, index=TEAMS)
PRESNAP = {"False Start", "Delay of Game", "Encroachment", "Neutral Zone Infraction", "Defensive Offside",
           "Offensive Offside", "Illegal Formation", "Illegal Shift", "Illegal Motion", "Defensive Delay of Game"}


def per(num, den):
    num = pd.Series(num, index=TEAMS, dtype=float) if not isinstance(num, pd.Series) else num.reindex(TEAMS).astype(float)
    den = pd.Series(den, index=TEAMS, dtype=float) if not isinstance(den, pd.Series) else den.reindex(TEAMS).astype(float)
    return num / den.where(den > 0)


def wmean(df, by, val, w):
    d = df[[by, val, w]].dropna()
    d = d[d[w] > 0]
    if d.empty:
        return NAN.copy()
    g = d.assign(x=d[val] * d[w]).groupby(by)
    return (g.x.sum() / g[w].sum()).reindex(TEAMS)


def ngs(kind, season, current):
    p = download(f"nextgen_stats/ngs_{kind}.csv.gz", max_age_h=2.0 if current else 24.0 * 30)
    if not p:
        return pd.DataFrame()
    d = pd.read_csv(p, low_memory=False)
    d = d[(d.season == season) & (d.season_type == "REG") & (d.week > 0) & d.team_abbr.notna()].copy()
    d["team"] = d.team_abbr.replace(FIX)
    return d[d.team.isin(TIX)]


def opponents(games, season):
    g = games[(games.season == season) & (games.game_type == "REG")]
    a = pd.DataFrame({"week": g.week, "team": g.home_team, "opp": g.away_team})
    b = pd.DataFrame({"week": g.week, "team": g.away_team, "opp": g.home_team})
    return pd.concat([a, b]).drop_duplicates(["week", "team"])


def with_opp(d, opp):
    return d.merge(opp, on=["week", "team"], how="left")


def drives(pbp, side):
    """Per-drive summary for offense (side='posteam') or defense (side='defteam')."""
    d = pbp[pbp.posteam.isin(TIX) & pbp.defteam.isin(TIX) & pbp.fixed_drive.notna()].copy()
    d = d.sort_values(["game_id", "play_id"])
    sc = d[d.play_type.isin(["run", "pass"]) & (d.qb_kneel != 1)]
    first = sc.groupby(["game_id", "fixed_drive"]).agg(posteam=("posteam", "first"), defteam=("defteam", "first"),
                                                        start=("yardline_100", "first"), plays=("play_id", "size"),
                                                        yds=("yards_gained", "sum"), res=("fixed_drive_result", "first"),
                                                        top=("drive_time_of_possession", "first"))
    sc_all = d.groupby(["game_id", "fixed_drive"]).agg(s0=("posteam_score", "first"), s1=("posteam_score_post", "max"))
    dr = first.join(sc_all, how="left")
    dr["pts"] = (dr.s1 - dr.s0).clip(lower=0, upper=8).fillna(0)
    dr["td"] = (dr.res == "Touchdown").astype(float)
    dr["punt"] = (dr.res == "Punt").astype(float)
    dr["to"] = dr.res.isin(["Turnover", "Opp touchdown"]).astype(float)
    dr["three_out"] = ((dr.plays <= 3) & (dr.res == "Punt")).astype(float)
    dr["own_start"] = 100 - dr.start
    t = dr.top.astype(str).str.split(":", expand=True)
    dr["sec"] = pd.to_numeric(t[0], errors="coerce") * 60 + pd.to_numeric(t[1], errors="coerce") if t.shape[1] > 1 else np.nan
    dr = dr[~dr.res.isin(["End of half", "End of game"]) | (dr.plays > 3)]
    g = dr.groupby(side)
    return pd.DataFrame({"pts": g.pts.mean(), "td": g.td.mean(), "three_out": g.three_out.mean(), "punt": g.punt.mean(),
                         "to": g.to.mean(), "start": g.own_start.mean(), "yds": g.yds.mean(), "plays": g.plays.mean(),
                         "sec": g.sec.mean(), "n": g.size()}).reindex(TEAMS)


def extra_values(season, games, pbp, s, pp, pr, pdf, gp, current, is_rb):
    V = {}
    opp = opponents(games, season)
    qb = with_opp(ngs("passing", season, current), opp)
    ru = with_opp(ngs("rushing", season, current), opp)
    rc = with_opp(ngs("receiving", season, current), opp)
    if len(ru):
        ru = ru[ru.player_position.isin(["RB", "FB", "HB"])]

    # ---------------- passing ----------------
    P = pd.DataFrame(index=TEAMS)
    dbk = s[s.db == 1]
    att = s[s.pass_attempt == 1]
    for side, pre in (("posteam", "off"), ("defteam", "def")):
        a = att.groupby(side); d = dbk.groupby(side)
        pyds = att[att.sack != 1].groupby(side).yards_gained.sum().reindex(TEAMS)
        syds = dbk[dbk.sack == 1].groupby(side).yards_gained.sum().reindex(TEAMS).fillna(0)
        td = att.groupby(side).pass_touchdown.sum().reindex(TEAMS)
        ints = att.groupby(side).interception.sum().reindex(TEAMS)
        natt = att[att.sack != 1].groupby(side).size().reindex(TEAMS)
        nsack = dbk.groupby(side).sack.sum().reindex(TEAMS)
        P[f"{pre}_anya"] = per(pyds + 20 * td - 45 * ints + syds, natt + nsack)
        P[f"{pre}_cmp"] = per(att[att.sack != 1].groupby(side).complete_pass.sum(), natt)
        P[f"{pre}_int"] = per(ints, natt)
        P[f"{pre}_td"] = per(td, natt)
        P[f"{pre}_expl"] = per(dbk[(dbk["pass"] == 1) & (dbk.yards_gained >= 20)].groupby(side).size(), d.size())
        P[f"{pre}_epa"] = d.epa.mean().reindex(TEAMS)
        P[f"{pre}_succ"] = d.success.mean().reindex(TEAMS)
        key = "team" if pre == "off" else "opp"
        P[f"{pre}_cpoe"] = wmean(qb, key, "completion_percentage_above_expectation", "attempts") / 100 if len(qb) else NAN
        P[f"{pre}_iay"] = wmean(qb, key, "avg_intended_air_yards", "attempts") if len(qb) else NAN
        P[f"{pre}_sticks"] = wmean(qb, key, "avg_air_yards_to_sticks", "attempts") if len(qb) else NAN
        P[f"{pre}_yacoe"] = wmean(rc, key, "avg_yac_above_expectation", "receptions") if len(rc) else NAN
        P[f"{pre}_sep"] = wmean(rc, key, "avg_separation", "targets") if len(rc) else NAN
        P[f"{pre}_cushion"] = wmean(rc, key, "avg_cushion", "targets") if len(rc) else NAN
    P["off_ttt"] = wmean(qb, "team", "avg_time_to_throw", "attempts") if len(qb) else NAN
    P["off_aggr"] = wmean(qb, "team", "aggressiveness", "attempts") / 100 if len(qb) else NAN
    P["def_aggr"] = wmean(qb, "opp", "aggressiveness", "attempts") / 100 if len(qb) else NAN
    if len(pp):
        x = pp.copy()
        for c in ("passing_bad_throws", "passing_drops"):
            x[c] = pd.to_numeric(x.get(c), errors="coerce").fillna(0)
        bt = x.groupby("team")[["passing_bad_throws", "passing_drops"]].sum()
        natt_o = att[att.sack != 1].groupby("posteam").size().reindex(TEAMS)
        P["off_bad"] = per(bt.passing_bad_throws.reindex(TEAMS), natt_o)
        P["off_drop"] = per(bt.passing_drops.reindex(TEAMS), natt_o)
    V["passing"] = P

    # ---------------- rushing ----------------
    R = pd.DataFrame(index=TEAMS)
    runs = s[s.dr == 1]
    for side, pre in (("posteam", "off"), ("defteam", "def")):
        g = runs.groupby(side)
        R[f"{pre}_ypc"] = g.yards_gained.mean().reindex(TEAMS)
        R[f"{pre}_epa"] = g.epa.mean().reindex(TEAMS)
        R[f"{pre}_succ"] = g.success.mean().reindex(TEAMS)
        R[f"{pre}_expl"] = runs.assign(x=(runs.yards_gained >= 10).astype(float)).groupby(side).x.mean().reindex(TEAMS)
        R[f"{pre}_stuff"] = runs.assign(x=(runs.yards_gained <= 0).astype(float)).groupby(side).x.mean().reindex(TEAMS)
        key = "team" if pre == "off" else "opp"
        R[f"{pre}_ryoe"] = wmean(ru, key, "rush_yards_over_expected_per_att", "rush_attempts") if len(ru) else NAN
        R[f"{pre}_box8"] = wmean(ru, key, "percent_attempts_gte_eight_defenders", "rush_attempts") / 100 if len(ru) else NAN
        R[f"{pre}_eff"] = wmean(ru, key, "efficiency", "rush_attempts") if len(ru) else NAN
    R["off_ttl"] = wmean(ru, "team", "avg_time_to_los", "rush_attempts") if len(ru) else NAN
    if len(pr):
        x = pr[pr.pfr_player_id.map(is_rb)].copy()
        for c in ("carries", "rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles"):
            x[c] = pd.to_numeric(x.get(c), errors="coerce").fillna(0)
        for key, pre in (("team", "off"), ("opponent", "def")):
            if key not in x:
                continue
            a = x.groupby(key)[["carries", "rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles"]].sum()
            R[f"{pre}_ybc"] = per(a.rushing_yards_before_contact.reindex(TEAMS), a.carries.reindex(TEAMS))
            R[f"{pre}_yac"] = per(a.rushing_yards_after_contact.reindex(TEAMS), a.carries.reindex(TEAMS))
            R[f"{pre}_btk"] = per(a.rushing_broken_tackles.reindex(TEAMS), a.carries.reindex(TEAMS)) * 100
    V["rushing"] = R

    # ---------------- drives ----------------
    D = pd.DataFrame(index=TEAMS)
    for side, pre in (("posteam", "off"), ("defteam", "def")):
        dd = drives(pbp, side)
        for c in ("pts", "td", "three_out", "punt", "to", "start", "yds", "plays", "sec"):
            D[f"{pre}_{c}"] = dd[c]
        D[f"{pre}_n_pg"] = dd.n / gp
    V["drives"] = D

    # ---------------- situational ----------------
    S = pd.DataFrame(index=TEAMS)
    t3 = s[s.down == 3].assign(conv=lambda x: x.third_down_converted.fillna(0), fail=lambda x: x.third_down_failed.fillna(0))
    f4 = s[s.down == 4].assign(conv=lambda x: x.fourth_down_converted.fillna(0), fail=lambda x: x.fourth_down_failed.fillna(0))
    all4 = pbp[(pbp.down == 4) & pbp.posteam.isin(TIX) & pbp.play_type.isin(["run", "pass", "punt", "field_goal"])]
    short4 = all4[(all4.ydstogo <= 2) & (all4.yardline_100.between(30, 70)) & (all4.qtr <= 4)]
    for side, pre in (("posteam", "off"), ("defteam", "def")):
        for name, lo, hi in (("short", 1, 3), ("med", 4, 6), ("long", 7, 99)):
            x = t3[t3.ydstogo.between(lo, hi)].groupby(side)
            S[f"{pre}_3rd_{name}"] = per(x.conv.sum(), x.conv.sum() + x.fail.sum())
        x = t3.groupby(side)
        S[f"{pre}_3rd"] = per(x.conv.sum(), x.conv.sum() + x.fail.sum())
        x = f4.groupby(side)
        S[f"{pre}_4th"] = per(x.conv.sum(), x.conv.sum() + x.fail.sum())
        gtg = s[s.goal_to_go == 1].groupby(["game_id", "fixed_drive", side]).fixed_drive_result.first().reset_index()
        S[f"{pre}_gtg_td"] = gtg.assign(td=(gtg.fixed_drive_result == "Touchdown").astype(float)).groupby(side).td.mean().reindex(TEAMS)
        rz = s.groupby(["game_id", "fixed_drive", side]).agg(m=("yardline_100", "min"), r=("fixed_drive_result", "first")).reset_index()
        rz = rz[rz.m <= 20]
        S[f"{pre}_rz_td"] = rz.assign(td=(rz.r == "Touchdown").astype(float)).groupby(side).td.mean().reindex(TEAMS)
    S["off_go_short"] = short4.assign(go=short4.play_type.isin(["run", "pass"]).astype(float)).groupby("posteam").go.mean().reindex(TEAMS)
    give = (s.groupby("posteam").interception.sum() + s.groupby("posteam").fumble_lost.sum()).reindex(TEAMS)
    take = (s.groupby("defteam").interception.sum() + s.groupby("defteam").fumble_lost.sum()).reindex(TEAMS)
    S["to_margin_pg"] = (take - give) / gp
    V["situational"] = S

    # ---------------- special teams ----------------
    T = pd.DataFrame(index=TEAMS)
    k = pbp[pbp.posteam.isin(TIX)]
    fg = k[k.field_goal_attempt == 1]
    made = (fg.field_goal_result == "made").astype(float)
    fg = fg.assign(made=made)
    T["fg"] = fg.groupby("posteam").made.mean().reindex(TEAMS)
    T["fg40"] = fg[fg.kick_distance.between(40, 49)].groupby("posteam").made.mean().reindex(TEAMS)
    T["fg50"] = fg[fg.kick_distance >= 50].groupby("posteam").made.mean().reindex(TEAMS)
    T["fga_pg"] = fg.groupby("posteam").size().reindex(TEAMS) / gp
    xp = k[k.extra_point_attempt == 1].assign(good=lambda x: (x.extra_point_result == "good").astype(float))
    T["xp"] = xp.groupby("posteam").good.mean().reindex(TEAMS)
    pu = k[(k.punt_attempt == 1) & (k.punt_blocked != 1) & k.kick_distance.notna()].copy()
    pu["net"] = pu.kick_distance - pu.return_yards.fillna(0) - 20 * pu.touchback.fillna(0)
    T["punt_net"] = pu.groupby("posteam").net.mean().reindex(TEAMS)
    T["punt_in20"] = pu.groupby("posteam").punt_inside_twenty.mean().reindex(TEAMS)
    T["punt_ret_allowed"] = pu[pu.return_yards.fillna(0) != 0].groupby("posteam").return_yards.mean().reindex(TEAMS)
    T["punt_ret"] = pu[pu.return_yards.fillna(0) != 0].groupby("defteam").return_yards.mean().reindex(TEAMS)
    ko = pbp[(pbp.kickoff_attempt == 1) & pbp.posteam.isin(TIX) & pbp.defteam.isin(TIX)]
    # on kickoffs nflverse sets posteam = receiving team, defteam = kicking team
    T["ko_tb"] = ko.groupby("defteam").touchback.mean().reindex(TEAMS)
    ret = ko[(ko.touchback != 1) & ko.return_yards.notna()]
    T["kr"] = ret.groupby("posteam").return_yards.mean().reindex(TEAMS)
    T["kr_allowed"] = ret.groupby("defteam").return_yards.mean().reindex(TEAMS)
    st = pbp[pbp.play_type.isin(["punt", "field_goal", "kickoff", "extra_point"]) & pbp.posteam.isin(TIX) & pbp.defteam.isin(TIX) & pbp.epa.notna()]
    T["st_epa_pg"] = (st.groupby("posteam").epa.sum().reindex(TEAMS).fillna(0) - st.groupby("defteam").epa.sum().reindex(TEAMS).fillna(0)) / gp
    V["special_teams"] = T

    # ---------------- discipline ----------------
    Q = pd.DataFrame(index=TEAMS)
    pen = pbp[(pbp.penalty == 1) & pbp.penalty_team.isin(TIX)].copy()
    pen["team"] = pen.penalty_team.replace(FIX)
    acc = pen[pen.penalty_yards.fillna(0) != 0]
    Q["pen_pg"] = acc.groupby("team").size().reindex(TEAMS).fillna(0) / gp
    Q["pen_yds_pg"] = acc.groupby("team").penalty_yards.sum().reindex(TEAMS).fillna(0) / gp
    Q["presnap_pg"] = acc[acc.penalty_type.isin(PRESNAP)].groupby("team").size().reindex(TEAMS).fillna(0) / gp
    on_off = acc[acc.team == acc.posteam]
    on_def = acc[acc.team == acc.defteam]
    Q["off_pen_pg"] = on_off.groupby("team").size().reindex(TEAMS).fillna(0) / gp
    Q["def_pen_pg"] = on_def.groupby("team").size().reindex(TEAMS).fillna(0) / gp
    opp_acc = acc.assign(opp=np.where(acc.team == acc.posteam, acc.defteam, acc.posteam))
    Q["drawn_pg"] = opp_acc.groupby("opp").size().reindex(TEAMS).fillna(0) / gp
    Q["fpd_pg"] = acc[acc.penalty_type.isin(["Defensive Pass Interference"])].groupby("team").size().reindex(TEAMS).fillna(0) / gp
    if len(pdf):
        x = pdf.copy()
        x["def_missed_tackles"] = pd.to_numeric(x.get("def_missed_tackles"), errors="coerce").fillna(0)
        x["def_tackles_combined"] = pd.to_numeric(x.get("def_tackles_combined"), errors="coerce").fillna(0)
        a = x.groupby("team")[["def_missed_tackles", "def_tackles_combined"]].sum().reindex(TEAMS)
        Q["missed_pg"] = a.def_missed_tackles / gp
        Q["missed_rate"] = per(a.def_missed_tackles, a.def_missed_tackles + a.def_tackles_combined)
    V["discipline"] = Q

    # ---------------- NGS additions for the line pages ----------------
    V["_ngs_oline"] = pd.DataFrame({"ttt_ngs": P["off_ttt"], "ryoe": R["off_ryoe"], "box8": R["off_box8"]})
    V["_ngs_dline"] = pd.DataFrame({"ryoe": R["def_ryoe"], "box8": R["def_box8"]})
    return V
