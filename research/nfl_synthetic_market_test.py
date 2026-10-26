"""Pre-registered synthetic-market back-test: research/NFL_SYNTHETIC_MARKET_RULE.md. Research only.
Usage: python research/nfl_synthetic_market_test.py [market-data dir for the 2024-25 Polymarket proxy check]
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nfl_backtest as B  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, TIX, DIVS, games, load_pbp  # noqa: E402
from nfl_futures_diagnosis import WF, V4  # noqa: E402

SEASONS = range(2013, 2026)
CHECKS = (4, 9, 13)
N = 10000
RIDGE, PREV_W = 1.0, 1 / 3
DIV_OF = {t: d for d, ts in DIVS.items() for t in ts}
OUT = os.path.join(ROOT, "research")


def neutral(z):
    return z.location.astype(str).str.lower().eq("neutral").to_numpy()


def market_ratings(g, y, w):
    """Weighted ridge on closing spreads: season y weeks 1..w (weight 1) and season y-1 (weight 1/3)."""
    reg = g[g.game_type.eq("REG") & g.spread_line.notna()]
    cur = reg[(reg.season == y) & (reg.week <= w)]
    pri = reg[reg.season == y - 1]
    z = pd.concat([cur.assign(wt=1.0), pri.assign(wt=PREV_W)])
    n = len(TEAMS)
    X = np.zeros((len(z), n + 1))
    X[np.arange(len(z)), z.home_team.map(TIX).to_numpy()] = 1
    X[np.arange(len(z)), z.away_team.map(TIX).to_numpy()] = -1
    X[:, n] = (~neutral(z)).astype(float)
    W = z.wt.to_numpy(); yv = z.spread_line.to_numpy(float)
    P = np.diag([RIDGE] * n + [0.0])
    beta = np.linalg.solve(X.T @ (W[:, None] * X) + P, X.T @ (W * yv))
    r, h = beta[:n], beta[n]
    return r - r.mean(), float(h)


def validate(g):
    rows = []
    for y in SEASONS:
        for w in CHECKS:
            r, h = market_ratings(g, y, w)
            nxt = g[(g.season == y) & g.game_type.eq("REG") & (g.week == w + 1) & g.spread_line.notna()]
            pred = r[nxt.home_team.map(TIX).to_numpy()] - r[nxt.away_team.map(TIX).to_numpy()] + h * (~neutral(nxt))
            act = nxt.spread_line.to_numpy(float)
            rows.append(dict(season=y, week=w, games=len(nxt), rmse=float(np.sqrt(np.mean((pred - act) ** 2))),
                             corr=float(np.corrcoef(pred, act)[0, 1]), home_edge=h))
    return pd.DataFrame(rows)


def simulate_rows(g):
    rows = []
    for y in SEASONS:
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        out = B.outcomes(g, y)
        for w in CHECKS:
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            cur = cur_all[(cur_all.week <= w) & (cur_all.season_type == "REG")]
            ratings.P["coef"] = WF[str(y)]["coef"]
            b4, _ = ratings.base_ratings(cur, pri, gg, y)
            greg = gg[(gg.season == y) & (gg.game_type == "REG")]
            Rv4 = V4["scale"] * (b4 - b4.mean())
            Rmk, h = market_ratings(g, y, w)
            for arm, R in (("v4", Rv4), ("market", Rmk)):
                res = simulate.simulate(greg, R, N, V4["tau"], V4["sigma"], V4["hfa"], seed=1000 * y + w, hfa_post=V4["hfa_post"],
                                        n_seeds=7 if y >= 2020 else 6)
                for i, t in enumerate(TEAMS):
                    rows.append(dict(season=y, week=w, arm=arm, team=t, rating=float(R[i]), div=float(res["div"][i]),
                                     playoff=float(res["playoff"][i]), y_div=float(out["div"][i]), y_playoff=float(out["playoff"][i])))
            print(y, w, round(float(np.corrcoef(Rv4, Rmk)[0, 1]), 3), flush=True)
    return pd.DataFrame(rows)


def blend(v, m, market):
    if market == "div":
        b = np.sqrt(np.clip(v, 1e-4, 1) * np.clip(m, 1e-4, 1))
        return b
    lv, lm = np.log(np.clip(v, 1e-4, 1 - 1e-4) / (1 - np.clip(v, 1e-4, 1 - 1e-4))), np.log(np.clip(m, 1e-4, 1 - 1e-4) / (1 - np.clip(m, 1e-4, 1 - 1e-4)))
    return 1 / (1 + np.exp(-(lv + lm) / 2))


def cell_losses(z, col):
    """division: mean -log p(winner) over divisions (probabilities normalised); make-playoffs: Brier."""
    d = z.assign(division=z.team.map(DIV_OF))
    ll = []
    for _, G in d.groupby("division"):
        p = np.clip(G[col + "_div"].to_numpy(), .002, 1); p = p / p.sum()
        ll.append(-np.log(p[G.y_div.to_numpy() == 1][0]))
    return float(np.mean(ll)), float(((z[col + "_playoff"] - z.y_playoff) ** 2).mean())


def fee_cost(q):
    c = q + 0.01
    return c + 0.03 * c * (1 - c)


def evaluate(S):
    v = S[S.arm == "v4"].set_index(["season", "week", "team"]); m = S[S.arm == "market"].set_index(["season", "week", "team"])
    J = v[["div", "playoff", "y_div", "y_playoff"]].rename(columns={"div": "v4_div", "playoff": "v4_playoff"}).join(
        m[["div", "playoff"]].rename(columns={"div": "mk_div", "playoff": "mk_playoff"})).reset_index()
    J["bl_div"] = blend(J.v4_div, J.mk_div, "div"); J["bl_playoff"] = blend(J.v4_playoff, J.mk_playoff, "playoff")
    per = []
    for (y, w), z in J.groupby(["season", "week"]):
        v4d, v4p = cell_losses(z, "v4"); mkd, mkp = cell_losses(z, "mk"); bld, blp = cell_losses(z, "bl")
        per.append(dict(season=y, week=w, div_gain=mkd - v4d, playoff_gain=mkp - v4p, blend_div_gain=mkd - bld, blend_playoff_gain=mkp - blp,
                        v4_div=v4d, mk_div=mkd, v4_playoff=v4p, mk_playoff=mkp))
    P = pd.DataFrame(per)
    P["gain"] = (P.div_gain + P.playoff_gain) / 2
    P["blend_gain"] = (P.blend_div_gain + P.blend_playoff_gain) / 2
    g = P.groupby("season").gain.mean()
    rng = np.random.default_rng(20261026)
    boot = g.to_numpy()[rng.integers(0, len(g), (10000, len(g)))].mean(1)
    # paper bets against the synthetic price
    bets = []
    for mk in ("div", "playoff"):
        q = J["mk_" + mk]; cost = fee_cost(q); edge = J["v4_" + mk] / cost - 1
        sel = (q > 0) & (edge >= 0.10)
        z = J[sel].assign(market=mk, q=q[sel], cost=cost[sel], edge=edge[sel], model=J.loc[sel, "v4_" + mk], won=J.loc[sel, "y_" + mk])
        z["profit"] = np.where(z.won == 1, 100 / z.cost - 100, -100.0)
        z["expected"] = 100 * z.model / z.cost - 100
        bets.append(z[["season", "week", "team", "market", "model", "q", "cost", "edge", "won", "profit", "expected"]])
    Bt = pd.concat(bets, ignore_index=True)
    by = Bt.groupby("season").profit.sum().reindex(list(SEASONS), fill_value=0.0)
    nb = Bt.groupby("season").size().reindex(list(SEASONS), fill_value=0)
    roi_boot = []
    for idx in rng.integers(0, len(by), (10000, len(by))):
        st = nb.to_numpy()[idx].sum() * 100
        roi_boot.append(by.to_numpy()[idx].sum() / st if st else 0.0)
    top4 = Bt.sort_values("profit", ascending=False).head(4)
    summary = dict(
        primary_gain=float(g.mean()), lower90=float(np.quantile(boot, .10)), seasons_better=int((g > 0).sum()),
        by_season={str(k): float(x) for k, x in g.items()},
        division_gain=float(P.div_gain.mean()), playoff_gain=float(P.playoff_gain.mean()),
        by_week={f"w{w}": dict(div=float(z.div_gain.mean()), playoff=float(z.playoff_gain.mean())) for w, z in P.groupby("week")},
        v4_better=bool(np.quantile(boot, .10) > 0 and (g > 0).sum() >= 8),
        blend_diagnostic=dict(gain_vs_market=float(P.blend_gain.mean()), seasons_better=int((P.groupby("season").blend_gain.mean() > 0).sum())),
        paper_bets=dict(bets=int(len(Bt)), staked=float(100 * len(Bt)), profit=float(Bt.profit.sum()),
                        return_on_stake=float(Bt.profit.sum() / (100 * len(Bt))) if len(Bt) else None,
                        expected_profit=float(Bt.expected.sum()), wins=int((Bt.won == 1).sum()),
                        return_90=[float(x) for x in np.percentile(roi_boot, [5, 95])],
                        profit_without_top4=float(Bt.profit.sum() - top4.profit.sum()),
                        top4=top4[["season", "week", "team", "market", "cost", "profit"]].to_dict("records"),
                        by_season={str(k): dict(bets=int(nb[k]), profit=float(by[k])) for k in SEASONS},
                        by_market={mk: dict(bets=int((Bt.market == mk).sum()), profit=float(Bt[Bt.market == mk].profit.sum())) for mk in ("div", "playoff")}))
    return J, P, Bt, summary


def proxy_check(J, md):
    sys.path.insert(0, os.path.join(ROOT, "research"))
    import nfl_futures_scorecard as F
    g = games()
    out = {}
    for season, ev in F.BACKFILL.items():
        dates = F.checkpoint_dates(g, season)
        for mk, slugs in ev.items():
            M = {}
            for s in slugs:
                M.update(F.history(md, s))
            for w in CHECKS:
                if w not in dates:
                    continue
                z = J[(J.season == season) & (J.week == w)]
                pm = np.array([F.price_at(M.get(t), dates[w]) or np.nan for t in z.team], float)
                ok = ~np.isnan(pm)
                if ok.sum() < 4:
                    continue
                syn = z["mk_" + mk].to_numpy()[ok]
                out[f"{season} {mk} w{w}"] = dict(teams=int(ok.sum()), mean_abs_diff=float(np.abs(syn - pm[ok]).mean()), corr=float(np.corrcoef(syn, pm[ok])[0, 1]))
    return out


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    V = validate(g)
    V.to_csv(os.path.join(OUT, "nfl_synthetic_market_validation.csv"), index=False)
    val = dict(mean_rmse=float(V.rmse.mean()), mean_corr=float(V["corr"].mean()), min_corr=float(V["corr"].min()), max_rmse=float(V.rmse.max()))
    val["passes"] = bool(val["mean_rmse"] <= 4.0 and val["mean_corr"] >= 0.80)
    print("validation", val, flush=True)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    res = dict(rule="research/NFL_SYNTHETIC_MARKET_RULE.md", started_utc=started, validation=val, code_sha256=sha(__file__),
               rule_sha256=sha(os.path.join(OUT, "NFL_SYNTHETIC_MARKET_RULE.md")))
    if val["passes"]:
        S = simulate_rows(g)
        S.to_csv(os.path.join(OUT, "nfl_synthetic_market_rows.csv"), index=False)
        J, P, Bt, summ = evaluate(S)
        P.to_csv(os.path.join(OUT, "nfl_synthetic_market_cells.csv"), index=False)
        Bt.to_csv(os.path.join(OUT, "nfl_synthetic_market_bets.csv"), index=False)
        res["results"] = summ
        if len(sys.argv) > 1:
            res["polymarket_proxy_check"] = proxy_check(J, sys.argv[1])
    res["completed_utc"] = datetime.now(timezone.utc).isoformat()
    open(os.path.join(OUT, "nfl_synthetic_market_results.json"), "w").write(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k not in ("code_sha256", "rule_sha256")}, indent=2, default=str)[:6000])


if __name__ == "__main__":
    main()
