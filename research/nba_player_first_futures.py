"""Amendment 1, Test 2: futures replay with the player-first term (BT_PF=1) vs the committed live replay (model/replay/nba_<y>.csv)."""
import json, os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PF = sys.argv[1]
MK = [("title", "title"), ("conf", "finals"), ("div", "div"), ("seed1", "seed1"), ("playoff", "playoff")]


def ll(p, y):
    p = np.clip(p, .003, .997)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


rows = []
for y in [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]:
    a = pd.read_csv(os.path.join(ROOT, "model", "replay", f"nba_{y}.csv"))
    b = pd.read_csv(os.path.join(PF, f"nba_{y}.csv"))
    assert len(a) == len(b)
    r = {"season": y}
    for k, o in MK:
        r[f"base_{k}"], r[f"pf_{k}"] = ll(a["p_" + k], a["y_" + o]), ll(b["p_" + k], b["y_" + o])
    r["base"] = np.mean([r[f"base_{k}"] for k, _ in MK])
    r["pf"] = np.mean([r[f"pf_{k}"] for k, _ in MK])
    rows.append(r)
R = pd.DataFrame(rows)
g = (R.base - R.pf).to_numpy()
rng = np.random.default_rng(6)
bs = [g[rng.integers(0, len(g), len(g))].mean() for _ in range(2000)]
out = {"seasons": R.season.tolist(), "base": round(float(R.base.mean()), 4), "pf": round(float(R.pf.mean()), 4), "gain": round(float(g.mean()), 4),
       "ci90": [round(float(np.percentile(bs, 5)), 4), round(float(np.percentile(bs, 95)), 4)], "seasons_better": int((g > 0).sum()),
       "by_market": {k: {"base": round(float(R[f"base_{k}"].mean()), 4), "pf": round(float(R[f"pf_{k}"].mean()), 4)} for k, _ in MK},
       "by_season": {int(s): round(float(x), 4) for s, x in zip(R.season, g)}}
worst = max(out["by_market"][k]["pf"] - out["by_market"][k]["base"] for k, _ in MK)
out["gates"] = {"ci_above_0": out["ci90"][0] > 0, "7_of_11": out["seasons_better"] >= 7, "no_market_worse_than_0.002": worst <= 0.002}
out["pass"] = all(out["gates"].values())
json.dump(out, open(os.path.join(ROOT, "research", os.environ.get("PF_OUT", "nba_player_first_futures_results.json")), "w"), indent=1)
print(json.dumps(out, indent=1))
