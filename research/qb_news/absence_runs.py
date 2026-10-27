"""Historical absence runs of a team's incumbent QB (research/NFL_QB_NEWS_RULE.md, version 2), from official weekly data only.
Incumbent at week k = the team's QB with most dropbacks in its regular-season games before week k (the reference-QB definition).
A run starts at a team game where the incumbent did not start (audited starter labels) AND was, for that week, listed Out or Doubtful
on the official injury report, held roster status RES (reserve: IR, PUP, NFI) or SUS (suspended), or was listed Questionable and inactive.
The incumbent is fixed when the run starts and kept until it ends (he starts again or is no longer listed = medical return).
Week 1: the incumbent is the team's previous-season dropback leader if he is on its roster in weeks 1-2. It continues while the same
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
    """(gsis_id, week) -> status for injury-related absences known after that week's game (version 3, after GPT's review):
    Out or Doubtful on the official injury report; roster RES (reserve lists) or SUS; or listed Questionable AND roster INA (inactive)
    for that week, i.e. a confirmed injury absence from a completed game. INA without an injury listing (healthy scratch) is excluded."""
    inj = pd.read_csv(os.path.join(DATA, f"injuries_{y}.csv"), low_memory=False)
    inj = inj[inj.game_type == "REG"]
    q = {(r.gsis_id, int(r.week)) for r in inj[inj.report_status == "Questionable"].itertuples()}
    s = {(r.gsis_id, int(r.week)): r.report_status for r in inj[inj.report_status.isin(["Out", "Doubtful"])].itertuples()}
    ros = pd.read_csv(os.path.join(DATA, f"roster_weekly_{y}.csv"), low_memory=False)
    for r in ros[ros.status.isin(["RES", "SUS"])].itertuples():
        s.setdefault((r.gsis_id, int(r.week)), r.status)
    for r in ros[ros.status == "INA"].itertuples():
        if (r.gsis_id, int(r.week)) in q:
            s.setdefault((r.gsis_id, int(r.week)), "Q-INA")
    return s


def prior_leaders(y):
    """Week-1 incumbents: each team's previous-season dropback leader, only if he is on that team's roster in weeks 1-2 of season y."""
    pdb = dropbacks_by_week(y - 1)
    lead = pdb.groupby(["posteam", "qb"]).n.sum().reset_index().sort_values("n").groupby("posteam").qb.last().to_dict()
    ros = pd.read_csv(os.path.join(DATA, f"roster_weekly_{y}.csv"), low_memory=False)
    ros = ros[ros.week <= 2].assign(team=lambda x: x.team.replace(FIX))
    on = set(zip(ros.team, ros.gsis_id))
    return {t: q for t, q in lead.items() if (t, q) in on}


def availability(y):
    """(gsis_id, week) -> 'available' when the QB was medically available for that week's game: roster status ACT and not injury-listed
    (see statuses), or he took a dropback / started. Inactive without an injury listing (healthy scratch) is also 'available'.
    Weeks with no roster record are absent from the map (unknown)."""
    st = statuses(y)
    ros = pd.read_csv(os.path.join(DATA, f"roster_weekly_{y}.csv"), low_memory=False)
    av = {}
    for r in ros[ros.status.isin(["ACT", "INA"])].itertuples():
        k = (r.gsis_id, int(r.week))
        if k not in st:
            av[k] = "available"
    db = dropbacks_by_week(y)
    for r in db.itertuples():
        av[(r.qb, int(r.week))] = "available"
    lab = LAB[LAB.season == y]
    return av


def dropbacks_by_week(y):
    s = scrimmage(load_pbp(y))
    s = s[(s.season_type == "REG") & (s.qb_dropback == 1)].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    return s.groupby(["posteam", "week", "qb"]).size().rename("n").reset_index()


def runs(y, g):
    """Version 3b (GPT's final check): a run ends only on verified medical availability (roster ACT/INA without an injury listing, or
    played). A week with no record and no listing censors the run (missing records do not establish recovery), as does season end.
    Losing the starting job while healthy ends the absence; it is not counted as injury duration."""
    st = statuses(y)
    av = availability(y)
    db = dropbacks_by_week(y)
    prior_leader = prior_leaders(y)
    lab = LAB[LAB.season == y]
    reg = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
    out = []
    for t in sorted(set(reg.home_team) | set(reg.away_team)):
        tg = reg[(reg.home_team == t) | (reg.away_team == t)].sort_values("week")
        cur = None
        for k, gid in zip(tg.week, tg.game_id):
            k = int(k)
            starter = lab[(lab.game_id == gid) & (lab.team == t)].chosen
            starter = starter.iloc[0] if len(starter) else None
            if cur:
                q = cur["qb"]
                if (q, k) in st and starter != q:
                    cur["L"] += 1
                    continue
                cur["censored"] = (q, k) not in av      # neither listed nor verified available: unknown -> censored
                out.append(cur)
                cur = None
            prev = db[(db.posteam == t) & (db.week < k)]
            inc = prev.groupby("qb").n.sum().idxmax() if len(prev) else prior_leader.get(t)
            if inc is not None and starter != inc and (inc, k) in st:
                cur = dict(season=y, team=t, qb=inc, first_week=k, L=1, res=False)
            if cur is not None:
                cur["res"] = cur["res"] or st.get((cur["qb"], k)) == "RES"
        if cur:
            cur["censored"] = True
            out.append(cur)
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
