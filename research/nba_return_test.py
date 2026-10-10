"""How long do NBA rotation players listed OUT stay out? Live recovery rules vs earlier-season data (research only).

Observations: every regular-season game 2019-20..2025-26 at which a rotation player (12+ minutes over his last 10 games
played, from games before the report) is listed Out on the latest official report published 60+ minutes before
tip-off (research/nba_official_pregame.py). Outcome: still out at the team's 1st, 3rd, 5th, 10th and 20th next game; an
absence ends at the first game he plays; censored at season end or when he appears for another team.

Predictors of P(still out at the k-th next game):
  live      the live rule when ESPN gives no return date (pipeline/nba_avail.py): return day lognormal around 14 days
            (90 days if the injury text says season / ACL / Achilles / surgery), sigma 0.9, counted from TODAY - the
            countdown restarts at every report
  live_upd  the same distribution counted from the start of the absence, conditioned on him still being out:
            P(T > e + d | T > e)
  empirical share still out at game k among earlier seasons' observations of the same class and games-already-missed
            bucket (walk-forward: fitted on seasons before the test season)
Classes from the official reason text: long (season / ACL / Achilles / surgery, as the live rule), injury (other
Injury/Illness), non_injury (rest, personal reasons, suspension, not with team, protocols, G League).
Not tested here: ESPN's dated return estimates (only archived from October 2026 on).
Usage: python research/nba_return_test.py <dir with pregame_*.csv.gz> <out.json>
"""
import bisect
import collections
import glob
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba_availability2 as V2  # noqa: E402
import nba_avail as LIVE  # noqa: E402
import nba_official as O  # noqa: E402

HORIZONS = (1, 3, 5, 10, 20)
BUCKETS = ((0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, 10 ** 6))


def bucket(e):
    return next(i for i, (lo, hi) in enumerate(BUCKETS) if lo <= e <= hi)


def klass(reason):
    r = reason if isinstance(reason, str) else ""
    if LIVE.LONG_TERM.search(r):
        return "long"
    if re.search(r"Injury/Illness|Sprain|Strain|Contusion|Soreness|Fracture|Tear|Concussion|Rehab|Tendin|Management|Surgery|Illness", r, re.I) \
            and not re.match(r"\s*(G League|Personal|League Suspension|Not With Team|Rest|Trade|Health and Safety|Suspension)", r, re.I):
        return "injury"
    return "non_injury"


def live_out(dd, cls, elapsed_days=0.0, update=False):
    """P(still out dd days after the report) under the live undated rule."""
    med = LIVE.LONG_TERM_DAYS if cls == "long" else LIVE.NO_DATE_DAYS
    s = LIVE.NO_DATE_SIGMA
    sf = lambda x: 1.0 - norm.cdf((math.log(max(x, 1e-6)) - math.log(med)) / s)
    if not update:
        return sf(dd)
    return sf(elapsed_days + dd) / max(sf(elapsed_days), 1e-9)


def main(folder, out_path):
    d = V2.load()
    d = d[d.season >= 2019].copy()
    d["athlete_id"] = d.athlete_id.astype(str)
    d["gid"] = d.game_id.astype(str)
    # team schedules (games with box scores), who played, and each player's row history (for censoring by team change)
    tg = d.drop_duplicates(["gid", "team_abbreviation"]).sort_values("date")
    sched = {k: list(zip(v.date, v.gid)) for k, v in tg.groupby(["team_abbreviation", "season"])}
    played = d[d.played].groupby(["gid", "team_abbreviation"]).athlete_id.agg(set).to_dict()
    rows_by_p = {p: list(zip(v.date, v.team_abbreviation)) for p, v in d.sort_values("date").groupby("athlete_id")}
    # minutes in games played, in order, for the rotation filter
    mins_by_p = {p: (list(v.date), list(v.minutes)) for p, v in d[d.played].sort_values("date").groupby("athlete_id")}
    names = d.drop_duplicates(["season", "athlete_id"])
    key = collections.defaultdict(set)
    for r in names.itertuples():
        key[(r.season, O.name_key(r.athlete_display_name))].add(r.athlete_id)

    P = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(folder, "pregame_*.csv.gz")))], ignore_index=True)
    P = P[(P.status == "Out") & P.player.notna()]
    P["gid"] = P.game_id.astype(str)
    obs, unmatched = [], 0
    for r in P.itertuples():
        ids = key.get((int(r.season), O.player_key(r.player)), set())
        if len(ids) != 1:
            unmatched += 1
            continue
        p = next(iter(ids))
        sc = sched.get((r.team, int(r.season)))
        if not sc:
            continue
        gids = [g for _, g in sc]
        if r.gid not in gids:
            continue
        i = gids.index(r.gid)
        d0 = sc[i][0]
        # rotation filter from games before the report
        md, mm = mins_by_p.get(p, ([], []))
        j = bisect.bisect_left(md, d0)
        last = mm[max(0, j - 10):j]
        if not last or sum(last) / len(last) < 12:
            continue
        # games already missed (streak) and days since the absence began
        e, k = 0, i - 1
        while k >= 0 and p not in played.get((gids[k], r.team), set()):
            e += 1
            k -= 1
        start_date = sc[k + 1][0] if e else d0
        elapsed_days = (d0 - start_date).days
        # outcome path: still out at next games until he plays; censor at a team change or season end
        hist = rows_by_p.get(p, [])
        hd = [h_[0] for h_ in hist]
        first_other = None
        for dt_, t in hist[bisect.bisect_right(hd, d0):]:
            if t != r.team:
                first_other = dt_
                break
        path = []
        for step in range(1, max(HORIZONS) + 1):
            if i + step >= len(sc):
                break
            dk, gk = sc[i + step]
            if first_other is not None and first_other <= dk:
                break
            out_k = p not in played.get((gk, r.team), set())
            path.append(((dk - d0).days, out_k))
            if not out_k:
                break
        days = [(sc[i + step][0] - d0).days for step in range(1, max(HORIZONS) + 1) if i + step < len(sc)]
        obs.append(dict(season=int(r.season), pid=p, team=r.team, gid=r.gid, cls=klass(r.reason), e=e, b=bucket(e),
                        elapsed_days=elapsed_days, path=path, days=days))
    O_ = pd.DataFrame(obs)
    print("observations", len(O_), "unmatched names", unmatched, flush=True)

    def outcome(path, h):
        """1 = still out at the h-th next game, 0 = back by then, None = censored before h."""
        if len(path) >= h:
            return int(all(o for _, o in path[:h]))
        if path and not path[-1][1]:
            return 0
        return None

    for h in HORIZONS:
        O_[f"y{h}"] = O_.path.map(lambda p, h=h: outcome(p, h))
        O_[f"dd{h}"] = O_.days.map(lambda v, h=h: v[h - 1] if len(v) >= h else None)   # date of the team's h-th next game
    seasons = sorted(O_.season.unique())
    test_seasons = seasons[2:]
    res = {"observations": int(len(O_)), "absences": int(O_.groupby(["pid", "team", "season"]).ngroups), "unmatched_report_rows": unmatched,
           "class_counts": O_.cls.value_counts().to_dict(), "test_seasons": [int(s) for s in test_seasons], "horizons": {}}
    for h in HORIZONS:
        y, dd = f"y{h}", f"dd{h}"
        x = O_[O_[y].notna() & O_[dd].notna()].copy()
        x[y] = x[y].astype(int)
        x["p_live"] = [live_out(a, c) for a, c in zip(x[dd], x.cls)]
        x["p_upd"] = [live_out(a, c, ed, True) for a, c, ed in zip(x[dd], x.cls, x.elapsed_days)]
        x["p_emp"] = np.nan
        for s in test_seasons:
            tr = x[x.season < s]
            tab = tr.groupby(["cls", "b"])[y].agg(["sum", "size"])
            cls_tab = tr.groupby("cls")[y].agg(["sum", "size"])
            def emp(c, b):
                if (c, b) in tab.index and tab.loc[(c, b), "size"] >= 30:
                    t = tab.loc[(c, b)]
                else:
                    t = cls_tab.loc[c] if c in cls_tab.index else pd.Series({"sum": 1, "size": 2})
                return (t["sum"] + 1) / (t["size"] + 2)
            m = x.season == s
            x.loc[m, "p_emp"] = [emp(c, b) for c, b in zip(x.loc[m, "cls"], x.loc[m, "b"])]
        t = x[x.season.isin(test_seasons)]

        def sc_(p, yy):
            p = np.clip(p, 1e-3, 1 - 1e-3)
            return {"brier": round(float(np.mean((p - yy) ** 2)), 4), "log_loss": round(float(-np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p))), 4)}
        e = {"n": int(len(t)), "actual_still_out": round(float(t[y].mean()), 3)}
        for nm in ("p_live", "p_upd", "p_emp"):
            e[nm] = {**sc_(t[nm].values, t[y].values), "mean_pred": round(float(t[nm].mean()), 3)}
        e["by_class"] = {}
        for c, z in t.groupby("cls"):
            e["by_class"][c] = {"n": int(len(z)), "actual": round(float(z[y].mean()), 3),
                                **{nm: {**sc_(z[nm].values, z[y].values), "mean_pred": round(float(z[nm].mean()), 3)} for nm in ("p_live", "p_upd", "p_emp")}}
        e["by_elapsed_bucket"] = {f"{BUCKETS[b][0]}-{BUCKETS[b][1] if BUCKETS[b][1] < 10 ** 5 else '+'}": {
            "n": int(len(z)), "actual": round(float(z[y].mean()), 3), "live": round(float(z.p_live.mean()), 3),
            "live_upd": round(float(z.p_upd.mean()), 3), "empirical": round(float(z.p_emp.mean()), 3)} for b, z in t.groupby("b")}
        e["by_season"] = {int(s): {"n": int(len(z)), **{nm: sc_(z[nm].values, z[y].values)["brier"] for nm in ("p_live", "p_upd", "p_emp")}}
                          for s, z in t.groupby("season")}
        res["horizons"][h] = e
    json.dump(res, open(out_path, "w"), indent=1)
    if os.environ.get("FREEZE_TABLE"):
        # frozen challenger: the same empirical table fitted on ALL collected seasons, for prospective testing only
        tab = {}
        for h in HORIZONS:
            y = f"y{h}"
            x = O_[O_[y].notna()]
            g = x.groupby(["cls", "b"])[y].agg(["sum", "size"])
            gc = x.groupby("cls")[y].agg(["sum", "size"])
            for c in ("long", "injury", "non_injury"):
                for b in range(len(BUCKETS)):
                    t = g.loc[(c, b)] if (c, b) in g.index and g.loc[(c, b), "size"] >= 30 else gc.loc[c]
                    tab.setdefault(c, {}).setdefault(str(b), {})[str(h)] = round(float((t["sum"] + 1) / (t["size"] + 2)), 4)
        json.dump({"version": "returns-v1 (frozen " + pd.Timestamp.utcnow().strftime("%Y-%m-%d") + ")",
                   "fitted_on": [int(s) for s in seasons], "horizons": list(HORIZONS),
                   "buckets_games_already_missed": [list(b) for b in BUCKETS], "classes": "long / injury / non_injury (see research/nba_return_test.py)",
                   "p_still_out": tab}, open(os.environ["FREEZE_TABLE"], "w"), indent=1)
    print(json.dumps({h: {k: v for k, v in e.items() if k in ("n", "actual_still_out", "p_live", "p_upd", "p_emp")} for h, e in res["horizons"].items()}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
