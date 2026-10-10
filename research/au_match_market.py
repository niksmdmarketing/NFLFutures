"""AFL and NBL: our point-in-time match ratings (the same SRS + prior method the Futures pages use) vs AusSportsBetting
closing head-to-head odds. Usage: python research/au_match_market.py afl|nbl <odds.xlsx>"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import match_vs_market as M  # noqa: E402

sport, xlsx = sys.argv[1], sys.argv[2]
os.environ.setdefault("TRENDS_NHL_OLD", "0")
import trends  # noqa: E402

if sport == "afl":
    import afl_site as S
    HOME, SD, K, REG = S.HGA, S.GAME_SD, S.K_PRIOR, S.PRIOR_REG
    NAMEMAP = {"Adelaide": "ADE", "Brisbane": "BRI", "Carlton": "CAR", "Collingwood": "COL", "Essendon": "ESS", "Fremantle": "FRE",
               "GWS Giants": "GWS", "Geelong": "GEE", "Gold Coast": "GCS", "Hawthorn": "HAW", "Melbourne": "MEL", "North Melbourne": "NTH",
               "Port Adelaide": "PTA", "Richmond": "RIC", "St Kilda": "STK", "Sydney": "SYD", "West Coast": "WCE", "Western Bulldogs": "WBD"}
else:
    import nbl_site as S
    HOME, SD, K, REG = S.HCA, S.GAME_SD, S.K_PRIOR, S.PRIOR_REG
    NAMEMAP = {"Adelaide 36ers": "ADL", "Brisbane Bullets": "BRI", "Cairns Taipans": "CNS", "Gold Coast": "GCB", "Illawarra Hawks": "ILL",
               "Wollongong Hawks": "ILL", "Melbourne Tigers": "MEL", "Melbourne United": "MEL", "New Zealand Breakers": "NZL",
               "Perth Wildcats": "PER", "South East Melbourne Phoenix": "SEM", "Sydney Kings": "SYD", "Tasmania JackJumpers": "TAS",
               "Townsville Crocodiles": "TSV"}

G = trends.LOADERS[sport]()[0].copy()
G["date"] = pd.to_datetime(G.date).dt.normalize()
G["ha"] = np.where(G.home, "H", "A")
G["margin"] = G.pf - G.pa
rows = []
for y in sorted(G.season.unique()):
    g = G[G.season == y]
    prev = G[G.season == y - 1]
    prior = {t: REG * v for t, v in S.srs(prev).items()} if len(prev) else {}
    dates = sorted(g.date.unique())
    n_days = len(dates)
    for i, d in enumerate(dates):
        played = g[g.date < d]
        rating = S.srs(played, prior=prior, k=K) if len(played) else dict(prior)
        for r in g[(g.date == d) & g.home].itertuples():
            m = rating.get(r.team, 0.0) - rating.get(r.opp, 0.0) + HOME
            rows.append(dict(season=y, date=d, home=r.team, away=r.opp, frac=i / max(1, n_days), y=float(r.pf > r.pa),
                             tie=r.pf == r.pa, p_model=float(M.phi(m / SD))))
P = pd.DataFrame(rows)
P = P[~P.tie]
O = pd.read_excel(xlsx, header=1)
O = O[O["Play Off Game?"].fillna("") != "Y"]
O = O[~O["Notes"].fillna("").str.contains("unreliable", case=False)]   # provider flags these closing figures as unreliable
O["date"] = pd.to_datetime(O.Date).dt.normalize()
O["home"], O["away"] = O["Home Team"].map(NAMEMAP), O["Away Team"].map(NAMEMAP)
hc = O["Home Odds Close"].fillna(O["Home Odds"])
ac = O["Away Odds Close"].fillna(O["Away Odds"])
O["p_market"] = M.devig(hc, ac)
O = O.dropna(subset=["home", "away", "p_market"])
# match on teams and date within a day either side (time zones)
J = []
for shift in (0, -1, 1):
    o = O.assign(date=O.date + pd.Timedelta(days=shift))
    J.append(P.merge(o[["date", "home", "away", "p_market"]], on=["date", "home", "away"], how="inner"))
J = pd.concat(J).drop_duplicates(["date", "home", "away"])
print(sport, "games with ratings", len(P), "matched to odds", len(J))
out, R = M.analyse(J[["season", "frac", "y", "p_model", "p_market"]])
out["matched_games"] = int(len(J))
J.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), f"match_{sport}.csv"), index=False)
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(ROOT, "model", f"match_vs_market_{sport}.json"), "w"), indent=1)
