"""Challenger "c" for research/NBA_PROPS_PRICE_TEST_RULE.md (Amendment 6): monotone recalibration of the frozen model's
appearing-conditional cumulative probabilities, per stat and expected-minutes band, fitted by isotonic regression on development
replays (games tipping before 12 Jan 2026 00:00 UTC; no prices).

  python research/nba_props_challenger_c.py check <archive_dir> [<archive_dir> ...]    holdout check (fit < 15 Dec, check 15 Dec..11 Jan)
  python research/nba_props_challenger_c.py freeze <archive_dir> [...]                 refit kept maps on all development games -> model/nba_props_challenger_c.json
  python research/nba_props_challenger_c.py selftest

apply(pmf_unconditional, p_appear, exp_minutes, stat, maps) returns the challenger's unconditional pmf; used by the price-test runner.
"""
import gzip
import glob
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

DEV_END = pd.Timestamp("2026-01-12T00:00:00Z")      # earliest priced game tips 13 Jan 2026
HOLD_START = pd.Timestamp("2025-12-15T00:00:00Z")
FIELD = {"pts": "pts_d_v2", "reb": "reb_v2", "ast": "ast_v2"}
BANDS = [(0, 15), (15, 25), (25, 99)]
FLOOR = 1e-3        # mix 0.1% of the frozen pmf back in so no value the frozen model allows gets probability zero
OUT = os.path.join(ROOT, "model", "nba_props_challenger_c.json")


def band_of(em):
    for i, (lo, hi) in enumerate(BANDS):
        if lo < em <= hi or (i == 0 and em <= hi):
            return i
    return len(BANDS) - 1


def conditional(unc, pa):
    """Appearing-conditional pmf from the stored unconditional pmf (mass 1 - pa was added at zero)."""
    c = np.asarray(unc, float).copy()
    c[0] -= (1 - pa)
    c = np.clip(c, 0, None)
    s = c.sum()
    return c / s if s > 0 else c


def load(dirs, end=DEV_END):
    """Player rows from replay archives, games tipping before `end`, one record per game (the latest cutoff at or before tip-60)."""
    import nba_props_price_run as R
    s = pd.read_csv(os.path.join(ROOT, "data", "nba", "nba_schedule_2026.csv"), low_memory=False)
    tips = dict(zip(pd.to_numeric(s.id, errors="coerce"), pd.to_datetime(s.game_date_time if "game_date_time" in s else s.date, utc=True,
                                                                         errors="coerce")))
    best = {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*.json.gz"), recursive=True):
            if "_60_" not in os.path.basename(p):
                continue
            r = json.load(gzip.open(p))
            gid, cut = int(r["game_id"]), pd.Timestamp(r["cutoff_utc"])
            tip = tips.get(gid)
            if tip is None or pd.isna(tip) or tip >= end or cut > tip - pd.Timedelta(minutes=60) or not r.get("players"):
                continue
            if gid not in best or cut > best[gid][0]:      # the latest cutoff at or before tip - 60 minutes
                best[gid] = (cut, tip, r)
    rows = []
    for gid, (cut, tip, r) in best.items():
        if True:
            for pl in r["players"]:
                q = np.asarray(pl["minutes_v2"], float)
                em = float((np.arange(1, len(q) + 1) * q).sum() / max(q.sum(), 1e-12))
                rows.append(dict(game_id=int(r["game_id"]), aid=int(pl["aid"]), tip=tip, pa=float(pl["p_appear"]), em=em,
                                 **{s: pl.get(f) for s, f in FIELD.items()}))
    F = pd.DataFrame(rows)
    O = R.outcomes(seasons=(2026,))
    D = F.merge(O[["game_id", "aid", "minutes", "pts", "reb", "ast"]].rename(columns={"pts": "y_pts", "reb": "y_reb", "ast": "y_ast"}),
                on=["game_id", "aid"], how="inner")
    return D[D.minutes > 0].reset_index(drop=True)


def _pairs(D, s):
    """(band, F(k), 1{y<=k}) over k = 0..99.9th percentile of each forecast."""
    B, X, Y = [], [], []
    for unc, pa, em, y in zip(D[s], D.pa, D.em, D["y_" + s]):
        c = conditional(unc, pa)
        cdf = np.cumsum(c)
        kmax = int(np.searchsorted(cdf, 0.999)) + 1
        k = np.arange(min(kmax, len(cdf)))
        B.append(np.full(len(k), band_of(em)))
        X.append(cdf[k])
        Y.append((y <= k).astype(float))
    return np.concatenate(B), np.concatenate(X), np.concatenate(Y)


def fit(D):
    from sklearn.isotonic import IsotonicRegression
    maps = {}
    for s in FIELD:
        b, x, y = _pairs(D, s)
        maps[s] = {}
        for i in range(len(BANDS)):
            m = b == i
            if m.sum() < 200:
                continue
            ir = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True, out_of_bounds="clip").fit(x[m], y[m])
            maps[s][str(i)] = {"x": [float(v) for v in ir.X_thresholds_], "y": [float(v) for v in ir.y_thresholds_], "n": int(m.sum())}
    return maps


def calibrated_conditional(c, em, s, maps):
    mp = (maps.get(s) or {}).get(str(band_of(em)))
    if not mp:
        return c
    cdf = np.cumsum(c)
    g = np.interp(cdf, mp["x"], mp["y"])
    g = np.maximum.accumulate(np.clip(g, 0, 1))
    g[-1] = 1.0
    new = np.diff(np.concatenate([[0.0], g]))
    new = (1 - FLOOR) * new + FLOOR * c
    return new / new.sum()


def apply(unc, pa, em, s, maps):
    c = calibrated_conditional(conditional(unc, pa), em, s, maps)
    out = pa * c
    out[0] += 1 - pa
    return out


def logscore(D, s, maps=None):
    v = []
    for unc, pa, em, y in zip(D[s], D.pa, D.em, D["y_" + s]):
        c = conditional(unc, pa)
        if maps is not None:
            c = calibrated_conditional(c, em, s, maps)
        v.append(np.log(max(c[int(y)] if int(y) < len(c) else 0.0, 1e-9)))
    return float(np.mean(v))


def _summary(D, s, maps=None):
    """Calibration of P(over) at the forecast median line, and P(0), by band (for the report)."""
    out = {}
    for i in range(len(BANDS)):
        G = D[D.em.map(band_of) == i]
        if len(G) == 0:
            continue
        p0, a0, po, ao = [], [], [], []
        for unc, pa, em, y in zip(G[s], G.pa, G.em, G["y_" + s]):
            c = conditional(unc, pa)
            if maps is not None:
                c = calibrated_conditional(c, em, s, maps)
            cdf = np.cumsum(c)
            med = int(np.searchsorted(cdf, 0.5))
            p0.append(c[0]); a0.append(float(y == 0)); po.append(1 - cdf[med]); ao.append(float(y > med))
        out[f"{BANDS[i][0]}-{BANDS[i][1]}"] = dict(n=len(G), p_zero=round(float(np.mean(p0)), 4), actual_zero=round(float(np.mean(a0)), 4),
                                                   p_over_median=round(float(np.mean(po)), 4), actual_over_median=round(float(np.mean(ao)), 4))
    return out


def check(dirs):
    D = load(dirs)
    A, H = D[D.tip < HOLD_START], D[D.tip >= HOLD_START]
    maps = fit(A)
    res = {"n_fit": len(A), "n_holdout": len(H), "fit_games": int(A.game_id.nunique()), "holdout_games": int(H.game_id.nunique()), "stats": {}}
    for s in FIELD:
        lb, lc = logscore(H, s), logscore(H, s, maps)
        res["stats"][s] = dict(holdout_logscore_b=lb, holdout_logscore_c=lc, keep=bool(lc > lb),
                               calib_b=_summary(H, s), calib_c=_summary(H, s, maps))
    json.dump(res, open(os.path.join(HERE, "nba_props_challenger_c_check.json"), "w"), indent=1)
    print(json.dumps({s: {k: v[k] for k in ("holdout_logscore_b", "holdout_logscore_c", "keep")} for s, v in res["stats"].items()}, indent=1))
    return res


def freeze(dirs):
    chk = json.load(open(os.path.join(HERE, "nba_props_challenger_c_check.json")))
    D = load(dirs)
    maps = fit(D)
    kept = {s: (maps[s] if chk["stats"][s]["keep"] else {}) for s in FIELD}
    out = dict(version="c", rule="research/NBA_PROPS_PRICE_TEST_RULE.md Amendment 6", dev_end=str(DEV_END), bands=BANDS, floor=FLOOR,
               fields=FIELD, kept={s: bool(kept[s]) for s in FIELD}, n_dev=len(D), dev_games=int(D.game_id.nunique()), maps=kept)
    json.dump(out, open(OUT, "w"), indent=1)
    print(OUT, hashlib.sha256(open(OUT, "rb").read()).hexdigest(), out["kept"], out["n_dev"])


def selftest():
    rng = np.random.default_rng(3)
    # forecasts too confident: true counts ~ Poisson(mu * extra spread); frozen pmf = Poisson(mu); c should improve log score
    from scipy.stats import poisson, nbinom
    rows = []
    for i in range(4000):
        mu = rng.uniform(1, 20)
        pmf = poisson.pmf(np.arange(60), mu)
        n = 3.0
        y = nbinom.rvs(n, n / (n + mu), random_state=rng)
        rows.append(dict(pts=list(pmf), reb=list(pmf), ast=list(pmf), pa=1.0, em=rng.uniform(5, 35), y_pts=y, y_reb=y, y_ast=y,
                         tip=pd.Timestamp("2025-11-01", tz="UTC")))
    D = pd.DataFrame(rows)
    maps = fit(D.iloc[:3000])
    H = D.iloc[3000:]
    assert logscore(H, "pts", maps) > logscore(H, "pts") + 0.05, (logscore(H, "pts", maps), logscore(H, "pts"))
    out = apply(np.array(D.pts.iloc[0]) * 0.8 + np.r_[0.2, np.zeros(59)], 0.8, 20, "pts", maps)
    assert abs(out.sum() - 1) < 1e-9 and (out >= 0).all() and out[0] >= 0.2 - 1e-9
    assert np.allclose(apply(np.array(D.pts.iloc[0]), 1.0, 20, "pts", {}), D.pts.iloc[0])
    print("selftest passed")


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"check": lambda: check(sys.argv[2:]), "freeze": lambda: freeze(sys.argv[2:]), "selftest": selftest}[cmd]()
