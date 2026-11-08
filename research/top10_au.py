"""Top-10 backtest edges for AFL/NBL (rule: research/TOP10_BACKTEST_EDGES_RULE.md, Amendment 4).
Usage: python research/top10_au.py afl|nbl <odds.xlsx> <out dir>"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M

sport, xlsx, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
if sport == "afl":
    import afl_site as S
    HOME, SD, K, REG = S.HGA, S.GAME_SD, S.K_PRIOR, S.PRIOR_REG
else:
    import nbl_site as S
    HOME, SD, K, REG = S.HCA, S.GAME_SD, S.K_PRIOR, S.PRIOR_REG
O = pd.read_excel(xlsx, header=1)
O["date"] = pd.to_datetime(O.Date).dt.normalize()
O["season"] = O.date.dt.year if sport == "afl" else np.where(O.date.dt.month >= 8, O.date.dt.year, O.date.dt.year - 1)
O["playoff"] = O["Play Off Game?"].fillna("").eq("Y")
O["unreliable"] = O["Notes"].fillna("").str.contains("unreliable", case=False)
O = O.dropna(subset=["Home Score", "Away Score"]).sort_values("date").reset_index(drop=True)
# long table for the rating function (regular season only), same columns the engine uses
R = O[~O.playoff]
rows = []
for se, dt_, ht, at, hs, as_ in zip(R.season, R.date, R["Home Team"], R["Away Team"], R["Home Score"], R["Away Score"]):
    rows.append(dict(season=se, date=dt_, team=ht, opp=at, ha="H", pf=hs, pa=as_))
    rows.append(dict(season=se, date=dt_, team=at, opp=ht, ha="A", pf=as_, pa=hs))
G = pd.DataFrame(rows); G["margin"] = G.pf - G.pa
out_rows = []
for y in sorted(G.season.unique()):
    g = G[G.season == y]; prev = G[G.season == y - 1]
    if not len(prev): continue
    prior = {t: REG * v for t, v in S.srs(prev).items()}
    dates = sorted(g.date.unique()); n = len(dates)
    for i, d in enumerate(dates):
        played = g[g.date < d]
        rating = S.srs(played, prior=prior, k=K) if len(played) else dict(prior)
        for r in g[(g.date == d) & (g.ha == "H")].itertuples():
            m = rating.get(r.team, 0.0) - rating.get(r.opp, 0.0) + HOME
            out_rows.append(dict(season=y, date=d, home=r.team, away=r.opp, frac=i / max(1, n), margin_model=m, p_model=float(M.phi(m / SD)),
                                 result=r.pf - r.pa, y=float(r.pf > r.pa), tie=r.pf == r.pa, gp_home=int((played.team == r.team).sum()), gp_away=int((played.team == r.opp).sum())))
P = pd.DataFrame(out_rows)
O["home"], O["away"] = O["Home Team"], O["Away Team"]
hc = O["Home Odds Close"].fillna(O["Home Odds"]); ac = O["Away Odds Close"].fillna(O["Away Odds"])
O["p_market"] = M.devig(hc, ac)
O["line_close"] = O["Home Line Close"]
keep = O[~O.playoff & ~O.unreliable][["date", "home", "away", "p_market", "line_close", "Home Odds Close", "Away Odds Close", "Home Score", "Away Score"]].dropna(subset=["p_market"])
J = P.merge(keep, on=["date", "home", "away"], how="inner")
J = J[(~J.tie) & (J.season >= 2012)].copy()
J["gap"] = J.p_model - J.p_market; J = J[J.gap != 0].copy()
J["side"] = np.where(J.gap > 0, "home", "away"); J["edge"] = J.gap.abs()
J["pm_side"] = np.where(J.gap > 0, J.p_model, 1 - J.p_model); J["pk_side"] = np.where(J.gap > 0, J.p_market, 1 - J.p_market)
J.to_csv(os.path.join(out, f"{sport}_edges_all.csv"), index=False)
def ll(p, y): p = np.clip(p, 1e-4, 1 - 1e-4); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
print(sport, "rated games", len(P), "with odds", len(J), "seasons", J.season.nunique(), "model LL", round(ll(J.p_model, J.y).mean(), 4), "market LL", round(ll(J.p_market, J.y).mean(), 4))
disc = J[J.season <= 2019]
top = disc.sort_values("edge", ascending=False).head(10)
cols = ["season", "date", "home", "away", "side", "pm_side", "pk_side", "edge", "margin_model", "line_close", "Home Odds Close", "Away Odds Close", "result", "gp_home", "gp_away"]
print(top[cols].round(3).to_string(index=False))
top[cols].to_csv(os.path.join(out, f"{sport}_top10_discovery.csv"), index=False)
rng = np.random.default_rng(0)
for name, X in (("disc", disc), ("eval", J[J.season >= 2020]), ("all", J)):
    k = int(round(len(X) * 0.05)); A = X.sort_values("edge", ascending=False).head(k); B = X.assign(g2=-X.gap).sort_values("g2", ascending=False).head(k)
    d = lambda Z: ll(Z.p_model, Z.y) - ll(Z.p_market, Z.y)
    seas = sorted(X.season.unique()); b = []
    for _ in range(2000):
        pick = rng.choice(seas, len(seas)); a = np.concatenate([d(A[A.season == s]).values for s in pick]); c = np.concatenate([d(B[B.season == s]).values for s in pick])
        if len(a) and len(c): b.append(a.mean() - c.mean())
    print(name, "n/tail", k, "LL gap A", round(d(A).mean(), 4), "B", round(d(B).mean(), 4), "D", round(d(A).mean() - d(B).mean(), 4), np.percentile(b, [5, 95]).round(3), "early (frac<.2) share of top5%", round((A.frac < .2).mean(), 3), "vs all", round((X.frac < .2).mean(), 3))
# weight on the model's margin gap
sig = SD
J["mk_margin"] = (lambda p: __import__("scipy.stats", fromlist=["norm"]).norm.ppf(np.clip(p, 1e-4, 1 - 1e-4)) * SD)(J.p_market)
J["gap_m"] = J.margin_model - J.mk_margin; J["out_gap"] = J.result - J.mk_margin
for lab, X in (("frac<.2", J[J.frac < .2]), ("frac .2-.8", J[(J.frac >= .2) & (J.frac < .8)]), ("frac>=.8", J[J.frac >= .8]), ("all", J)):
    x, yv = X.gap_m.values, X.out_gap.values; bb = (x * yv).sum() / (x * x).sum(); seas = sorted(X.season.unique()); bs = []
    for _ in range(1500):
        p = rng.choice(seas, len(seas)); Z = pd.concat([X[X.season == s] for s in p]); bs.append((Z.gap_m * Z.out_gap).sum() / (Z.gap_m ** 2).sum())
    print("weight on model gap", lab, "n", len(X), round(bb, 3), np.percentile(bs, [5, 95]).round(3))
