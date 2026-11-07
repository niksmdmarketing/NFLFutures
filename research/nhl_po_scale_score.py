"""Scores research/NHL_PO_SCALE_RULE.md (Amendments 1-3). Nothing here is tuned; settings are the rule's.
Usage: python research/nhl_po_scale_score.py <arms_dir> [out.json]
  <arms_dir>/<arm>/nhl_<season>.csv for arms: A_live (baseline), C1_t1.0_on (the only arm that can pass), and descriptive arms."""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

SEASONS = [2015, 2016, 2017, 2018, 2021, 2022, 2023, 2024, 2025]
PRIMARY, LIVE = "C1_t1.0_on", "A_live"
MDM, FQ_TOL, NOHARM = 0.65, 0.5, -0.0005
DRAWS, SEED = 10000, 20261108
LL_MARKETS = {"playoff": ("p_playoff", "y_playoff"), "div": ("p_div", "y_div"), "r2": ("p_r2", "y_r2"), "r3": ("p_r3", "y_r3"),
              "finals": ("p_conf", "y_finals"), "title": ("p_title", "y_title")}


def load(d):
    fs = [os.path.join(d, f"nhl_{y}.csv") for y in SEASONS]
    missing = [f for f in fs if not os.path.exists(f)]
    if missing:
        raise ValueError(f"missing seasons in {d}: {missing}")
    D = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1))
    return D


def slope(p, y):
    """Logistic calibration slope of y on logit(p) (Newton, intercept free). Returns nan if unidentified."""
    p = np.clip(np.asarray(p, float), 0.002, 0.998)
    y = np.asarray(y, float)
    if y.sum() == 0 or y.sum() == len(y):
        return np.nan
    X = np.column_stack([np.ones(len(p)), np.log(p / (1 - p))])
    b = np.array([0.0, 1.0])
    for _ in range(60):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-9 * np.eye(2), X.T @ (y - mu))
        b = b + step
        if np.abs(step).max() < 1e-9:
            break
    return float(b[1])


def stage(D, name):
    return D[D.week == 0] if name == "preseason" else D[(D.frac >= 0.001) & (D.frac < 0.25)]


def ll(p, y, lo=0.002):
    p = np.clip(np.asarray(p, float), lo, 1 - lo)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def season_ll(D):
    """Per season, per market mean log loss over every checkpoint; combined = equal-weight mean over markets."""
    out = {}
    for m, (pc, yc) in LL_MARKETS.items():
        out[m] = D.assign(l=ll(D[pc], D[yc])).groupby("season").l.mean()
    return pd.DataFrame(out)


def toward_one(sl_live, sl_arm):
    return abs(sl_live - 1) - abs(sl_arm - 1)


def boot(Dlive, Darm, rng):
    """Season-cluster bootstrap of: Cup-slope movement toward 1 at preseason and first quarter, and combined log-loss gain."""
    gl, ga = {s: Dlive[Dlive.season == s] for s in SEASONS}, {s: Darm[Darm.season == s] for s in SEASONS}
    ll_live, ll_arm = season_ll(Dlive), season_ll(Darm)
    gain = (ll_live - ll_arm)
    res = {"pre": [], "fq": [], "ll": []}
    for _ in range(DRAWS):
        pick = rng.choice(SEASONS, len(SEASONS))
        for st, key in (("preseason", "pre"), ("first quarter", "fq")):
            L = pd.concat([stage(gl[s], st) for s in pick]); A = pd.concat([stage(ga[s], st) for s in pick])
            sl, sa = slope(L.p_title, L.y_title), slope(A.p_title, A.y_title)
            res[key].append(toward_one(sl, sa) if np.isfinite(sl) and np.isfinite(sa) else np.nan)
        res["ll"].append(float(gain.loc[pick].mean(axis=1).mean()))
    return {k: np.array(v) for k, v in res.items()}, gain


def summarise(v):
    v = v[np.isfinite(v)]
    return {"lo90": float(np.percentile(v, 5)), "hi90": float(np.percentile(v, 95)), "draws": int(len(v))}


def arm_report(Dlive, Darm, rng):
    r = {}
    for st in ("preseason", "first quarter"):
        for m, (pc, yc) in (("title", ("p_title", "y_title")), ("finals", ("p_conf", "y_finals")), ("playoff", ("p_playoff", "y_playoff"))):
            L, A = stage(Dlive, st), stage(Darm, st)
            r[f"slope_{m}_{st}"] = {"live": slope(L[pc], L[yc]), "arm": slope(A[pc], A[yc])}
    bs, gain = boot(Dlive, Darm, rng)
    mv_pre = toward_one(r["slope_title_preseason"]["live"], r["slope_title_preseason"]["arm"])
    mv_fq = toward_one(r["slope_title_first quarter"]["live"], r["slope_title_first quarter"]["arm"])
    r["movement_toward_1"] = {"preseason": {"point": mv_pre, **summarise(bs["pre"])}, "first_quarter": {"point": mv_fq, **summarise(bs["fq"])}}
    r["combined_ll_gain"] = {"point": float(gain.mean(axis=1).mean()), **summarise(bs["ll"]), "seasons_better": int((gain.mean(axis=1) > 0).sum())}
    r["market_ll_gain"] = {m: float(gain[m].mean()) for m in gain}
    return r


def decide(rep):
    """Amendments 2-3: pass / insufficient / fail for the primary arm."""
    mv = rep["movement_toward_1"]
    noharm = (rep["combined_ll_gain"]["lo90"] >= NOHARM) and all(g >= NOHARM for g in rep["market_ll_gain"].values()) \
        and mv["first_quarter"]["lo90"] >= -FQ_TOL
    pre = mv["preseason"]
    if not noharm or pre["point"] <= 0:
        return "fail", {"no_harm_ok": bool(noharm), "moves_toward_1": bool(pre["point"] > 0)}
    if pre["lo90"] > 0:
        return "pass", {"no_harm_ok": True}
    return "insufficient", {"observed_movement": pre["point"], "mdm": MDM, "below_mdm": bool(pre["point"] < MDM)}


def live_equivalent(p_replay, p_live, n_replay, n_live, z_max=3.5):
    """Amendment 2 point 1: max over teams of |diff| / se with se = sqrt(p(1-p)(1/N_replay + 1/N_live))."""
    p_replay, p_live = np.asarray(p_replay, float), np.asarray(p_live, float)
    pbar = np.clip((p_replay + p_live) / 2, 1e-4, 1 - 1e-4)
    z = np.abs(p_replay - p_live) / np.sqrt(pbar * (1 - pbar) * (1 / n_replay + 1 / n_live))
    return bool(z.max() < z_max), float(z.max())


def main(arms_dir, out_path=None):
    live = load(os.path.join(arms_dir, LIVE))
    out = {"rule": "research/NHL_PO_SCALE_RULE.md Amendments 1-3", "seasons": SEASONS, "mdm": MDM, "arms": {}}
    out["live_slopes"] = {st: slope(stage(live, st).p_title, stage(live, st).y_title) for st in ("preseason", "first quarter")}
    for d in sorted(glob.glob(os.path.join(arms_dir, "*"))):
        name = os.path.basename(d)
        if name == LIVE or not os.path.isdir(d):
            continue
        rep = arm_report(live, load(d), np.random.default_rng(SEED))
        if name == PRIMARY:
            rep["decision"], rep["decision_detail"] = decide(rep)
        else:
            rep["decision"] = "descriptive only (cannot pass)"
        out["arms"][name] = rep
    print(json.dumps(out, indent=1, default=float))
    if out_path:
        json.dump(out, open(out_path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
