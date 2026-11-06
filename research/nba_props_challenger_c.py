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

DEV_START = pd.Timestamp("2025-10-21T00:00:00Z")
DEV_END = pd.Timestamp("2026-01-12T00:00:00Z")      # earliest priced game tips 13 Jan 2026
HOLD_START = pd.Timestamp("2025-12-15T00:00:00Z")
FIELD = {"pts": "pts_d_v2", "reb": "reb_v2", "ast": "ast_v2"}
BANDS = [(0, 15), (15, 25), (25, 99)]
FLOOR = 1e-3        # mix 0.1% of the frozen pmf back in so no value the frozen model allows gets probability zero
OUT = os.path.join(ROOT, "model", "nba_props_challenger_c.json")


def band_of(em):
    em = float(em)
    if not np.isfinite(em) or em < 0:
        raise ValueError("Expected minutes must be finite and nonnegative")
    return 0 if em <= 15 else 1 if em <= 25 else 2


def expected_minutes(q):
    q = np.asarray(q, float)
    if q.ndim != 1 or not len(q) or not np.isfinite(q).all() or (q < 0).any() or q.sum() <= 0:
        raise ValueError("Invalid conditional minutes PMF")
    return float(q @ np.arange(1, len(q) + 1) / q.sum())


ARCHIVE_TOL = 1e-5     # Amendment 11: the archive rounds p_appear to 6 and pmf entries to 7 decimals
PA_MIN = 0.01          # Amendment 11: below this the conditional is too imprecise to recover; excluded for every model and counted


class LowAppearance(ValueError):
    """p_appear below PA_MIN: the player-game is excluded (for b, c and every reported model alike) and counted."""


def conditional(unc, pa):
    """Appearing-conditional pmf from the stored unconditional pmf (Amendment 11 policy).
    Positive counts come only from the appearing component, so they are recovered by division (no subtraction near zero);
    the zero mass is the remainder. Inputs inconsistent beyond the archive's rounding (1e-5) stop the run."""
    u = np.asarray(unc, float)
    pa = float(pa)
    if u.ndim != 1 or not len(u) or not np.isfinite(u).all() or (u < 0).any():
        raise ValueError("Invalid stored PMF")
    if not np.isfinite(pa) or not 0 <= pa <= 1:
        raise ValueError("Invalid p_appear")
    if pa < PA_MIN:
        raise LowAppearance(f"p_appear {pa} below {PA_MIN}")
    if abs(float(u.sum()) - 1) > ARCHIVE_TOL:
        raise ValueError("Stored PMF normalization exceeds the archive-rounding tolerance")
    tail = u[1:] / pa
    if float(tail.sum()) > 1 + ARCHIVE_TOL / pa:
        raise ValueError("Stored PMF has more positive-count mass than p_appear allows")
    c = np.r_[max(0.0, 1.0 - float(tail.sum())), tail]
    return c / c.sum()


def load(dirs, end=DEV_END):
    """Frozen-b 60-minute replays only, inside the registered development window."""
    import nba_props_price_run as R
    end = min(pd.Timestamp(end), DEV_END)
    schedule = pd.read_csv(os.path.join(ROOT, "data", "nba", "nba_schedule_2026.csv"), low_memory=False)
    schedule = schedule[pd.to_numeric(schedule.season_type, errors="coerce") == 2]
    tips = dict(zip(pd.to_numeric(schedule.id, errors="coerce"),
                    pd.to_datetime(schedule.game_date_time if "game_date_time" in schedule else schedule.date,
                                   utc=True, errors="coerce")))
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
            if tip is None or pd.isna(tip) or not DEV_START <= tip < end or not record.get("players"):
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
        for player in record["players"]:
            rows.append(dict(game_id=gid, aid=int(player["aid"]), tip=tip, pa=float(player["p_appear"]),
                             em=expected_minutes(player["minutes_v2"]), **{s: player.get(f) for s, f in FIELD.items()}))
    if not rows:
        raise ValueError("No eligible registered development replays")
    forecasts = pd.DataFrame(rows)
    if forecasts.duplicated(["game_id", "aid"]).any():
        raise ValueError("Duplicate development player-game")
    outcomes = R.outcomes(seasons=(2026,))
    data = forecasts.merge(outcomes[["game_id", "aid", "minutes", "pts", "reb", "ast"]].rename(
        columns={"pts": "y_pts", "reb": "y_reb", "ast": "y_ast"}),
        on=["game_id", "aid"], how="inner", validate="one_to_one")
    data = data[data.minutes > 0]
    low = data.pa < PA_MIN                      # Amendment 11: excluded and counted
    load.excluded_low_appearance = int(low.sum())
    return data[~low].reset_index(drop=True)


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


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def fit(D):
    """c2 (Amendment 12): per stat and band, logit G = a + b logit F, by maximum Bernoulli likelihood of 1{y <= k}; b > 0."""
    from scipy.optimize import minimize
    maps = {}
    for s in FIELD:
        bnd, x, y = _pairs(D, s)
        maps[s] = {}
        for i in range(len(BANDS)):
            m = (bnd == i) & (x < 1)
            if m.sum() < 200:
                continue
            z, yy = _lg(x[m]), y[m]

            def nll(th):
                a, lb = th
                eta = a + np.exp(lb) * z
                return float(np.sum(np.logaddexp(0, eta) - yy * eta))
            o = minimize(nll, np.array([0.0, 0.0]), method="BFGS")
            maps[s][str(i)] = {"type": "logit", "a": float(o.x[0]), "b": float(np.exp(o.x[1])), "n": int(m.sum()), "converged": bool(o.success)}
    return maps


def calibrated_conditional(c, em, s, maps):
    c = np.asarray(c, float)
    stat_maps = maps.get(s) or {}
    if not stat_maps:
        return c
    mp = stat_maps.get(str(band_of(em)))
    if not mp:
        return c
    cdf = np.clip(np.cumsum(c), 0, 1)
    if mp.get("type") == "logit":
        g = np.where(cdf >= 1 - 1e-12, 1.0, 1 / (1 + np.exp(-(mp["a"] + mp["b"] * _lg(cdf)))))
        g = np.maximum.accumulate(np.clip(g, 0, 1))
        g[-1] = 1.0
        new = np.diff(np.r_[0.0, g])
        new = (1 - FLOOR) * new + FLOOR * c
        return new / new.sum()
    x, y = np.asarray(mp["x"], float), np.asarray(mp["y"], float)
    # One CDF argument must have one mapped value. Anchor g(1)=1, including
    # earlier bins with CDF == 1, rather than inventing mass at the last bin.
    below = x < 1
    g = np.interp(cdf, np.r_[x[below], 1.0], np.r_[y[below], 1.0])
    g = np.maximum.accumulate(np.clip(g, 0, 1))
    g[-1] = 1.0
    new = np.diff(np.r_[0.0, g])
    new = (1 - FLOOR) * new + FLOOR * c
    return new / new.sum()


def apply(unc, pa, em, s, maps):
    c = calibrated_conditional(conditional(unc, pa), em, s, maps)
    out = pa * c
    out[0] += 1 - pa
    return out


def logscore(D, s, maps=None):
    values = []
    for unc, pa, em, y in zip(D[s], D.pa, D.em, D["y_" + s]):
        if not np.isfinite(y) or y < 0 or int(y) != y:
            raise ValueError("Log score requires a nonnegative integer observation")
        c = conditional(unc, pa)
        if maps is not None:
            c = calibrated_conditional(c, em, s, maps)
        probability = c[int(y)] if int(y) < len(c) else 0.0
        values.append(float(np.log(probability)) if probability > 0 else -np.inf)
    if not values:
        raise ValueError("No holdout observations")
    return float(np.mean(values))


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


def holdout_check(D):
    A, H = D[D.tip < HOLD_START], D[D.tip >= HOLD_START]
    if A.empty or H.empty:
        raise ValueError("Both registered training and holdout windows are required")
    maps = fit(A)
    result = {"n_fit": len(A), "n_holdout": len(H), "fit_games": int(A.game_id.nunique()),
              "holdout_games": int(H.game_id.nunique()), "stats": {}}
    for stat in FIELD:
        baseline, challenger = logscore(H, stat), logscore(H, stat, maps)
        result["stats"][stat] = dict(holdout_logscore_b=baseline, holdout_logscore_c=challenger,
                                     keep=bool(challenger > baseline),
                                     calib_b=_summary(H, stat), calib_c=_summary(H, stat, maps))
    return result


def check(dirs):
    result = holdout_check(load(dirs))
    with open(os.path.join(HERE, "nba_props_challenger_c_check.json"), "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({s: {k: v[k] for k in ("holdout_logscore_b", "holdout_logscore_c", "keep")}
                      for s, v in result["stats"].items()}, indent=1))
    return result


def freeze(dirs):
    # Derive keep/identity and the final refit from the same freshly loaded
    # development cohort. An unrelated/stale check JSON cannot select maps.
    D = load(dirs)
    chk = holdout_check(D)
    maps = fit(D)
    kept = {s: maps[s] if chk["stats"][s]["keep"] else {} for s in FIELD}
    out = dict(version="c2", rule="research/NBA_PROPS_PRICE_TEST_RULE.md Amendments 6, 11 and 12", dev_end=str(DEV_END),
               bands=BANDS, floor=FLOOR, fields=FIELD, kept={s: bool(kept[s]) for s in FIELD},
               n_dev=len(D), dev_games=int(D.game_id.nunique()), maps=kept)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    with open(OUT, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(OUT, digest, out["kept"], out["n_dev"])


def selftest():
    rng = np.random.default_rng(3)
    # forecasts too confident: true counts ~ Poisson(mu * extra spread); frozen pmf = Poisson(mu); c should improve log score
    from scipy.stats import poisson, nbinom
    rows = []
    for i in range(4000):
        mu = rng.uniform(1, 20)
        pmf = poisson.pmf(np.arange(60), mu)
        n = 3.0
        # Keep this fabricated test's observations in the finite PMF support;
        # an exact log score must not hide unsupported counts behind a cap.
        pmf[-1] += max(0.0, 1.0 - float(pmf.sum()))
        y = min(nbinom.rvs(n, n / (n + mu), random_state=rng), len(pmf) - 1)
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
