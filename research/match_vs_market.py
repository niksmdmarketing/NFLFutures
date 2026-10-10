"""Our point-in-time match ratings vs closing betting lines (research; prices never feed the independent model).

Input per game: season, stage (fraction of the regular season played before the game), home win (1/0), our model's
pre-game home win probability, and the market's (de-margined) home win probability.
Outputs, all chronological (weights fitted on earlier seasons only, then scored on the next season):
  * log-loss of model, market, and the log-odds pool  logit(p) = w*logit(model) + (1-w)*logit(market), by stage
  * the fitted weight w per stage: how much our ratings add on top of the market (0 = nothing)
"""
import math

import numpy as np
import pandas as pd

STAGES = [(0.0, 0.25, "first quarter"), (0.25, 0.5, "second quarter"), (0.5, 0.75, "third quarter"), (0.75, 1.01, "last quarter")]
W_GRID = np.round(np.arange(0.0, 1.01, 0.05), 2)


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def pool(pm, pk, w):
    return 1 / (1 + np.exp(-(w * logit(pm) + (1 - w) * logit(pk))))


def stage_of(f):
    for a, b, name in STAGES:
        if a <= f < b:
            return name
    return STAGES[-1][2]


def analyse(D, min_train=3):
    """D: season, frac, y, p_model, p_market. Returns dict with chronological results and full-sample weights."""
    D = D.dropna(subset=["p_model", "p_market", "y"]).copy()
    D["stage"] = D.frac.map(stage_of)
    seasons = sorted(D.season.unique())
    rows = []
    for s in seasons[min_train:]:
        tr, te = D[D.season < s], D[D.season == s]
        for st, x in te.groupby("stage"):
            t = tr[tr.stage == st]
            if len(t) < 50:
                continue
            w = max(W_GRID, key=lambda w_: -ll(pool(t.p_model.values, t.p_market.values, w_), t.y.values))
            rows.append(dict(season=s, stage=st, n=len(x), w=float(w), model=ll(x.p_model.values, x.y.values),
                             market=ll(x.p_market.values, x.y.values), pooled=ll(pool(x.p_model.values, x.p_market.values, w), x.y.values)))
    R = pd.DataFrame(rows)
    out = {"seasons": f"{seasons[0]}-{seasons[-1]}", "games": int(len(D)), "test_seasons": f"{seasons[min_train]}-{seasons[-1]}" if len(seasons) > min_train else None}
    by = {}
    for st in [s[2] for s in STAGES]:
        x = R[R.stage == st]
        if x.empty:
            continue
        n = x.n.sum()
        wavg = lambda c: float((x[c] * x.n).sum() / n)
        d = (x.market - x.pooled)
        by[st] = dict(games=int(n), model=round(wavg("model"), 4), market=round(wavg("market"), 4), pooled=round(wavg("pooled"), 4),
                      weight_on_model=round(float((x.w * x.n).sum() / n), 2), seasons_pooled_better=int((d > 0).sum()), seasons=int(len(x)))
        full = D[D.stage == st]
        by[st]["weight_all_seasons"] = float(max(W_GRID, key=lambda w_: -ll(pool(full.p_model.values, full.p_market.values, w_), full.y.values)))
    out["by_stage"] = by
    n = R.n.sum()
    out["overall"] = {k: round(float((R[k] * R.n).sum() / n), 4) for k in ("model", "market", "pooled")} if n else {}
    return out, R


def phi(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2)))


def devig(h, a):
    """Decimal odds -> de-margined home probability."""
    ih, ia = 1 / h, 1 / a
    return ih / (ih + ia)


def american_to_decimal(m):
    m = np.asarray(m, float)
    return np.where(m > 0, 1 + m / 100, 1 + 100 / np.abs(m))
