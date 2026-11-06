"""Challenger "e" for research/NBA_PROPS_PRICE_TEST_RULE.md (Amendment 13): boosted-tree correction of the frozen model's
appearing-conditional mean, per stat; the frozen shape is kept by exponential tilting. Archive fields only, no prices.

  python research/nba_props_challenger_e.py check <archive_dir> [<archive_dir> ...]    fit < 15 Dec 2025, holdout 15 Dec .. 11 Jan
  python research/nba_props_challenger_e.py freeze <archive_dir> [...]                 refit kept stats on all development games
  python research/nba_props_challenger_e.py selftest

apply(unc, pa, record_player, stat, model) returns the challenger's unconditional pmf (used only if a stat is kept).
"""
import glob
import gzip
import hashlib
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nba_props_challenger_c as C   # noqa: E402  (same eligibility, conditional(), and c2 maps)

STATS = ("pts", "reb", "ast")
FIELD = C.FIELD
RHO = (0.7, 1.4)
FLOOR = C.FLOOR
ITERS = (25, 50, 100, 200, 300)
HGB = dict(max_depth=3, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0, early_stopping=False, random_state=0)
MU_MIN = 0.05
OUT = os.path.join(ROOT, "model", "nba_props_challenger_e")


def _moments(c):
    k = np.arange(len(c))
    mu = float(c @ k)
    return mu, float(np.sqrt(max(c @ (k - mu) ** 2, 0.0))), float(c[0])


def features(player, pa, conds, status_codes):
    """One feature row from archive fields: minutes pmf, stage-1 fields, report status, frozen conditional moments of each stat."""
    q = np.asarray(player["minutes_v2"], float)
    row = [C.expected_minutes(q), float(player.get("stage1_mu", np.nan)), float(player.get("stage1_sd", np.nan)), float(pa),
           float(player.get("p_under15_stage1", np.nan)), float(player.get("pi_short", np.nan)), float(bool(player.get("risk_group_v2"))),
           float(status_codes.get(str(player.get("status")), -1))]
    for s in STATS:
        row += list(_moments(conds[s]))
    return row


FEATURE_NAMES = ["em", "stage1_mu", "stage1_sd", "p_appear", "p_under15", "pi_short", "risk", "status"] + \
                [f"{s}_{m}" for s in STATS for m in ("mu", "sd", "p0")]


def load(dirs, end=C.DEV_END):
    """Same cohort as c2 (C.load rules), with the extra archive fields kept. Returns a DataFrame; pmfs stay as lists."""
    import nba_props_price_run as R
    end = min(pd.Timestamp(end), C.DEV_END)
    schedule = pd.read_csv(os.path.join(ROOT, "data", "nba", "nba_schedule_2026.csv"), low_memory=False)
    schedule = schedule[pd.to_numeric(schedule.season_type, errors="coerce") == 2]
    tips = dict(zip(pd.to_numeric(schedule.id, errors="coerce"),
                    pd.to_datetime(schedule.game_date_time if "game_date_time" in schedule else schedule.date, utc=True, errors="coerce")))
    best = {}
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(directory, "**", "*.json.gz"), recursive=True)):
            if "_60_" not in os.path.basename(path):
                continue
            with gzip.open(path) as f:
                record = json.load(f)
            if record.get("params_id") != "b" or record.get("horizon_min") != 60:
                continue
            if not isinstance(record.get("report"), dict) or record["report"].get("replay") is not True:
                continue
            gid = int(record["game_id"])
            tip = tips.get(gid)
            if tip is None or pd.isna(tip) or not C.DEV_START <= tip < end or not record.get("players"):
                continue
            cut, run = pd.Timestamp(record["cutoff_utc"]), pd.Timestamp(record["run_utc"])
            if pd.isna(cut) or pd.isna(run) or cut.tzinfo is None or run.tzinfo is None:
                raise ValueError("Replay timing evidence requires explicit time zones")
            if cut > tip - pd.Timedelta(minutes=60) or run > cut:
                continue
            if gid not in best or cut > best[gid][0]:
                best[gid] = (cut, tip, record)
    rows = []
    for gid, (cut, tip, record) in best.items():
        for p in record["players"]:
            rows.append(dict(game_id=gid, aid=int(p["aid"]), tip=tip, pa=float(p["p_appear"]), em=C.expected_minutes(p["minutes_v2"]),
                             player=p, **{s: p.get(f) for s, f in FIELD.items()}))
    F = pd.DataFrame(rows)
    if F.duplicated(["game_id", "aid"]).any():
        raise ValueError("Duplicate development player-game")
    out = R.outcomes(seasons=(2026,))
    D = F.merge(out[["game_id", "aid", "minutes", "pts", "reb", "ast"]].rename(columns={"pts": "y_pts", "reb": "y_reb", "ast": "y_ast"}),
                on=["game_id", "aid"], how="inner", validate="one_to_one")
    D = D[D.minutes > 0]
    D = D[~(D.pa < C.PA_MIN)].reset_index(drop=True)
    return D


def prepare(D, status_codes):
    """Conditional pmfs and the feature matrix for every row."""
    conds = [{s: C.conditional(r[s], r.pa) for s in STATS} for _, r in D.iterrows()]
    X = np.array([features(r.player, r.pa, c, status_codes) for (_, r), c in zip(D.iterrows(), conds)], float)
    return conds, X


def status_map(D):
    return {s: i for i, s in enumerate(sorted({str(p.get("status")) for p in D.player}))}


def tilt(c, target):
    """Exponential tilt of pmf c so that its mean equals target (target inside the support's reach)."""
    from scipy.optimize import brentq
    c = np.asarray(c, float)
    k = np.arange(len(c))
    if target <= 1e-9 or target >= k[-1] - 1e-9 or c.sum() <= 0:
        return c

    def mean_at(th):
        w = c * np.exp(np.clip(th * (k - k.mean()), -700, 700))
        return float((w @ k) / w.sum())
    lo, hi = -2.0, 2.0
    if not (mean_at(lo) <= target <= mean_at(hi)):
        return c
    th = brentq(lambda t: mean_at(t) - target, lo, hi, xtol=1e-10)
    w = c * np.exp(np.clip(th * (k - k.mean()), -700, 700))
    return w / w.sum()


def corrected(c, rho):
    mu = _moments(c)[0]
    if mu < MU_MIN:
        return c
    new = tilt(c, mu * float(np.clip(rho, *RHO)))
    new = (1 - FLOOR) * new + FLOOR * c
    return new / new.sum()


def _dev(y, mu, w):
    """Weighted Poisson deviance of the ratio target (sum of w * ratio-deviance)."""
    mu = np.maximum(mu, 1e-9)
    return float(np.sum(w * 2 * (np.where(y > 0, y * np.log(np.maximum(y, 1e-12) / mu), 0.0) - (y - mu))))


def fit_stat(X, conds, D, s):
    """Pick iterations on the last 20% of the fitting rows by tip time, then refit on all fitting rows."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    mu = np.array([_moments(c[s])[0] for c in conds])
    y = D["y_" + s].to_numpy(float)
    ok = mu >= MU_MIN
    order = np.argsort(D.tip.to_numpy(), kind="stable")
    order = order[ok[order]]
    cut = int(len(order) * 0.8)
    tr, va = order[:cut], order[cut:]
    ratio, w = y / np.maximum(mu, MU_MIN), mu
    m = HistGradientBoostingRegressor(loss="poisson", max_iter=max(ITERS), **HGB).fit(X[tr], ratio[tr], sample_weight=w[tr])
    devs = {}
    for i, pred in enumerate(m.staged_predict(X[va]), start=1):
        if i in ITERS:
            devs[i] = _dev(ratio[va], np.clip(pred, *RHO), w[va])
    n_iter = min(devs, key=devs.get)
    model = HistGradientBoostingRegressor(loss="poisson", max_iter=n_iter, **HGB).fit(X[order], ratio[order], sample_weight=w[order])
    return model, n_iter, devs


def row_scores(D, conds, X, models, maps_c2=None):
    """Per-row appearing-conditional log scores: frozen b, c2 (if maps given), e (stats with a model)."""
    out = {s: {"b": [], "c2": [], "e": []} for s in STATS}
    pred = {s: (models[s].predict(X) if models.get(s) is not None else None) for s in STATS}
    for i, (c, y_row) in enumerate(zip(conds, D.itertuples())):
        for s in STATS:
            y = int(getattr(y_row, "y_" + s))
            cb = c[s]
            out[s]["b"].append(float(np.log(cb[y])) if y < len(cb) and cb[y] > 0 else -np.inf)
            if maps_c2 is not None:
                c2 = C.calibrated_conditional(cb, y_row.em, s, maps_c2)
                out[s]["c2"].append(float(np.log(c2[y])) if y < len(c2) and c2[y] > 0 else -np.inf)
            if pred[s] is not None:
                ce = corrected(cb, pred[s][i])
                out[s]["e"].append(float(np.log(ce[y])) if y < len(ce) and ce[y] > 0 else -np.inf)
    return {s: {k: np.array(v) for k, v in d.items() if v} for s, d in out.items()}


def date_boot_lb(diff, dates, draws=2000, seed=1):
    """One-sided 90% lower bound of the mean of diff, resampling whole dates."""
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"x": diff, "d": dates}).groupby("d").x.agg(["sum", "count"])
    s, n = d["sum"].to_numpy(), d["count"].to_numpy()
    idx = rng.integers(0, len(s), size=(draws, len(s)))
    means = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    return float(np.quantile(means, 0.10))


def holdout_check(D):
    A, H = D[D.tip < C.HOLD_START].reset_index(drop=True), D[D.tip >= C.HOLD_START].reset_index(drop=True)
    if A.empty or H.empty:
        raise ValueError("Both registered training and holdout windows are required")
    codes = status_map(A)
    cA, XA = prepare(A, codes)
    cH, XH = prepare(H, codes)
    maps = C.fit(A)
    models, iters = {}, {}
    for s in STATS:
        models[s], iters[s], _ = fit_stat(XA, cA, A, s)
    S = row_scores(H, cH, XH, models, maps)
    dates = H.tip.dt.strftime("%Y-%m-%d").to_numpy()
    res = {"n_fit": len(A), "n_holdout": len(H), "status_codes": codes, "stats": {}}
    for s in STATS:
        b, c2, e = S[s]["b"], S[s]["c2"], S[s]["e"]
        lb = date_boot_lb(e - c2, dates) if np.isfinite(e - c2).all() else float("nan")
        res["stats"][s] = dict(iterations=iters[s], holdout_b=float(b.mean()), holdout_c2=float(c2.mean()), holdout_e=float(e.mean()),
                               e_minus_c2=float((e - c2).mean()), e_minus_c2_lower90=lb, e_minus_b=float((e - b).mean()),
                               keep=bool(e.mean() > b.mean() and e.mean() > c2.mean() and lb > 0))
    return res


def check(dirs):
    D = load(dirs)
    res = holdout_check(D)
    json.dump(res, open(os.path.join(HERE, "nba_props_challenger_e_check.json"), "w"), indent=1)
    print(json.dumps(res["stats"], indent=1), res["n_fit"], res["n_holdout"])


def freeze(dirs):
    D = load(dirs)
    chk = holdout_check(D)           # keep/identity from a fresh cohort, as c2
    codes = status_map(D)
    conds, X = prepare(D, codes)
    models, iters = {}, {}
    for s in STATS:
        if chk["stats"][s]["keep"]:
            models[s], iters[s], _ = fit_stat(X, conds, D, s)
    manifest = dict(version="e", rule="research/NBA_PROPS_PRICE_TEST_RULE.md Amendment 13", dev_end=str(C.DEV_END), n_dev=len(D),
                    feature_names=FEATURE_NAMES, status_codes=codes, rho_clip=RHO, floor=FLOOR, iterations=iters,
                    kept={s: s in models for s in STATS}, hgb=HGB)
    with open(OUT + ".pkl", "wb") as f:
        pickle.dump({"models": models, "manifest": manifest}, f, protocol=4)
    json.dump(manifest, open(OUT + ".json", "w"), indent=1)
    print(OUT, hashlib.sha256(open(OUT + ".pkl", "rb").read()).hexdigest(), manifest["kept"], manifest["n_dev"])


def selftest():
    from scipy.stats import poisson
    rng = np.random.default_rng(5)
    # tilt hits its target and keeps validity
    c = poisson.pmf(np.arange(60), 8.0)
    c = c / c.sum()
    t = tilt(c, 9.6)
    assert abs(t @ np.arange(60) - 9.6) < 1e-6 and abs(t.sum() - 1) < 1e-9
    assert np.allclose(corrected(c, 1.0), (1 - FLOOR) * tilt(c, c @ np.arange(60)) + FLOOR * c, atol=1e-6)
    # a hidden feature shifts the true mean by 25%; the model must learn it and improve the log score out of sample
    n = 5000
    mu = rng.uniform(3, 20, n)
    flag = rng.integers(0, 2, n)
    y = rng.poisson(mu * (1 + 0.25 * flag))
    pm = [poisson.pmf(np.arange(80), m) / poisson.pmf(np.arange(80), m).sum() for m in mu]
    X = np.column_stack([flag, mu])
    conds = [{"pts": p, "reb": p, "ast": p} for p in pm]
    D = pd.DataFrame({"tip": pd.date_range("2025-11-01", periods=n, freq="h", tz="UTC"), "y_pts": y, "y_reb": y, "y_ast": y})
    tr, te = np.arange(3500), np.arange(3500, n)
    model, it, _ = fit_stat(X[tr], [conds[i] for i in tr], D.iloc[tr].reset_index(drop=True), "pts")
    rho = model.predict(X[te])
    ls_b = np.mean([np.log(pm[i][y[i]]) for i in te])
    ls_e = np.mean([np.log(corrected(pm[i], r)[y[i]]) for i, r in zip(te, rho)])
    assert ls_e > ls_b + 0.01, (ls_e, ls_b)
    # bootstrap bound is a number and zero-difference data does not pass
    assert date_boot_lb(np.zeros(100), np.repeat(np.arange(10), 10)) <= 1e-12
    print("selftest passed", round(ls_e - ls_b, 4), it)


if __name__ == "__main__":
    {"check": lambda: check(sys.argv[2:]), "freeze": lambda: freeze(sys.argv[2:]), "selftest": selftest}[sys.argv[1]]()
