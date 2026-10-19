"""Individual playoff games 2013-2025 with ratings fixed immediately before each postseason (all regular-season games, nothing
from the playoffs; research/nfl_futures_diagnosis.py 'end' checkpoint). Per game: predicted margin (rating gap + playoff home edge;
Super Bowl neutral), win probability as in the simulation (sd = sqrt(sigma^2 + 2 tau^2)), actual margin. Split by round, era, and No. 1 seeds.
Diagnostic only; no setting is changed."""
import json, os, sys
import numpy as np, pandas as pd
from scipy.stats import norm
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import FIX, games  # noqa: E402
H = os.path.join(ROOT, "research")
PR = pd.concat([pd.read_csv(os.path.join(H, "nfl_futures_diagnosis_playoff_rows_2013_19.csv")), pd.read_csv(os.path.join(H, "nfl_futures_diagnosis_playoff_rows.csv"))])
MOD = {"v4wf": dict(hpo=1.8, sd=float(np.sqrt(11.37 ** 2 + 2 * 5.0 ** 2))), "v5like": dict(hpo=4.0, sd=float(np.sqrt(12.0 ** 2 + 2 * 4.0 ** 2)))}
g = games()
for c in ("home_team", "away_team"):
    g[c] = g[c].replace(FIX)
po = g[(g.game_type != "REG") & g.season.between(2013, 2025) & g.result.notna()].copy()
rows = []
for m, P in MOD.items():
    r = PR[PR.model == m].set_index(["season", "team"])
    for x in po.itertuples():
        h, a = (x.season, x.home_team), (x.season, x.away_team)
        if h not in r.index or a not in r.index:
            continue
        neutral = x.game_type == "SB" or str(x.location) == "Neutral"
        pred = r.loc[h, "rating"] - r.loc[a, "rating"] + (0 if neutral else P["hpo"])
        sh, sa = int(r.loc[h, "seed"]), int(r.loc[a, "seed"])
        rows.append(dict(model=m, season=x.season, era="2013-19" if x.season <= 2019 else "2020-25", round=x.game_type, home=x.home_team, away=x.away_team,
                         seed_h=sh, seed_a=sa, pred=pred, p_home=norm.cdf(pred / P["sd"]), actual=x.result, neutral=neutral))
D = pd.DataFrame(rows)
D.to_csv(os.path.join(H, "nfl_playoff_games.csv"), index=False)


def summ(d):
    y = (d.actual > 0).astype(float)
    b = np.polyfit(d.pred, d.actual, 1)[0] if len(d) > 5 else np.nan
    return {"games": int(len(d)), "pred_home_wins": round(float(d.p_home.sum()), 1), "actual_home_wins": int(y.sum()),
            "mean_pred_margin": round(float(d.pred.mean()), 1), "mean_actual_margin": round(float(d.actual.mean()), 1),
            "margin_slope": round(float(b), 2), "brier": round(float(((d.p_home - y) ** 2).mean()), 4)}


out = {}
for m, d in D.groupby("model"):
    o = {"all": summ(d)}
    for k, x in d.groupby("era"):
        o[k] = summ(x)
    for k, x in d.groupby("round"):
        o[k] = summ(x)
    for (e, k), x in d.groupby(["era", "round"]):
        o[f"{e} {k}"] = summ(x)
    # No. 1 seed games from the No. 1 seed's side
    s1 = d[(d.seed_h == 1) | (d.seed_a == 1)].copy()
    s1 = s1[~((s1.seed_h == 1) & (s1.seed_a == 1))]
    sgn = np.where(s1.seed_h == 1, 1, -1)
    s1["p1"] = np.where(sgn == 1, s1.p_home, 1 - s1.p_home)
    s1["pred1"] = sgn * s1.pred
    s1["act1"] = sgn * s1.actual
    for lab, x in (("all", s1), *s1.groupby("era")):
        o[f"No.1 seed games {lab}"] = {"games": int(len(x)), "pred_wins": round(float(x.p1.sum()), 1), "actual_wins": int((x.act1 > 0).sum()),
                                       "mean_pred_margin": round(float(x.pred1.mean()), 1), "mean_actual_margin": round(float(x.act1.mean()), 1),
                                       "close_games_<=7": int((x.act1.abs() <= 7).sum()), "close_wins": int(((x.act1 > 0) & (x.act1 <= 7)).sum()),
                                       "close_losses": int(((x.act1 < 0) & (x.act1 >= -7)).sum())}
    o["No.1 seed game list"] = [f"{x.season} {x.round} {x.home}-{x.away} p1={x.p1:.2f} margin1={x.act1:+.0f}" for x in s1.sort_values(["season"]).itertuples()]
    out[m] = o
json.dump(out, open(os.path.join(H, "nfl_playoff_games.json"), "w"), indent=1)
for m, o in out.items():
    print("==", m)
    for k, v in o.items():
        if k != "No.1 seed game list":
            print(k, v)
print("\n".join(out["v4wf"]["No.1 seed game list"]))
