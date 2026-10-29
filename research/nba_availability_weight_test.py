"""Frozen synthetic-absence comparison; see NBA_AVAILABILITY_WEIGHT_RULE.md.
Raw inputs and row-level outcomes MUST stay in the private output directory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import nba as N
import nba_avail as A
import nba_backtest as B
import nba_title_backtest as T
from nba_avail_futures_test import synthetic_report

SEEDS = (20261029, 20261030)
YEARS = [y for y in range(2013, 2027) if y != 2020]


def inputs(folder, reuse):
    folder.mkdir(parents=True, exist_ok=True)
    jobs = []
    for y in range(2009, 2027):
        for tag, stem in (("espn_nba_team_boxscores", "team_box"), ("espn_nba_player_boxscores", "player_box")):
            jobs.append((tag, f"{stem}_{y}.csv"))
    jobs += [("espn_nba_schedules", f"nba_schedule_{y}.csv") for y in YEARS]
    def one(job):
        tag, name = job
        path = folder / name
        shared = reuse / name
        if not path.exists():
            if shared.exists():
                path.write_bytes(shared.read_bytes())
            else:
                url = f"{N.RELEASE}/{tag}/{name}"
                with urllib.request.urlopen(url, timeout=120) as r:
                    data = r.read()
                path.write_bytes(data)
        return dict(name=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = list(pool.map(one, jobs))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def run(folder, output):
    N.OVERRIDES_ON = False
    boxes = pd.concat([pd.read_csv(folder / f"team_box_{y}.csv", low_memory=False) for y in range(2009, 2027)])
    player_cache = {}
    rows = []
    default_rng = np.random.default_rng
    for y in YEARS:
        needed = set(range(y - 4, y + 1))
        for s in list(player_cache):
            if s not in needed:
                del player_cache[s]
        for s in needed:
            if s not in player_cache:
                player_cache[s] = pd.read_csv(folder / f"player_box_{s}.csv", low_memory=False)
        players = pd.concat([player_cache[s] for s in sorted(needed)])
        players["date"] = pd.to_datetime(players.game_date)
        schedule = N._schedule(pd.read_csv(folder / f"nba_schedule_{y}.csv", low_memory=False))
        games = B.season_games(boxes, y)
        outcome = T.outcomes(boxes, y)
        if outcome is None:
            raise ValueError(f"Missing outcomes {y}")
        for c in (.2, .4, .6, .8):
            k = round(c * len(games))
            cutoff = games.date.iloc[k - 1]
            tr = boxes[(pd.to_numeric(boxes.season) < y) |
                       ((pd.to_numeric(boxes.season) == y) & boxes.game_id.isin(set(games.gid.iloc[:k])))]
            ratings, fit = N._fit_ratings(tr, y, current_weight=8.)
            ratings["rating"] = ratings.raw_net - ratings.raw_net.mean()
            N.HFA = fit["home_offense_points_per_100"] if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).to_numpy(float)
            sched = schedule.copy()
            sched["completed"] = sched.completed & (pd.to_datetime(sched.game_date) <= cutoff)
            past = players[players.date <= cutoff]
            report = synthetic_report(past, cutoff, y)
            for weight in (4, 8):
                with patch.dict(A.RATING_W, {0: float(weight)}):
                    values = A.player_values(past, y, today=cutoff.date())
                plan = A.plan(sched, report, values, N.NAMES, today=cutoff.date())
                for seed in SEEDS:
                    with patch.object(N.np.random, "default_rng", side_effect=lambda *args, seed=seed, **kw: default_rng(seed)):
                        result = N._simulate(sched, ratings, 2000, plan, playin=y >= 2021, season_games=72 if y == 2021 else 82)
                    for team, v in result.items():
                        rows.append(dict(season=y, check=c, weight=weight, seed=seed, team=team,
                                         p_title=v["p_title"], p_conf=v["p_conf"], p_playoff=v["p_playoff"],
                                         y_title=int(team == outcome["champ"]), y_conf=int(team in outcome["finalists"]),
                                         y_playoff=int(team in outcome["playoffs"]), episodes=len(plan["episodes"])))
            print(f"finished {y} checkpoint {c}", flush=True)
            pd.DataFrame(rows).to_csv(output / "paired_predictions.csv.gz", index=False)
    return pd.DataFrame(rows)


def score(data):
    markets = ("title", "conf", "playoff")
    avg = data.groupby(["season", "check", "weight", "team"], as_index=False).mean(numeric_only=True)
    def losses(d):
        parts = []
        for m in markets:
            p, y = d["p_" + m].clip(.002, .998), d["y_" + m]
            parts.append(d.assign(market=m, loss=-(y * np.log(p) + (1-y) * np.log(1-p))))
        return pd.concat(parts).groupby(["season", "weight", "market"]).loss.mean().unstack("weight")
    l = losses(avg)
    delta = (l[4] - l[8]).unstack("market")
    primary = delta.drop(index=2021)
    combined = primary.mean(axis=1)
    rng = np.random.default_rng(20261029)
    draws = rng.choice(combined.to_numpy(), size=(10000, len(combined)), replace=True).mean(axis=1)
    interval = np.quantile(draws, [.025, .975]).tolist()
    seeds = {}
    for seed in SEEDS:
        sl = losses(data[data.seed == seed])
        seeds[str(seed)] = float((sl[4] - sl[8]).loc[lambda x: x.index.get_level_values("season") != 2021].mean())
    gates = dict(positive_ci=interval[0] > 0, seasons_better=int((combined > 0).sum()) >= 8,
                 no_market_worse=bool((primary.mean() >= 0).all()), both_seeds_positive=all(x > 0 for x in seeds.values()),
                 sensitivity_positive=float(delta.mean(axis=1).mean()) > 0, complete_seasons=len(primary) == 12)
    return dict(label="synthetic undated-absence engine-only development comparison", adopted=False,
                pass_gates=all(gates.values()), gates=gates, gain=float(combined.mean()), ci95=interval,
                seasons_better=int((combined > 0).sum()), seasons=len(primary), per_market_gain=primary.mean().to_dict(),
                per_season_gain=combined.to_dict(), sensitivity_gain=float(delta.mean(axis=1).mean()),
                seed_gains=seeds, season_2021_gain=float(delta.loc[2021].mean()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--reuse", required=True)
    a = p.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    try:
        inputs(out / "inputs", Path(a.reuse))
        d = run(out / "inputs", out)
        result = score(d)
    except Exception as exc:
        (out / "results.json").write_text(json.dumps(dict(status="incomplete", error=repr(exc)), indent=2))
        raise
    (out / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
