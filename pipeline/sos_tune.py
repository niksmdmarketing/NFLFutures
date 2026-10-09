"""Tunes the schedule-context model per sport on past results (run offline: python pipeline/sos_tune.py).

Pre-game ratings come from a sequential margin-Elo (no future information). Residual margin is then regressed on
home advantage, short rest, long rest and travel. Three variants are compared on the last five seasons, which were not
used to fit; the chosen variant (TypeSafe picks it from this table) and its coefficients go to pipeline/sos_params.json.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sos_params.json")

# days since the previous game: <= short counts as short rest, >= long as long rest
REST = {"nfl": (5, 10), "nhl": (1, 4), "nba": (1, 4), "nbl": (2, 7), "afl": (5, 9)}

# (lat, lon) of each club's home city; travel = distance between the two clubs' home cities
COORDS = {
    "nfl": dict(ARI=(33.5, -112.1), ATL=(33.8, -84.4), BAL=(39.3, -76.6), BUF=(42.8, -78.8), CAR=(35.2, -80.9), CHI=(41.9, -87.6),
                CIN=(39.1, -84.5), CLE=(41.5, -81.7), DAL=(32.8, -97.1), DEN=(39.7, -105.0), DET=(42.3, -83.0), GB=(44.5, -88.1),
                HOU=(29.7, -95.4), IND=(39.8, -86.2), JAX=(30.3, -81.6), KC=(39.1, -94.6), LA=(34.0, -118.3), LAC=(34.0, -118.3),
                LV=(36.1, -115.2), MIA=(25.96, -80.2), MIN=(45.0, -93.3), NE=(42.1, -71.3), NO=(30.0, -90.1), NYG=(40.8, -74.1),
                NYJ=(40.8, -74.1), PHI=(39.9, -75.2), PIT=(40.4, -80.0), SEA=(47.6, -122.3), SF=(37.4, -122.0), TB=(27.98, -82.5),
                TEN=(36.2, -86.8), WAS=(38.9, -76.9)),
    "nhl": dict(ANA=(33.8, -117.9), BOS=(42.4, -71.1), BUF=(42.9, -78.9), CAR=(35.8, -78.7), CBJ=(40.0, -83.0), CGY=(51.0, -114.1),
                CHI=(41.9, -87.7), COL=(39.7, -105.0), DAL=(32.8, -96.8), DET=(42.3, -83.1), EDM=(53.5, -113.5), FLA=(26.2, -80.3),
                LAK=(34.0, -118.3), MIN=(44.9, -93.1), MTL=(45.5, -73.6), NJD=(40.7, -74.2), NSH=(36.2, -86.8), NYI=(40.7, -73.6),
                NYR=(40.75, -74.0), OTT=(45.3, -75.9), PHI=(39.9, -75.2), PIT=(40.4, -80.0), SEA=(47.6, -122.35), SJS=(37.3, -121.9),
                STL=(38.6, -90.2), TBL=(27.9, -82.5), TOR=(43.6, -79.4), UTA=(40.8, -111.9), VAN=(49.3, -123.1), VGK=(36.1, -115.2),
                WPG=(49.9, -97.1), WSH=(38.9, -77.0), ARI=(33.5, -112.1), PHX=(33.5, -112.1), ATL=(33.8, -84.4)),
    "nba": dict(ATL=(33.8, -84.4), BKN=(40.7, -74.0), BOS=(42.4, -71.1), CHA=(35.2, -80.8), CHI=(41.9, -87.7), CLE=(41.5, -81.7),
                DAL=(32.8, -96.8), DEN=(39.7, -105.0), DET=(42.3, -83.1), GS=(37.8, -122.4), HOU=(29.75, -95.4), IND=(39.8, -86.2),
                LAC=(34.0, -118.3), LAL=(34.0, -118.3), MEM=(35.1, -90.05), MIA=(25.8, -80.2), MIL=(43.0, -87.9), MIN=(44.98, -93.3),
                NO=(29.95, -90.1), NY=(40.75, -74.0), OKC=(35.5, -97.5), ORL=(28.5, -81.4), PHI=(39.9, -75.2), PHX=(33.45, -112.07),
                POR=(45.5, -122.7), SA=(29.4, -98.5), SAC=(38.6, -121.5), TOR=(43.6, -79.4), UTAH=(40.8, -111.9), WSH=(38.9, -77.0),
                NJ=(40.7, -74.0), NOH=(29.95, -90.1), NOK=(35.5, -97.5), SEA=(47.6, -122.3), VAN=(49.3, -123.1), GSW=(37.8, -122.4),
                NYK=(40.75, -74.0), SAS=(29.4, -98.5), NOP=(29.95, -90.1), UTA=(40.8, -111.9), WAS=(38.9, -77.0), PHO=(33.45, -112.07)),
    "nbl": dict(SYD=(-33.9, 151.2), TAS=(-42.9, 147.3), PER=(-31.95, 115.86), NZL=(-36.85, 174.76), CNS=(-16.9, 145.8),
                MEL=(-37.8, 145.0), SEM=(-38.0, 145.1), BRI=(-27.5, 153.0), ADL=(-34.9, 138.6), ILL=(-34.4, 150.9),
                NZB=(-36.85, 174.76), WOL=(-34.4, 150.9)),
    "afl": dict(ADE=(-34.9, 138.6), BRI=(-27.5, 153.0), CAR=(-37.8, 144.97), COL=(-37.8, 144.98), ESS=(-37.75, 144.9), FRE=(-32.05, 115.75),
                GCS=(-28.0, 153.4), GEE=(-38.15, 144.36), GWS=(-33.85, 151.07), HAW=(-37.85, 145.0), MEL=(-37.82, 144.98),
                NTH=(-37.8, 144.95), PTA=(-34.85, 138.5), RIC=(-37.83, 144.99), STK=(-37.86, 144.98), SYD=(-33.9, 151.2),
                WBD=(-37.8, 144.9), WCE=(-31.95, 115.86)),
}


def km(sport, a, b):
    ca, cb = COORDS[sport].get(a), COORDS[sport].get(b)
    if ca is None or cb is None:
        return 0.0
    la1, lo1, la2, lo2 = map(math.radians, (*ca, *cb))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def rest_flags(sport, days):
    """days since the team's previous game -> (short, long) flags; unknown (first game) counts as neither."""
    s, l = REST[sport]
    if days is None or days != days:
        return 0.0, 0.0
    return float(days <= s), float(days >= l)


def history(sport):
    """One row per past regular-season game: season, date, home, away, margin (home - away) and context features."""
    import trends as T_
    G = T_.LOADERS[sport]()[0].copy()
    G["date"] = pd.to_datetime(G.date).dt.normalize()
    G = G.sort_values(["season", "team", "date"])
    G["rest"] = G.groupby(["season", "team"]).date.diff().dt.days
    sh, lo = zip(*[rest_flags(sport, d) for d in G.rest])
    G["short"], G["long"] = sh, lo
    h = G[G.home].drop(columns=["home"]).rename(columns={"team": "home", "opp": "away", "short": "sh_h", "long": "lo_h"})
    a = G[~G.home][["gid", "team", "short", "long"]].rename(columns={"team": "away2", "short": "sh_a", "long": "lo_a"})
    H = h.merge(a, on="gid", how="inner")
    H = H[H.away == H.away2].drop_duplicates("gid")
    H["margin"] = H.pf - H.pa
    H["dist"] = [km(sport, x, y) / 1000 for x, y in zip(H.home, H.away)]
    H = H.sort_values(["date", "gid"]).reset_index(drop=True)
    return H[["season", "date", "home", "away", "margin", "sh_h", "sh_a", "lo_h", "lo_a", "dist"]]


def elo_pre(H, k, keep, hfa, sd_scale=1.0):
    """Pre-game rating difference (home - away) from a margin Elo that only sees earlier games."""
    r, d = {}, np.zeros(len(H))
    season = None
    for i, (s, h, a, m) in enumerate(zip(H.season.values, H.home.values, H.away.values, H.margin.values)):
        if s != season:
            for t in r:
                r[t] *= keep
            season = s
        diff = r.get(h, 0.0) - r.get(a, 0.0)
        d[i] = diff
        err = m - (diff + hfa)
        r[h] = r.get(h, 0.0) + k * err
        r[a] = r.get(a, 0.0) - k * err
    return d


def design(H, d, variant):
    cols = [np.ones(len(H))]
    if variant >= 1:
        cols += [(H.sh_h - H.sh_a).values, (H.lo_h - H.lo_a).values]
    if variant >= 2:
        cols += [H.dist.values]
    return np.column_stack(cols)


def tune(sport):
    H = history(sport)
    seasons = sorted(H.season.unique())
    best = None
    hfa0 = H.margin.mean()
    for k in (0.01, 0.02, 0.03, 0.05, 0.08):
        for keep in (0.4, 0.6, 0.8):
            d = elo_pre(H, k, keep, hfa0)
            ok = H.season >= seasons[2]
            mse = float(((H.margin - d - hfa0)[ok] ** 2).mean())
            if best is None or mse < best[0]:
                best = (mse, k, keep, d)
    mse0, k, keep, d = best
    test_seasons = seasons[-5:]
    test = H.season.isin(test_seasons).values
    train = ~test & (H.season >= seasons[2]).values
    y = (H.margin - d).values
    rows, coefs = [], {}
    for v, name in ((0, "home advantage only"), (1, "+ rest"), (2, "+ rest + travel")):
        X = design(H, d, v)
        beta = np.linalg.lstsq(X[train], y[train], rcond=None)[0]
        pred = X @ beta
        mse = float(((y - pred)[test] ** 2).mean())
        full = np.linalg.lstsq(X[H.season >= seasons[2]], y[H.season >= seasons[2]], rcond=None)[0]
        rows.append(dict(variant=v, name=name, test_rmse=round(math.sqrt(mse), 4), train_beta=[round(float(b), 3) for b in beta]))
        coefs[v] = [float(b) for b in full]
    base = rows[0]["test_rmse"]
    for r in rows:
        r["gain_pct"] = round(100 * (base ** 2 - r["test_rmse"] ** 2) / base ** 2, 3)
    return dict(sport=sport, games=len(H), seasons=f"{seasons[0]}-{seasons[-1]}", elo_k=k, elo_keep=keep, elo_rmse=round(math.sqrt(mse0), 3),
                test_seasons=[int(s) for s in test_seasons], variants=rows, coefs=coefs)


if __name__ == "__main__":
    os.environ.setdefault("TRENDS_NHL_OLD", "0")
    out = {}
    for sp in sys.argv[1:] or ["nfl", "nhl", "nba", "nbl", "afl"]:
        out[sp] = tune(sp)
        print(json.dumps({k: v for k, v in out[sp].items() if k != "coefs"}), flush=True)
    json.dump(out, open(os.path.join(os.environ.get("TMPDIR", "/tmp"), "sos_tune.json"), "w"), indent=1)
