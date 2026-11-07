"""Scores research/NHL_SERIES_CALIBRATION_RULE.md Stage 1 (Amendments 1-4). Usage: python research/nhl_series_score.py <series dir> <arms A_live dir> [out.json]
Wild cluster score bootstrap on 9 season clusters, all 2^9 = 512 Rademacher sign patterns (exact, no seed)."""
import glob
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nhl_po_scale_score as S  # noqa: E402

FLOOR, MDE = 0.10, 1.24


def fit(x, y, b0=(0.0, 1.0)):
    X = np.column_stack([np.ones(len(x)), x]); b = np.array(b0, float)
    for _ in range(80):
        mu = 1 / (1 + np.exp(-X @ b)); W = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-9 * np.eye(2), X.T @ (y - mu)); b = b + step
        if np.abs(step).max() < 1e-10:
            break
    return b, X, mu, W


def wild(q, y, cl):
    q = np.clip(np.asarray(q, float), 0.002, 0.998); y = np.asarray(y, float)
    x = np.log(q / (1 - q)); b, X, mu, W = fit(x, y)
    H = X.T @ (X * W[:, None]); Hi = np.linalg.inv(H)
    ids = sorted(set(cl)); sc = np.array([(X[np.asarray(cl) == c] * (y - mu)[np.asarray(cl) == c, None]).sum(0) for c in ids])
    draws = [b[1] + (Hi @ (np.array(w) @ sc))[1] for w in itertools.product((-1, 1), repeat=len(ids))]
    return float(b[1]), float(np.percentile(draws, 5)), float(np.percentile(draws, 95))


def verdict(sl, lo, hi):
    return {"slope": sl, "lo90": lo, "hi90": hi, "half_width": (hi - lo) / 2, "excludes_1": bool(lo > 1 or hi < 1),
            "direction": "underconfident (>1)" if sl > 1 else "overconfident (<1)"}


def main(ser_dir, arm_dir, out=None):
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(ser_dir, "*", "series_*.csv")))], ignore_index=True)
    res = {"series": {}, "companion": {}}
    fq = D[(D.label == "wk") & (D.gp_avg >= 0.082) & (D.gp_avg < 20.5)]
    fq = fq[fq.checkpoint == fq.groupby("season").checkpoint.transform("min")]
    for name, d in (("pre", D[D.label == "pre"]), ("fq", fq), ("end", D[D.label == "end"])):
        res["series"][name] = {"n": int(len(d)), **verdict(*wild(d.q, d.home_won, d.season.values))}
    L = S.load(arm_dir)
    for name, st in (("pre", "preseason"), ("fq", "first quarter")):
        d = S.stage(L, st)
        res["companion"][name] = {"playoff": verdict(*wild(d.p_playoff, d.y_playoff, d.season.values)),
                                  "division": verdict(*wild(d.p_div, d.y_div, d.season.values))}
    ser, comp = res["series"]["pre"], res["companion"]["pre"]["playoff"]
    disp = abs(ser["slope"] - 1)
    if ser["half_width"] > MDE and not ser["excludes_1"]:
        v = "Insufficient"
    elif not ser["excludes_1"]:
        v = "Calibrated (interval contains 1 and half-width within the minimum detectable movement)"
    elif disp < FLOOR:
        v = "Detectable but trivial, no authorisation"
    elif comp["excludes_1"] and (comp["slope"] > 1) == (ser["slope"] > 1):
        v = "Inherited from the ratings, Stage 2 not authorised"
    elif comp["excludes_1"]:
        v = "Opposite directions, no authorisation"
    else:
        v = "Series-channel defect, Stage 2 may be proposed"
    fqd = res["series"]["fq"]
    if v.startswith("Series-channel") and (fqd["slope"] > 1) != (ser["slope"] > 1):
        v = "Insufficient (first quarter downgrades)"
    res["verdict"] = v
    print(json.dumps(res, indent=1))
    if out:
        json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
