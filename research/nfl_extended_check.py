"""Input checks for the extended NFL futures baseline (2013-2025; research/TEST_POWER_RULE.md plan, 5 Nov 2026).
Per season: regular-season games and weeks in the schedule, results present, play-by-play coverage of every regular-season game
(this season and last, which the ratings use), walk-forward weights present and fitted only on earlier seasons, standings
(division winners, playoff seeds by era), Super Bowl result. Stops with a list of problems; prints a table otherwise.
Usage: python research/nfl_extended_check.py [first] [last]"""
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import FIX, TEAMS, games, load_pbp  # noqa: E402


def main(first, last):
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    st = pd.read_csv(os.path.join(ROOT, "data", "nfl_standings.csv"))
    st["team"] = st.team.replace(FIX)
    wf = json.load(open(os.path.join(ROOT, "model", "replay", "nfl_wf_coef.json")))
    problems, rows = [], []
    if "s-1" not in wf["note"]:
        problems.append("walk-forward note does not state training on earlier seasons only")
    pbp = {}
    for y in range(first - 1, last + 1):
        pbp[y] = load_pbp(y)
    for y in range(first, last + 1):
        reg = g[(g.season == y) & (g.game_type == "REG")]
        n_exp, wk_exp = (256, 17) if y <= 2020 else (272, 18)
        if y == 2022:
            n_exp = 271   # BUF-CIN (week 17, 2 Jan 2023) was cancelled and never replayed
        seeds_exp = 12 if y <= 2019 else 14
        r = dict(season=y, reg_games=len(reg), weeks=int(reg.week.max()), results=int(reg.result.notna().sum()))
        for s in (y, y - 1):
            gids = set(g[(g.season == s) & (g.game_type == "REG")].game_id)
            have = set(pbp[s].game_id.unique())
            r[f"pbp_cover_{'cur' if s == y else 'prev'}"] = round(len(gids & have) / max(len(gids), 1), 4)
        s_ = st[st.season == y]
        r.update(standings_teams=int(s_.team.isin(TEAMS).sum()), div_winners=int((s_.div_rank == 1).sum()),
                 seeds=int(s_.seed.notna().sum()), sb=int(((g.season == y) & (g.game_type == "SB") & g.result.notna()).sum()),
                 wf=str(y) in wf["seasons"], pbp_plays=len(pbp[y]))
        if r["reg_games"] != n_exp: problems.append(f"{y}: {r['reg_games']} regular-season games, expected {n_exp}")
        if r["weeks"] != wk_exp: problems.append(f"{y}: {r['weeks']} weeks, expected {wk_exp}")
        if r["results"] != n_exp: problems.append(f"{y}: {r['results']} results")
        if r["pbp_cover_cur"] < 0.999 or r["pbp_cover_prev"] < 0.999: problems.append(f"{y}: play-by-play coverage {r['pbp_cover_cur']}/{r['pbp_cover_prev']}")
        if r["standings_teams"] != 32 or r["div_winners"] != 8 or r["seeds"] != seeds_exp: problems.append(f"{y}: standings {r['standings_teams']} teams, {r['div_winners']} div winners, {r['seeds']} seeds (expected {seeds_exp})")
        if r["sb"] != 1: problems.append(f"{y}: Super Bowl result missing")
        if not r["wf"]: problems.append(f"{y}: no walk-forward weights")
        rows.append(r)
    T = pd.DataFrame(rows)
    print(T.to_string(index=False))
    if problems:
        raise SystemExit("NFL EXTENDED CHECK FAILED:\n  " + "\n  ".join(problems))
    print("NFL extended check passed")
    return T


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2013, int(sys.argv[2]) if len(sys.argv) > 2 else 2025)
