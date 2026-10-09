"""Player stats 2018 onward: season tables, career summaries and weekly game logs.

Sources (all nflverse): weekly player stats (regular season), Next Gen Stats weekly (time to throw, CPOE,
aggressiveness, rush yards over expected, separation, cushion, YAC over expected), Pro Football Reference weekly
advanced stats (pressures, bad throws, drops, yards before/after contact, broken tackles, coverage, missed tackles),
snap counts, and the players table (IDs, rookie season, draft, birth date).

Outputs (build/):
  players_<season>.json              one row per player with every stat (columnar)
  players_career.json                core stats per player-season, all seasons (for the player history view)
  players_weekly/<season>_<team>.json weekly game logs by team
Completed seasons are cached in data/ (keyed by this file's hash), so a normal run only rebuilds the current season.
"""
import hashlib
import json
import os
import warnings

import numpy as np
import pandas as pd

from common import DATA, FIX, OUT, TIX, download, log

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
FIRST = 2018
SRC_HASH = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:10]


def _csv(rel, current):
    p = download(rel, required=False, max_age_h=2.0 if current else 24 * 365)
    return pd.read_csv(p, low_memory=False) if p else pd.DataFrame()


def _num(d, cols):
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0) if c in d else 0.0
    return d


def idmap():
    p = download("players/players.csv", max_age_h=24 * 7)
    P = pd.read_csv(p, low_memory=False)
    P = P[P.gsis_id.notna()]
    return P.set_index("gsis_id"), dict(zip(P.pfr_id.dropna(), P.loc[P.pfr_id.notna(), "gsis_id"]))


COUNTS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
          "sack_yards_lost", "passing_air_yards", "passing_yards_after_catch", "passing_first_downs", "passing_epa",
          "passing_20", "carries", "rushing_yards", "rushing_tds", "rushing_fumbles_lost", "rushing_first_downs",
          "rushing_epa", "rushing_10", "rushing_20", "receptions", "targets", "receiving_yards", "receiving_tds",
          "receiving_air_yards", "receiving_yards_after_catch", "receiving_first_downs", "receiving_epa", "receiving_20",
          "receiving_fumbles_lost", "sack_fumbles_lost", "def_tackles_solo", "def_tackle_assists", "def_tackles_with_assist",
          "def_tackles_for_loss", "def_sacks", "def_qb_hits", "def_interceptions", "def_pass_defended",
          "def_fumbles_forced", "fumble_recovery_opp", "def_tds", "fg_made", "fg_att", "fg_made_40_49", "fg_missed_40_49",
          "fg_made_50_59", "fg_missed_50_59", "fg_made_60_", "fg_missed_60_", "pat_made", "pat_att", "pt_att", "pt_yards",
          "pt_inside_20", "pt_touchback", "pt_net_yards", "punt_returns", "punt_return_yards", "kickoff_returns",
          "kickoff_return_yards", "special_teams_tds"]
WEIGHTED = {"passing_cpoe": "attempts", "target_share": "w1", "air_yards_share": "w1", "wopr": "w1"}


def weekly(season, current):
    d = _csv(f"stats_player/stats_player_week_{season}.csv", current)
    if d.empty:
        return d
    d = d[d.season_type == "REG"].copy()
    for c in ("team", "opponent_team"):
        if c in d:
            d[c] = d[c].replace(FIX)
    d = _num(d, COUNTS + ["passing_cpoe", "target_share", "air_yards_share", "wopr", "fg_long"])
    d["w1"] = 1.0
    return d


def season_table(season, current, P, pfr2gsis):
    d = weekly(season, current)
    if d.empty:
        return pd.DataFrame(), d
    g = d.groupby("player_id")
    A = g[COUNTS].sum()
    A["name"] = g.player_display_name.last()
    A["pos"] = g.position.last()
    A["grp"] = g.position_group.last()
    A["team"] = g.team.last()
    A["games"] = g.week.nunique()
    A["fg_long"] = g.fg_long.max()
    for c, w in WEIGHTED.items():
        x = d[d[c] != 0]
        A[c] = (x[c] * x[w]).groupby(x.player_id).sum() / x.groupby("player_id")[w].sum()
    # identity: rookie season, draft, age
    info = P.reindex(A.index)
    A["rookie"] = (info.rookie_season == season).astype(int).values
    A["draft"] = np.where(info.draft_round.notna(), "R" + info.draft_round.fillna(0).astype(int).astype(str) + " #" +
                          info.draft_pick.fillna(0).astype(int).astype(str), "Undrafted")
    bd = pd.to_datetime(info.birth_date, errors="coerce")
    A["age"] = ((pd.Timestamp(f"{season}-09-01") - bd).dt.days / 365.25).round(1).values
    # Next Gen Stats (weekly, weighted to season)
    for kind, fields, w in (("passing", ["avg_time_to_throw", "aggressiveness", "avg_intended_air_yards"], "attempts"),
                            ("rushing", ["rush_yards_over_expected_per_att", "efficiency", "percent_attempts_gte_eight_defenders",
                                         "avg_time_to_los"], "rush_attempts"),
                            ("receiving", ["avg_separation", "avg_cushion", "avg_yac_above_expectation"], "targets")):
        n = _csv(f"nextgen_stats/ngs_{kind}.csv.gz", current)
        if n.empty:
            continue
        n = n[(n.season == season) & (n.season_type == "REG") & (n.week > 0)]
        n = _num(n, fields + [w])
        for f in fields:
            x = n[n[w] > 0]
            A[f"ngs_{f}"] = (x[f] * x[w]).groupby(x.player_gsis_id).sum() / x.groupby("player_gsis_id")[w].sum()
        if kind == "rushing":
            A["ngs_ryoe_total"] = (n.rush_yards_over_expected_per_att * n.rush_attempts).groupby(n.player_gsis_id).sum()
    # Pro Football Reference weekly advanced stats
    pf = {}
    for kind, cols in (("pass", ["times_pressured", "passing_bad_throws", "passing_drops", "times_blitzed", "times_hurried", "times_hit"]),
                       ("rush", ["rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles", "carries"]),
                       ("rec", ["receiving_drop", "receiving_broken_tackles"]),
                       ("def", ["def_pressures", "def_times_hurried", "def_times_hitqb", "def_missed_tackles", "def_targets",
                                "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed", "def_tackles_combined"])):
        x = _csv(f"pfr_advstats/advstats_week_{kind}_{season}.csv", current)
        if x.empty:
            continue
        if "game_type" in x:
            x = x[x.game_type == "REG"]
        x = _num(x, cols)
        x["gsis"] = x.pfr_player_id.map(pfr2gsis)
        s = x.groupby("gsis")[cols].sum()
        for c in cols:
            pf[f"pfr_{kind}_{c}"] = s[c]
    for k, v in pf.items():
        A[k] = v
    # snaps
    sn = _csv(f"snap_counts/snap_counts_{season}.csv", current)
    if not sn.empty:
        sn = sn[sn.game_type == "REG"] if "game_type" in sn else sn
        sn = _num(sn, ["offense_pct", "defense_pct", "offense_snaps", "defense_snaps", "st_snaps"])
        sn["gsis"] = sn.pfr_player_id.map(pfr2gsis)
        s = sn.groupby("gsis")
        A["off_snap_pct"] = s.offense_pct.mean().where(s.offense_snaps.sum() > 0)
        A["def_snap_pct"] = s.defense_pct.mean().where(s.defense_snaps.sum() > 0)
        A["off_snaps"] = s.offense_snaps.sum()
        A["def_snaps"] = s.defense_snaps.sum()
    return derive(A), d


def ratio(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return a / b.where(b > 0)


def derive(A):
    D = pd.DataFrame(index=A.index)
    for c in ("name", "pos", "grp", "team", "games", "rookie", "draft", "age"):
        D[c] = A[c]
    g = A.games.clip(lower=1)
    # passing
    D["att"], D["cmp"] = A.attempts, A.completions
    D["cmp_pct"] = ratio(A.completions, A.attempts)
    D["pass_yds"], D["pass_td"], D["int"] = A.passing_yards, A.passing_tds, A.passing_interceptions
    D["ypa"] = ratio(A.passing_yards, A.attempts)
    D["td_pct"], D["int_pct"] = ratio(A.passing_tds, A.attempts), ratio(A.passing_interceptions, A.attempts)
    D["sacks"] = A.sacks_suffered
    D["sack_pct"] = ratio(A.sacks_suffered, A.attempts + A.sacks_suffered)
    D["anya"] = ratio(A.passing_yards + 20 * A.passing_tds - 45 * A.passing_interceptions - A.sack_yards_lost, A.attempts + A.sacks_suffered)
    D["pass_epa"] = A.passing_epa
    D["epa_db"] = ratio(A.passing_epa, A.attempts + A.sacks_suffered)
    D["cpoe"] = A.passing_cpoe / 100
    D["adot"] = ratio(A.passing_air_yards, A.attempts)
    D["pass_fd"] = A.passing_first_downs
    D["pass_20"] = A.passing_20
    D["pass_yds_g"] = A.passing_yards / g
    D["ttt"] = A.get("ngs_avg_time_to_throw")
    D["aggr"] = A.get("ngs_aggressiveness", pd.Series(dtype=float)) / 100
    D["press_pct"] = ratio(A.get("pfr_pass_times_pressured", 0), A.attempts + A.sacks_suffered)
    D["bad_pct"] = ratio(A.get("pfr_pass_passing_bad_throws", 0), A.attempts)
    # rushing
    D["car"], D["rush_yds"], D["rush_td"] = A.carries, A.rushing_yards, A.rushing_tds
    D["ypc"] = ratio(A.rushing_yards, A.carries)
    D["rush_epa"] = A.rushing_epa
    D["epa_car"] = ratio(A.rushing_epa, A.carries)
    D["rush_fd"] = A.rushing_first_downs
    D["rush_10"], D["rush_20"] = A.rushing_10, A.rushing_20
    D["rush_yds_g"] = A.rushing_yards / g
    D["ryoe_att"] = A.get("ngs_rush_yards_over_expected_per_att")
    D["ryoe"] = A.get("ngs_ryoe_total")
    D["ngs_eff"] = A.get("ngs_efficiency")
    D["box8"] = A.get("ngs_percent_attempts_gte_eight_defenders", pd.Series(dtype=float)) / 100
    D["ybc_att"] = ratio(A.get("pfr_rush_rushing_yards_before_contact", 0), A.get("pfr_rush_carries", 0))
    D["yac_att"] = ratio(A.get("pfr_rush_rushing_yards_after_contact", 0), A.get("pfr_rush_carries", 0))
    D["btk"] = A.get("pfr_rush_rushing_broken_tackles", 0) + A.get("pfr_rec_receiving_broken_tackles", 0)
    D["fum_lost"] = A.rushing_fumbles_lost + A.receiving_fumbles_lost + A.sack_fumbles_lost
    # receiving
    D["tgt"], D["rec"], D["rec_yds"], D["rec_td"] = A.targets, A.receptions, A.receiving_yards, A.receiving_tds
    D["catch_pct"] = ratio(A.receptions, A.targets)
    D["ypr"], D["ypt"] = ratio(A.receiving_yards, A.receptions), ratio(A.receiving_yards, A.targets)
    D["rec_epa"] = A.receiving_epa
    D["epa_tgt"] = ratio(A.receiving_epa, A.targets)
    D["rec_adot"] = ratio(A.receiving_air_yards, A.targets)
    D["rec_air"] = A.receiving_air_yards
    D["yac"] = A.receiving_yards_after_catch
    D["tgt_share"], D["air_share"], D["wopr"] = A.target_share, A.air_yards_share, A.wopr
    D["rec_fd"], D["rec_20"] = A.receiving_first_downs, A.receiving_20
    D["rec_yds_g"] = A.receiving_yards / g
    D["sep"], D["cushion"], D["yacoe"] = A.get("ngs_avg_separation"), A.get("ngs_avg_cushion"), A.get("ngs_avg_yac_above_expectation")
    D["drops"] = A.get("pfr_rec_receiving_drop", 0)
    D["drop_pct"] = ratio(D.drops, A.targets)
    # scrimmage / total
    D["scrim_yds"] = A.rushing_yards + A.receiving_yards
    D["touches"] = A.carries + A.receptions
    D["tot_td"] = A.rushing_tds + A.receiving_tds + A.passing_tds * 0 + A.special_teams_tds
    D["tot_epa"] = A.passing_epa + A.rushing_epa + A.receiving_epa
    # defense
    D["tkl"] = A.def_tackles_solo + A.def_tackle_assists + A.def_tackles_with_assist
    D["solo"] = A.def_tackles_solo
    D["tfl"], D["dsacks"], D["qb_hits"] = A.def_tackles_for_loss, A.def_sacks, A.def_qb_hits
    D["pressures"] = A.get("pfr_def_def_pressures")
    D["hurries"] = A.get("pfr_def_def_times_hurried")
    D["dint"], D["pd"], D["ff"], D["fr"], D["dtd"] = A.def_interceptions, A.def_pass_defended, A.def_fumbles_forced, A.fumble_recovery_opp, A.def_tds
    D["tgt_allowed"] = A.get("pfr_def_def_targets")
    D["cmp_allowed"] = ratio(A.get("pfr_def_def_completions_allowed", 0), A.get("pfr_def_def_targets", 0))
    D["ypt_allowed"] = ratio(A.get("pfr_def_def_yards_allowed", 0), A.get("pfr_def_def_targets", 0))
    D["td_allowed"] = A.get("pfr_def_def_receiving_td_allowed")
    D["missed"] = A.get("pfr_def_def_missed_tackles")
    D["missed_pct"] = ratio(A.get("pfr_def_def_missed_tackles", 0), A.get("pfr_def_def_missed_tackles", 0) + A.get("pfr_def_def_tackles_combined", 0))
    # kicking / punting / returns
    D["fgm"], D["fga"] = A.fg_made, A.fg_att
    D["fg_pct"] = ratio(A.fg_made, A.fg_att)
    D["fg40"] = ratio(A.fg_made_40_49, A.fg_made_40_49 + A.fg_missed_40_49)
    D["fg50"] = ratio(A.fg_made_50_59 + A.fg_made_60_, A.fg_made_50_59 + A.fg_made_60_ + A.fg_missed_50_59 + A.fg_missed_60_)
    D["fg50m"] = A.fg_made_50_59 + A.fg_made_60_
    D["fg_long"] = A.fg_long
    D["xpm"], D["xpa"] = A.pat_made, A.pat_att
    D["xp_pct"] = ratio(A.pat_made, A.pat_att)
    D["punts"] = A.pt_att
    D["punt_avg"], D["punt_net"] = ratio(A.pt_yards, A.pt_att), ratio(A.pt_net_yards, A.pt_att)
    D["punt_in20"] = ratio(A.pt_inside_20, A.pt_att)
    D["kr"], D["kr_avg"] = A.kickoff_returns, ratio(A.kickoff_return_yards, A.kickoff_returns)
    D["pr"], D["pr_avg"] = A.punt_returns, ratio(A.punt_return_yards, A.punt_returns)
    D["st_td"] = A.special_teams_tds
    D["off_snap_pct"] = A.get("off_snap_pct", pd.Series(dtype=float))  # nflverse snap shares are already fractions
    D["def_snap_pct"] = A.get("def_snap_pct", pd.Series(dtype=float))
    keep = (A.attempts > 0) | (A.carries > 0) | (A.targets > 0) | (D.tkl > 0) | (A.def_sacks > 0) | (A.fg_att > 0) | (A.pt_att > 0) | (A.pat_att > 0)
    return D[keep]


CAREER = ["season", "name", "pos", "team", "games", "att", "pass_yds", "pass_td", "int", "anya", "epa_db", "cpoe", "car", "rush_yds",
          "rush_td", "ypc", "ryoe_att", "tgt", "rec", "rec_yds", "rec_td", "ypt", "scrim_yds", "tot_td", "tkl", "tfl", "dsacks",
          "pressures", "dint", "pd", "ff", "fgm", "fga", "fg_pct", "punt_net"]
WEEKLY = {"week": "week", "opp": "opponent_team", "att": "attempts", "cmp": "completions", "pass_yds": "passing_yards",
          "pass_td": "passing_tds", "int": "passing_interceptions", "sacks": "sacks_suffered", "pass_epa": "passing_epa",
          "cpoe": "passing_cpoe", "car": "carries", "rush_yds": "rushing_yards", "rush_td": "rushing_tds", "rush_epa": "rushing_epa",
          "tgt": "targets", "rec": "receptions", "rec_yds": "receiving_yards", "rec_td": "receiving_tds", "rec_epa": "receiving_epa",
          "tkl_solo": "def_tackles_solo", "tkl_ast": "def_tackle_assists", "tfl": "def_tackles_for_loss", "dsacks": "def_sacks",
          "qb_hits": "def_qb_hits", "dint": "def_interceptions", "pd": "def_pass_defended", "ff": "def_fumbles_forced",
          "fgm": "fg_made", "fga": "fg_att", "xpm": "pat_made", "punts": "pt_att"}


def clean(v):
    if v is None:
        return None
    if isinstance(v, (str, bool)):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return int(f) if f.is_integer() and abs(f) < 1e9 else round(f, 4)


def columnar(df, cols):
    return {c: [clean(v) for v in df[c].tolist()] for c in cols}


def build_season(season, current, P, pfr2gsis):
    T, W = season_table(season, current, P, pfr2gsis)
    if T.empty:
        return None
    T = T.reset_index().rename(columns={"index": "id", "player_id": "id"})
    cols = list(T.columns)
    season_json = {"season": season, "cols": cols, "data": columnar(T, cols)}
    wk = {}
    if not W.empty:
        W = W[["player_id", "team"] + list(WEEKLY.values())].copy()
        for team, x in W.groupby("team"):
            if team not in TIX:
                continue
            x = x.sort_values(["player_id", "week"])
            out = {"id": x.player_id.tolist()}
            for k, src in WEEKLY.items():
                out[k] = [clean(v) for v in x[src].tolist()]
            wk[team] = out
    return season_json, wk, T


def build_all(cur_season):
    P, pfr2gsis = idmap()
    os.makedirs(os.path.join(OUT, "players_weekly"), exist_ok=True)
    career = []
    seasons = []
    for y in range(FIRST, cur_season + 1):
        current = y == cur_season
        cache = os.path.join(DATA, f"players_{y}_{SRC_HASH}.json")
        if not current and os.path.exists(cache):
            blob = json.load(open(cache))
        else:
            r = build_season(y, current, P, pfr2gsis)
            if r is None:
                continue
            sj, wk, T = r
            blob = {"season": sj, "weekly": wk}
            if not current:
                json.dump(blob, open(cache, "w"), separators=(",", ":"))
        sj = blob["season"]
        seasons.append(y)
        with open(os.path.join(OUT, f"players_{y}.json"), "w") as f:
            json.dump(sj, f, separators=(",", ":"))
        for team, x in blob["weekly"].items():
            with open(os.path.join(OUT, "players_weekly", f"{y}_{team}.json"), "w") as f:
                json.dump(x, f, separators=(",", ":"))
        T = pd.DataFrame(sj["data"])
        T["season"] = y
        imp = (T.att >= 50) | (T.car >= 30) | (T.tgt >= 20) | (T.tkl >= 20) | (T.dsacks >= 2) | (T.fga >= 5) | (T.punts >= 10) | (T.dint >= 2)
        career.append(T[imp][["id"] + CAREER])
        log("players", y, len(T))
    C = pd.concat(career, ignore_index=True)
    with open(os.path.join(OUT, "players_career.json"), "w") as f:
        json.dump({"cols": ["id"] + CAREER, "data": columnar(C, ["id"] + CAREER)}, f, separators=(",", ":"))
    with open(os.path.join(OUT, "players_index.json"), "w") as f:
        json.dump({"seasons": seasons, "current": cur_season}, f)
    return seasons
