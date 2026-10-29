"""Original-code replication; see NBA_INJURY_BASE_REPLICATION_RULE.md.
Private inputs/output only. No model files overwritten.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import numpy as np
import pandas as pd


def worker(model_root, cache, output, years):
    sys.path.insert(0, str(model_root / "research"))
    sys.path.insert(0, str(model_root / "pipeline"))
    import nba_avail_futures_test as F
    import nba as N
    def cached(tag, name, *a, **kw):
        p = cache / name
        return str(p) if p.exists() else None
    N._download = cached
    N.NBA_DATA = str(cache)
    original = F.synthetic_report
    def normalized(players, cutoff, year):
        players = players.copy()
        players["athlete_id"] = players.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
        return original(players, cutoff, year)
    F.synthetic_report = normalized
    F.SIMS = 3000
    output.mkdir(parents=True, exist_ok=False)
    frames = []
    for year in years:
        d = F.run([year])
        if len(d) != 4 * 30 * 2:
            raise ValueError("Incomplete year " + str(year))
        frames.append(d)
        pd.concat(frames).to_csv(output / "rows.csv.gz", index=False)
        print("replicated", year, flush=True)
    return pd.concat(frames, ignore_index=True)


def score(data):
    means = []
    for market in ("title", "conf", "playoff"):
        d = data.copy()
        p, y = d["p_" + market].clip(.002, .998), d["y_" + market]
        d["loss"] = -(y*np.log(p)+(1-y)*np.log(1-p))
        means.append(d.assign(market=market))
    all_rows = pd.concat(means)
    season = all_rows.groupby(["season", "market", "variant"]).loss.mean().unstack("variant")
    gain = (season["without"] - season["with"]).unstack("market")
    combined = gain.mean(axis=1)
    rng = np.random.default_rng(20261029)
    ci = np.quantile(rng.choice(combined.to_numpy(), size=(10000,len(combined))).mean(axis=1), [.025,.975]).tolist()
    gates = dict(positive_ci=ci[0] > 0, no_market_worse=bool((gain.mean() >= 0).all()),
                 seasons_better=int((combined > 0).sum()) >= 10, complete=len(gain) == 14)
    by = all_rows.groupby(["check", "market", "variant"]).loss.mean().unstack("variant")
    return dict(label="ID-corrected replication of original synthetic replay; old era limitations retained",
                production_changed=False, passes_descriptive_gates=all(gates.values()), gates=gates,
                combined_gain=float(combined.mean()), ci95=ci, per_market_gain=gain.mean().to_dict(),
                per_season_gain=combined.to_dict(), seasons_better=int((combined > 0).sum()), seasons=len(gain),
                checkpoint_market_gain={str(k):float(v) for k,v in (by["without"]-by["with"]).items()},
                original_code_commit="a35e92878f45f25e9b18f29d3222754cfb3d205f", sims=3000, simulator_seed=20261009,
                episodes=data.groupby("season").n_out.agg(["min","max"]).to_dict("index"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-root", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    model, cache, output = (Path(x).resolve() for x in (a.model_root,a.cache,a.output))
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=model,text=True).strip() != "a35e92878f45f25e9b18f29d3222754cfb3d205f":
        raise ValueError("Wrong original code version")
    output.mkdir(parents=True,exist_ok=False)
    schedule = cache / "nba_schedule_2020.csv"
    if not schedule.exists():
        url="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2020.csv"
        with urllib.request.urlopen(url,timeout=60) as r: schedule.write_bytes(r.read())
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.glob("*.csv")}
    (output/"input_hashes.json").write_text(json.dumps(manifest,indent=2))
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(worker,model,cache,output/"part1",list(range(2013,2020))),
              pool.submit(worker,model,cache,output/"part2",list(range(2020,2027)))]
        data=pd.concat([j.result() for j in jobs],ignore_index=True)
    data.to_csv(output/"paired_predictions.csv.gz",index=False)
    result=score(data)
    (output/"results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
