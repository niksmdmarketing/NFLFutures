"""Run the whole pipeline: fresh data -> ratings -> simulation -> awards -> matchups -> stats -> site."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import awards  # noqa: E402
import afl  # noqa: E402
import build_site  # noqa: E402
import matchups  # noqa: E402
import nba  # noqa: E402
import nbl  # noqa: E402
import nhl  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
import simulate_v3  # noqa: E402
import stats  # noqa: E402
from common import OUT, TEAMS, current_season, games, load_pbp, log, write_json  # noqa: E402


def _track_record():
    """Per-market point-in-time test of the futures model (built offline by pipeline/nfl_backtest.py)."""
    from common import MODEL
    p = os.path.join(MODEL, "futures_backtest.json")
    return json.load(open(p)) if os.path.exists(p) else None


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
                                "track_record": _track_record(), "challenger": challenger})
    write_json("awards.json", awards.build(season, g, res, injuries))
    log("awards done")
    import award_race, players  # noqa: E401
    players.build_all(season)
    log("players done")
    write_json("award_race.json", award_race.build(season, g, json.load(open(os.path.join(OUT, "awards.json")))))
    log("award race done")
    write_json("matchups.json", {**matchups.build(season, g, cur, pri), "complete_week": through, "next_week": next_week})
    log("matchups done")
    for name, page in stats.build_all(season, g, cur, R, injuries).items():
        write_json(f"page_{name}.json", page)
    log("stats pages done")
    nba.build_data()
    nbl.build_data()
    nhl.build_data()
    try:
        afl.build_data()
    except Exception as e:  # noqa: BLE001
        log("afl data failed", e)
    build_site.build()
    nba.build_site()
    nbl.build_site()
    nhl.build_site()
    try:  # AFL is new and downloads a large archive; never let it block the other sports
        afl.build_site()
    except Exception as e:  # noqa: BLE001
        log("afl site failed", e)
    for mod in ("nba_site", "nbl_site", "afl_site"):  # NBA and AFL pages on the shared engine (replace the older page designs)
        try:
            m = __import__(mod)
            m.build_data()
            m.build_site()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            log(mod, "failed", e)
    try:  # winner trends read the data written above; never let them block the refresh
        import trends
        trends.build_data()
        trends.build_site()
    except Exception as e:  # noqa: BLE001
        log("trends failed", e)
    try:  # schedule difficulty pages need every sport's ratings and fixtures, so they run after the sport builds
        import sos
        sos.build_data()
        sos.build_site()
    except Exception as e:  # noqa: BLE001
        log("schedule outlook failed", e)
    try:  # private research dataset + leakage/coverage report: written to data/research, never published
        import snapshots
        snapshots.build_all()
    except Exception as e:  # noqa: BLE001
        log("snapshots failed", e)
    # Cloudflare Pages rejects the whole deployment if any file is over 25 MiB: drop such files loudly instead
    for dirpath, _, files in os.walk(os.path.join(os.path.dirname(OUT), "site")):
        for fn in files:
            fp = os.path.join(dirpath, fn)
            if os.path.getsize(fp) > 24 * 1024 * 1024:
                log("WARNING: removing oversized file from the site", fp, os.path.getsize(fp))
                os.remove(fp)
    log("site built")


if __name__ == "__main__":
    main()
