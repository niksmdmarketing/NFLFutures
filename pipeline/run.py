"""Run the whole pipeline: fresh data -> ratings -> simulation -> awards -> matchups -> stats -> site."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import awards  # noqa: E402
import build_site  # noqa: E402
import matchups  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
import simulate_v3  # noqa: E402
import stats  # noqa: E402
from common import TEAMS, current_season, games, load_pbp, log, write_json  # noqa: E402


def main():
    g = games()
    season = current_season(g)
    log("season", season)
    cur, pri, pri2 = load_pbp(season), load_pbp(season - 1), load_pbp(season - 2)
    greg_all = g[(g.season == season) & (g.game_type == "REG")]
    by_week = greg_all.groupby("week").result.agg(lambda r: (int(r.notna().sum()), len(r)))
    done_weeks = [int(w) for w, (d, n) in by_week.items() if d == n]
    open_weeks = [int(w) for w, (d, n) in by_week.items() if d < n]
    through = max([w for w in done_weeks if not open_weeks or w < min(open_weeks)], default=0)
    next_week = min(open_weeks) if open_weeks else None
    played_next = int(by_week.get(next_week, (0, 0))[0]) if next_week else 0
    log("play-by-play loaded; complete weeks through", through, "next week", next_week, "games played in it", played_next)

    R, comp, injuries = ratings.team_ratings(season, g, cur, pri, pri2)
    S = ratings.S["sim"]
    greg = g[(g.season == season) & (g.game_type == "REG")]
    Rv = R.rating.reindex(TEAMS).values
    n_sims = int(os.environ.get("N_SIMS", S["n_sims"]))
    res = simulate.simulate(greg, Rv, n_sims, S["tau"], S["sigma"], S["hfa"])
    log("simulation done")
    C = ratings.S.get("challenger")
    challenger = None
    if C:
        Rc = (R.base + R.qb_adj).reindex(TEAMS).values
        Rc = Rc - Rc.mean()
        rc = simulate_v3.simulate(greg, Rc, int(os.environ.get("N_SIMS_CHALLENGER", C["n_sims"])), C["tau"], C["sigma"], C["hfa"])
        challenger = {"name": C["name"], "teams": {t: {"rating": round(float(Rc[i]), 2), "mean_wins": round(float(rc["wins"][:, i].mean()), 2),
                                                        **{k: round(float(rc[k.replace("p_", "")][i]), 4) for k in ("p_div", "p_playoff", "p_seed1", "p_conf", "p_sb")}}
                                                    for i, t in enumerate(TEAMS)}}
        log("challenger simulation done")
    now = dt.datetime.now(dt.timezone.utc)
    meta = {"season": season, "through_week": through, "next_week": next_week, "next_week_played": played_next, "updated_utc": now.isoformat(timespec="minutes"),
            "injury_week": int(injuries.week.max()) if injuries is not None and len(injuries) else None,
            "model": ratings.S["version"], "n_sims": n_sims}
    write_json("meta.json", meta)
    write_json("futures.json", {"season": season, "through_week": through,
                                "teams": simulate.futures_table(res, Rv, R),
                                "track_record": ratings.S.get("track_record"), "challenger": challenger})
    write_json("awards.json", awards.build(season, g, res, injuries))
    log("awards done")
    write_json("matchups.json", {**matchups.build(season, g, cur, pri), "complete_week": through, "next_week": next_week})
    log("matchups done")
    for name, page in stats.build_all(season, g, cur, R, injuries).items():
        write_json(f"page_{name}.json", page)
    log("stats pages done")
    build_site.build()
    log("site built")


if __name__ == "__main__":
    main()
