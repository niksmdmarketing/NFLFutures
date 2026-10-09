"""Award race tracker: current candidates against past winners at the same point of the season.

For each award: the leading candidates (the award model's top names plus statistical leaders) with stats to date,
a 17-game pace and team record; and every winner from 2018 to last season with the same stats through the same week
and at season end. Recomputed on every refresh.
"""
import re


from common import TEAMS
import players

WINNERS = {  # AP award winners by season
    "MVP": {2018: "Patrick Mahomes", 2019: "Lamar Jackson", 2020: "Aaron Rodgers", 2021: "Aaron Rodgers", 2022: "Patrick Mahomes",
            2023: "Lamar Jackson", 2024: "Josh Allen", 2025: "Matthew Stafford"},
    "OPOY": {2018: "Patrick Mahomes", 2019: "Michael Thomas", 2020: "Derrick Henry", 2021: "Cooper Kupp", 2022: "Justin Jefferson",
             2023: "Christian McCaffrey", 2024: "Saquon Barkley", 2025: "Jaxon Smith-Njigba"},
    "DPOY": {2018: "Aaron Donald", 2019: "Stephon Gilmore", 2020: "Aaron Donald", 2021: "T.J. Watt", 2022: "Nick Bosa",
             2023: "Myles Garrett", 2024: "Patrick Surtain", 2025: "Myles Garrett"},
    "OROY": {2018: "Saquon Barkley", 2019: "Kyler Murray", 2020: "Justin Herbert", 2021: "Ja'Marr Chase", 2022: "Garrett Wilson",
             2023: "C.J. Stroud", 2024: "Jayden Daniels", 2025: "Tetairoa McMillan"},
    "DROY": {2018: "Darius Leonard", 2019: "Nick Bosa", 2020: "Chase Young", 2021: "Micah Parsons", 2022: "Sauce Gardner",
             2023: "Will Anderson", 2024: "Jared Verse", 2025: "Carson Schwesinger"},
    "CPOY": {2018: "Andrew Luck", 2019: "Ryan Tannehill", 2020: "Alex Smith", 2021: "Joe Burrow", 2022: "Geno Smith",
             2023: "Joe Flacco", 2024: "Joe Burrow", 2025: "Christian McCaffrey"},
}
COY = {2018: "CHI", 2019: "BAL", 2020: "CLE", 2021: "TEN", 2022: "NYG", 2023: "CLE", 2024: "MIN", 2025: "NE"}
ALIAS = {"darius leonard": "shaquille leonard", "sauce gardner": "ahmad gardner", "patrick surtain": "pat surtain"}
TITLES = {"MVP": "Most Valuable Player", "OPOY": "Offensive Player of the Year", "DPOY": "Defensive Player of the Year",
          "OROY": "Offensive Rookie of the Year", "DROY": "Defensive Rookie of the Year", "CPOY": "Comeback Player of the Year",
          "COY": "Coach of the Year"}
OFF_COLS = [("pass_yds", "Pass yds"), ("pass_td", "Pass TD"), ("int", "INT"), ("rush_yds", "Rush yds"), ("rec_yds", "Rec yds"),
            ("scrim_yds", "Scrim yds"), ("tot_td", "Total TD"), ("tot_epa", "Total EPA")]
DEF_COLS = [("dsacks", "Sacks"), ("tfl", "TFL"), ("qb_hits", "QB hits"), ("dint", "INT"), ("pd", "PD"), ("ff", "FF"), ("tkl", "Tackles")]


def norm(s):
    s = str(s).lower()
    s = ALIAS.get(s.strip(), s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def cum(W, upto):
    """Per-player totals from weekly rows through week `upto` (None = full season)."""
    d = W if upto is None else W[W.week <= upto]
    g = d.groupby("player_id")
    A = g[players.COUNTS].sum()
    A["name"], A["team"], A["pos"], A["grp"] = g.player_display_name.last(), g.team.last(), g.position.last(), g.position_group.last()
    A["games"] = g.week.nunique()
    A["rookie_flag"] = 0
    A["pass_yds"], A["pass_td"], A["int"] = A.passing_yards, A.passing_tds, A.passing_interceptions
    A["rush_yds"], A["rec_yds"] = A.rushing_yards, A.receiving_yards
    A["scrim_yds"] = A.rushing_yards + A.receiving_yards
    A["tot_td"] = A.passing_tds + A.rushing_tds + A.receiving_tds
    A["tot_epa"] = A.passing_epa + A.rushing_epa + A.receiving_epa
    A["dsacks"], A["tfl"], A["qb_hits"], A["dint"], A["pd"], A["ff"] = A.def_sacks, A.def_tackles_for_loss, A.def_qb_hits, A.def_interceptions, A.def_pass_defended, A.def_fumbles_forced
    A["tkl"] = A.def_tackles_solo + A.def_tackle_assists + A.def_tackles_with_assist
    A["norm"] = A.name.map(norm)
    return A


def records(games, season, upto=None):
    g = games[(games.season == season) & (games.game_type == "REG") & games.result.notna()]
    if upto is not None:
        g = g[g.week <= upto]
    rec = {t: [0, 0, 0] for t in TEAMS}
    for h, a, r in zip(g.home_team, g.away_team, g.result):
        if h not in rec or a not in rec:
            continue
        if r > 0: rec[h][0] += 1; rec[a][1] += 1
        elif r < 0: rec[a][0] += 1; rec[h][1] += 1
        else: rec[h][2] += 1; rec[a][2] += 1
    return rec


def rec_str(r):
    return f"{r[0]}-{r[1]}" + (f"-{r[2]}" if r[2] else "")


def row(A, pid, cols, rec, pace_games=17):
    r = A.loc[pid]
    out = {"name": r["name"], "team": r.team, "pos": r.pos, "games": int(r.games), "record": rec_str(rec.get(r.team, [0, 0, 0])),
           "win_pct": round((rec.get(r.team, [0, 0, 0])[0] + 0.5 * rec.get(r.team, [0, 0, 0])[2]) / max(sum(rec.get(r.team, [0, 0, 0])), 1), 3)}
    for k, _ in cols:
        v = float(r[k])
        out[k] = round(v, 2)
        out[k + "_pace"] = round(v / max(r.games, 1) * pace_games, 1)
    return out


def build(season, games, awards_json):
    W = players.weekly(season, True)
    if W.empty:
        return {"season": season, "week": 0, "awards": {}}
    week = int(W.week.max())
    cur = cum(W, None)
    P, _ = players.idmap()
    cur["rookie_flag"] = cur.index.map(lambda i: int(P.rookie_season.get(i, 0) == season) if i in P.index else 0)
    rec_now = records(games, season)
    hist = {}
    for y in range(2018, season):
        Wy = players.weekly(y, False)
        if not Wy.empty:
            hist[y] = (cum(Wy, week), cum(Wy, None), records(games, y, week), records(games, y))
    out = {"season": season, "week": week, "awards": {}}
    for aw in ("MVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY"):
        defensive = aw in ("DPOY", "DROY")
        cols = DEF_COLS if defensive else OFF_COLS
        model = {norm(c["name"]): c["prob"] for c in awards_json.get(aw, {}).get("candidates", [])}
        pool = cur[cur.grp.isin(["DL", "LB", "DB"])] if defensive else cur[~cur.grp.isin(["DL", "LB", "DB", "SPEC"])]
        if aw in ("OROY", "DROY"):
            pool = pool[pool.rookie_flag == 1]
        lead_key = {"MVP": "tot_epa", "OPOY": "scrim_yds", "DPOY": "dsacks", "OROY": "tot_epa", "DROY": "tkl", "CPOY": "tot_epa"}[aw]
        ids = list(pool[pool.norm.isin(model)].index) + list(pool.sort_values(lead_key, ascending=False).index[:8])
        if aw in ("OPOY", "OROY"):
            ids += list(pool.sort_values("pass_yds", ascending=False).index[:4])
        if aw == "DPOY":
            ids += list(pool.sort_values("dint", ascending=False).index[:3])
        seen, rows = set(), []
        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            r = row(cur, pid, cols, rec_now)
            r["model_prob"] = model.get(cur.loc[pid, "norm"])
            rows.append(r)
        rows.sort(key=lambda r: -(r["model_prob"] or 0))
        past = []
        for y, name in WINNERS[aw].items():
            if y not in hist:
                continue
            at, full, rec_at, rec_full = hist[y]

            f = full[full.norm == norm(name)]
            if f.empty:
                continue
            pid = f.index[0]
            r = {"season": y, "name": f.loc[pid, "name"], "team": f.loc[pid, "team"], "pos": f.loc[pid, "pos"]}
            r["record_at"] = rec_str(rec_at.get(r["team"], [0, 0, 0]))
            r["record_final"] = rec_str(rec_full.get(r["team"], [0, 0, 0]))
            for k, _ in cols:
                r[k + "_at"] = round(float(at.loc[pid, k]), 2) if pid in at.index else 0.0
                r[k + "_final"] = round(float(f.loc[pid, k]), 2)
            r["games_at"] = int(at.loc[pid, "games"]) if pid in at.index else 0
            past.append(r)
        out["awards"][aw] = {"title": TITLES[aw], "cols": [[k, lab] for k, lab in cols], "current": rows[:12], "past": past}
    # Coach of the Year: team records
    prev = records(games, season - 1)
    model = {c["team"]: c for c in awards_json.get("COY", {}).get("candidates", [])}
    rows = []
    for t in TEAMS:
        r = rec_now[t]
        gp = max(sum(r), 1)
        rows.append({"team": t, "coach": model.get(t, {}).get("name", ""), "record": rec_str(r), "win_pct": round((r[0] + 0.5 * r[2]) / gp, 3),
                     "prev_record": rec_str(prev[t]), "prev_win_pct": round((prev[t][0] + 0.5 * prev[t][2]) / max(sum(prev[t]), 1), 3),
                     "model_prob": model.get(t, {}).get("prob")})
    for r in rows:
        r["improve"] = round(r["win_pct"] - r["prev_win_pct"], 3)
    rows.sort(key=lambda r: -(r["model_prob"] or 0))
    past = []
    for y, t in COY.items():
        if y not in hist:
            continue
        _, _, rec_at, rec_full = hist[y]
        pr = records(games, y - 1)
        past.append({"season": y, "team": t, "record_at": rec_str(rec_at[t]), "record_final": rec_str(rec_full[t]), "prev_record": rec_str(pr[t])})
    out["awards"]["COY"] = {"title": TITLES["COY"], "current": rows[:15], "past": past}
    return out
