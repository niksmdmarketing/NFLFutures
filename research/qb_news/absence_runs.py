"""Historical absence runs of a team's incumbent QB (research/NFL_QB_NEWS_RULE.md, version 2), from official weekly data only.
Incumbent at week k = the team's QB with most dropbacks in its regular-season games before week k (the reference-QB definition).
A run starts at a team game where the incumbent did not start (audited starter labels) AND was, for that week, listed Out or Doubtful
on the official injury report or held roster status RES (reserve: IR, PUP, NFI) or SUS (suspended). It continues while the same
QB keeps missing starts with such a status; its length L = consecutive team games missed. Runs reaching the season's last
regular-season game are flagged censored. Outcome-independent: every listed absence counts, whatever its length.
Output: research/qb_news/absence_runs.csv (season, team, qb, first_week, L, censored).
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import DATA, FIX, games, load_pbp, scrimmage  # noqa: E402

LAB = pd.read_csv(os.path.join(ROOT, "research", "nfl_qb_starter_labels.csv"))
SEASONS = range(2013, 2026)


def statuses(y):
    inj = pd.read_csv(os.path.join(DATA, f"injuries_{y}.csv"), low_memory=False)
    inj = inj[(inj.game_type == "REG") & inj.report_status.isin(["Out", "Doubtful"])]
    s = {(r.gsis_id, int(r.week)): r.report_status for r in inj.itertuples()}
    ros = pd.read_csv(os.path.join(DATA, f"roster_weekly_{y}.csv"), low_memory=False)
    ros = ros[ros.status.isin(["RES", "SUS"])]
    for r in ros.itertuples():
        s.setdefault((r.gsis_id, int(r.week)), r.status)
    return s


def dropbacks_by_week(y):
    s = scrimmage(load_pbp(y))
    s = s[(s.season_type == "REG") & (s.qb_dropback == 1)].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    return s.groupby(["posteam", "week", "qb"]).size().rename("n").reset_index()


def runs(y, g):
    st = statuses(y)
    db = dropbacks_by_week(y)
    lab = LAB[LAB.season == y]
    reg = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
    out = []
    for t in sorted(set(reg.home_team) | set(reg.away_team)):
        tg = reg[(reg.home_team == t) | (reg.away_team == t)].sort_values("week")
        weeks = list(tg.week)
        cur = None
        for k, gid in zip(tg.week, tg.game_id):
            starter = lab[(lab.game_id == gid) & (lab.team == t)].chosen
            starter = starter.iloc[0] if len(starter) else None
            if cur:
                if starter != cur["qb"] and (cur["qb"], int(k)) in st:
                    cur["L"] += 1
                    continue
                out.append(cur)
                cur = None
            prev = db[(db.posteam == t) & (db.week < k)]
            inc = prev.groupby("qb").n.sum().idxmax() if len(prev) else None
            if inc is not None and starter != inc and (inc, int(k)) in st:
                cur = dict(season=y, team=t, qb=inc, first_week=int(k), L=1)
        if cur:
            cur["censored"] = True
            out.append(cur)
    for r in out:
        r.setdefault("censored", False)
    return out


def main():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows = []
    for y in SEASONS:
        rows += runs(y, g)
        print(y, sum(r["season"] == y for r in rows), flush=True)
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(ROOT, "research", "qb_news", "absence_runs.csv"), index=False)
    print(D.L.describe(), D.censored.mean())


if __name__ == "__main__":
    main()
