"""QB absence episodes and the data-validation gate (research/NFL_QB_AVAILABILITY_RULE.md). Run before any performance replay.
Usage: python research/nfl_qb_episodes.py   -> research/nfl_qb_episodes.csv, research/nfl_qb_validation.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import FIX, download, load_pbp  # noqa: E402

SEASONS = range(2009, 2026)
KNOWN = [  # (season, team, name fragment, first missed week, class, return week or None=censored) -- fixed in the rule
    (2017, "GB", "Rodgers", 7, "injury", 15), (2019, "NO", "Brees", 3, "injury", 8), (2019, "PIT", "Roethlisberger", 3, "injury", None),
    (2020, "DAL", "Prescott", 6, "injury", None), (2021, "SF", "Garoppolo", 5, "injury", 7), (2022, "MIA", "Tagovailoa", 5, "injury", 7),
    (2023, "NYJ", "Rodgers", 2, "injury", None), (2023, "CIN", "Burrow", 12, "injury", None)]


def team_games(g):
    r = g[g.game_type.eq("REG")]
    h = r.assign(team=r.home_team, qb=r.home_qb_id, qbname=r.home_qb_name)
    a = r.assign(team=r.away_team, qb=r.away_qb_id, qbname=r.away_qb_name)
    t = pd.concat([h, a])[["season", "week", "game_id", "gameday", "team", "qb", "qbname"]]
    t["team"] = t.team.replace(FIX)
    return t.sort_values(["season", "team", "week"]).reset_index(drop=True)


def load_season(y):
    inj = pd.read_csv(download(f"injuries/injuries_{y}.csv", required=False, max_age_h=1e6), low_memory=False)
    inj = inj[inj.game_type.eq("REG")] if "game_type" in inj else inj
    inj["team"] = inj.team.replace(FIX)
    ros = pd.read_csv(download(f"weekly_rosters/roster_weekly_{y}.csv", required=False, max_age_h=1e6), low_memory=False)
    ros = ros[ros.game_type.eq("REG")] if "game_type" in ros else ros
    ros["team"] = ros.team.replace(FIX)
    return inj, ros


def classify(y, wk, team, inc, inj, ros):
    i = inj[(inj.week == wk) & (inj.gsis_id == inc)]
    if len(i):
        r = i.iloc[0]
        if str(r.report_status) in ("Out", "Doubtful", "Questionable") and "not injury related" not in str(r.report_primary_injury).lower():
            return "injury"
    ro = ros[(ros.week == wk) & (ros.gsis_id == inc)]
    if len(ro):
        if (ro.team != team).any() or ro.status.isin(["CUT", "TRD", "RET"]).any():
            return "departure"
        if ro.status.eq("ACT").any():
            return "benching"
        return "ambiguous"
    return "ambiguous"


def episodes(t):
    out = []
    for y in SEASONS:
        inj, ros = load_season(y)
        for team, z in t[t.season == y].groupby("team"):
            z = z.sort_values("week").reset_index(drop=True)
            inc, incname = z.qb.iloc[0], z.qbname.iloc[0]
            open_ep = None
            for k, r in z.iterrows():
                if open_ep is None and r.qb != inc:
                    open_ep = dict(season=y, team=team, incumbent=inc, incumbent_name=incname, start_week=int(r.week), start_index=k,
                                   replacement=r.qb, replacement_name=r.qbname, cls=classify(y, int(r.week), team, inc, inj, ros), missed=0)
                if open_ep is not None:
                    if r.qb == inc:
                        open_ep.update(return_week=int(r.week), censored=False); out.append(open_ep); open_ep = None
                    else:
                        open_ep["missed"] += 1
            if open_ep is not None:
                open_ep.update(return_week=None, censored=True); out.append(open_ep)
    return pd.DataFrame(out)


def validate(t, E):
    res = {}
    # 1 starter ids
    cov = t.qb.notna().mean()
    agree = []
    for y in SEASONS:
        p = load_pbp(y)
        p = p[(p.season_type == "REG") & (p.qb_dropback == 1)] if "season_type" in p else p[p.qb_dropback == 1]
        p = p.assign(qb=p.passer_player_id.fillna(p.rusher_player_id), posteam=p.posteam.replace(FIX))
        lead = p.groupby(["game_id", "posteam"]).qb.agg(lambda x: x.value_counts().index[0]).rename("lead").reset_index()
        m = t[t.season == y].merge(lead, left_on=["game_id", "team"], right_on=["game_id", "posteam"], how="left")
        agree.append((m.qb == m.lead).mean())
    res["1_starter_ids"] = dict(coverage=float(cov), agreement_with_dropback_leader=float(np.mean(agree)), min_season_agreement=float(np.min(agree)),
                                passes=bool(cov >= .99 and np.mean(agree) >= .90))
    # 2 injury reports, 3 rosters
    wk_ok, qb_ok, ros_ok, found = [], [], [], []
    for y in SEASONS:
        inj, ros = load_season(y)
        weeks = sorted(t[t.season == y].week.unique())
        wk_ok += [w in set(inj.week) for w in weeks]
        qb_ok += [((inj.week == w) & (inj.position == "QB")).any() for w in weeks]
        ros_ok += [w in set(ros.week) for w in weeks]
        e = E[E.season == y]
        found += [((ros.week == r.start_week) & (ros.gsis_id == r.incumbent)).any() for r in e.itertuples()]
    res["2_injury_reports"] = dict(weeks_present=float(np.mean(wk_ok)), weeks_with_qb_listing=float(np.mean(qb_ok)),
                                   passes=bool(np.mean(wk_ok) == 1 and np.mean(qb_ok) >= .95))
    res["3_rosters"] = dict(weeks_present=float(np.mean(ros_ok)), incumbent_found_share=float(np.mean(found)),
                            passes=bool(np.mean(ros_ok) == 1 and np.mean(found) >= .95))
    # 4 known cases
    cases, off_by_one, wrong, not_injury = [], 0, 0, 0
    for y, team, name, wk, cls, ret in KNOWN:
        e = E[(E.season == y) & (E.team == team) & E.incumbent_name.fillna("").str.contains(name)]
        e = e.iloc[(e.start_week - wk).abs().argsort()[:1]] if len(e) else e
        if not len(e):
            cases.append(dict(case=f"{y} {team} {name}", found=False)); wrong += 1; not_injury += 1; continue
        r = e.iloc[0]
        dw = abs(int(r.start_week) - wk)
        dr = 0 if (ret is None and r.censored) else (abs(int(r.return_week) - ret) if (ret is not None and not r.censored) else 99)
        ok_cls = r.cls == cls
        not_injury += int(not ok_cls)
        exact = dw == 0 and dr == 0 and ok_cls
        near = ok_cls and dw <= 1 and dr <= 1 and not exact
        off_by_one += int(near); wrong += int(not exact and not near)
        cases.append(dict(case=f"{y} {team} {name}", found=True, start_week=int(r.start_week), expected_start=wk, cls=r.cls,
                          return_week=None if r.censored else int(r.return_week), expected_return=ret, exact=bool(exact), within_one=bool(near)))
    res["4_known_cases"] = dict(cases=cases, off_by_one=off_by_one, wrong=wrong, not_classified_injury=not_injury,
                                passes=bool(wrong == 0 and off_by_one <= 1), relabel_qb_role=bool(not_injury > 2))
    # 6 counts
    cnt = E.groupby(["cls"]).size().to_dict()
    res["6_counts"] = dict(episodes_by_class=cnt, injury_episodes=int(cnt.get("injury", 0)),
                           censored_share_injury=float(E[E.cls == "injury"].censored.mean()) if cnt.get("injury") else None,
                           by_season=E.groupby(["season", "cls"]).size().unstack(fill_value=0).to_dict("index"),
                           inconclusive_too_few=bool(cnt.get("injury", 0) < 40))
    res["5_timing"] = dict(note="Uses schedules' starter fields for games already played, the injury report and weekly roster of weeks <= checkpoint; "
                                "weekly labels are reconstructed/revised history, not an archived point-in-time feed.", passes=True)
    res["gate_passes"] = bool(all(res[k]["passes"] for k in ("1_starter_ids", "2_injury_reports", "3_rosters", "4_known_cases", "5_timing"))
                              and not res["6_counts"]["inconclusive_too_few"] and not res["4_known_cases"]["relabel_qb_role"])
    return res


def main():
    g = pd.read_csv(download("schedules/games.csv"), low_memory=False)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    t = team_games(g[g.season.isin(list(SEASONS))])
    E = episodes(t)
    E.to_csv(os.path.join(ROOT, "research", "nfl_qb_episodes.csv"), index=False)
    res = validate(t, E)
    open(os.path.join(ROOT, "research", "nfl_qb_validation.json"), "w").write(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "6_counts"} | {"counts": {k: v for k, v in res["6_counts"].items() if k != "by_season"}},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
