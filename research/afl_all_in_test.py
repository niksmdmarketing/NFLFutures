"""AFL all-in test per research/AFL_ALL_IN_RULE.md. Usage: python afl_all_in_test.py <clean_dir> [--out afl_all_in_results.json]"""
import json
import sys

import numpy as np
import pandas as pd

import afl_three_way_test as TW

FIT, TEST = [2021, 2022], [2023, 2024, 2025, 2026]


def main(clean, outp):
    M, base, ex = TW.predictions(clean)
    # X rating on expected-score margin, 2021 on
    sub = M[M.season >= 2021].copy()
    sub["xm"] = (sub.home_xscore - sub.away_xscore).where(sub.home_xscore.notna() & sub.away_xscore.notna(), sub.home_score - sub.away_score)
    TW.last_ha.clear()
    xd, xh = TW.season_ratings(sub.reset_index(drop=True), lambda g: g.xm.to_numpy(float), free_home=True)
    M.loc[sub.index, "Xr"] = xd
    # earlier 50/50 expected-score mix (research/AFL_WHEELO_XSCORE_RULE.md) is a different machinery; only its reported numbers are cited.
    fit = M.season.isin(FIT)
    Xmat = np.column_stack([M.B - ex["bB"][0], M.C - ex["bC"][0], M.Xr])
    w = TW.ols(Xmat[fit], M.act[fit].to_numpy())
    M["E"] = w[0] + np.nan_to_num(Xmat) @ w[1:]
    sdE = float(np.sqrt(np.mean((M.act[fit] - M.E[fit]) ** 2)))
    sd = {"A": TW.GAME_SD, "D": float(np.sqrt(np.mean((M.act[ex["tu"]] - M.D[ex["tu"]]) ** 2))), "E": sdE,
          "B": float(np.sqrt(np.mean((M.act[ex["tu"]] - M.B[ex["tu"]]) ** 2))), "C": float(np.sqrt(np.mean((M.act[ex["tu"]] - M.C[ex["tu"]]) ** 2)))}
    T = M[M.season.isin(TEST)].reset_index(drop=True)
    se = {k: (T.act - T[k]) ** 2 for k in ["A", "B", "C", "D", "E"]}
    res = {"weights_E": {"h": float(w[0]), "wB": float(w[1]), "wC": float(w[2]), "wX": float(w[3])}, "sd": sd, "n_test": len(T),
           "mse": {k: float(v.mean()) for k, v in se.items()}, "logloss": {k: TW.logloss(T[k].to_numpy(), T.act.to_numpy(), sd[k]) for k in se}}
    rounds = T.groupby(["season", "round"]).indices
    keys = list(rounds)
    rng = np.random.default_rng(13)
    draws = [np.concatenate([rounds[keys[i]] for i in rng.integers(0, len(keys), len(keys))]) for _ in range(2000)]
    early = T["round"] <= 8
    for ref in ["D", "A"]:
        d = (se[ref] - se["E"]).to_numpy()
        bs = np.array([d[i].mean() for i in draws])
        bys = {int(y): float(d[(T.season == y).to_numpy()].mean()) for y in TEST}
        slope = float(np.polyfit(T.E, T.act, 1)[0])
        g = {"1_mse_lower90_above_0": float(np.percentile(bs, 10)) > 0, "2_three_of_four": sum(v > 0 for v in bys.values()) >= 3,
             "3_logloss": res["logloss"]["E"] < res["logloss"][ref], "4_calib": 0.8 <= slope <= 1.2}
        res[f"E_vs_{ref}"] = {"gain": float(d.mean()), "gain_pct": float(d.mean() / se[ref].mean() * 100), "lower90": float(np.percentile(bs, 10)),
                              "by_season": bys, "early": float(d[early].mean()), "late": float(d[~early].mean()), "slope": slope,
                              "gates": {k: bool(v) for k, v in g.items()}, "all_pass": bool(all(g.values()))}
    dDA = (se["A"] - se["D"]).to_numpy()
    res["D_vs_A_on_these_games"] = {"gain": float(dDA.mean()), "by_season": {int(y): float(dDA[(T.season == y).to_numpy()].mean()) for y in TEST}}
    res["best"] = "E" if res["E_vs_D"]["all_pass"] else "D"
    json.dump(res, open(outp, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "afl_all_in_results.json")
