"""NBA and NHL: point-in-time match ratings (us_match_ratings.py) vs closing moneylines from the Sportsbook Reviews Online
archive (via the Internet Archive). Usage: python research/us_match_market.py nba|nhl <ratings.csv> <sbr dir>"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import match_vs_market as M  # noqa: E402

sport, ratings_csv, sbr_dir = sys.argv[1:4]
NBA = {"Atlanta": "ATL", "Boston": "BOS", "Brooklyn": "BKN", "NewJersey": "BKN", "Charlotte": "CHA", "Chicago": "CHI", "Cleveland": "CLE",
       "Dallas": "DAL", "Denver": "DEN", "Detroit": "DET", "GoldenState": "GS", "Houston": "HOU", "Indiana": "IND", "LAClippers": "LAC",
       "LALakers": "LAL", "Memphis": "MEM", "Miami": "MIA", "Milwaukee": "MIL", "Minnesota": "MIN", "NewOrleans": "NO", "NewYork": "NY",
       "OklahomaCity": "OKC", "Seattle": "OKC", "Orlando": "ORL", "Philadelphia": "PHI", "Phoenix": "PHX", "Portland": "POR",
       "Sacramento": "SAC", "SanAntonio": "SA", "Toronto": "TOR", "Utah": "UTAH", "Washington": "WSH"}
NHL = {"Anaheim": "ANA", "Arizona": "ARI", "Arizonas": "ARI", "Phoenix": "ARI", "Atlanta": "WPG", "Boston": "BOS", "Buffalo": "BUF",
       "Calgary": "CGY", "Carolina": "CAR", "Chicago": "CHI", "Colorado": "COL", "Columbus": "CBJ", "Dallas": "DAL", "Detroit": "DET",
       "Edmonton": "EDM", "Florida": "FLA", "LosAngeles": "LAK", "Minnesota": "MIN", "Montreal": "MTL", "NYIslanders": "NYI",
       "NYRangers": "NYR", "Nashville": "NSH", "NewJersey": "NJD", "Ottawa": "OTT", "Philadelphia": "PHI", "Pittsburgh": "PIT",
       "SanJose": "SJS", "Seattle": "SEA", "SeattleKraken": "SEA", "St.Louis": "STL", "Tampa": "TBL", "TampaBay": "TBL", "Toronto": "TOR",
       "Vancouver": "VAN", "Vegas": "VGK", "Washington": "WSH", "Winnipeg": "WPG", "WinnipegJets": "WPG"}
MAP = NBA if sport == "nba" else NHL


def norm(t):
    return re.sub(r"\s+", "", str(t))


rows = []
for f in sorted(glob.glob(os.path.join(sbr_dir, f"{sport}_*.xlsx"))):
    m = re.search(r"(\d{4})(?:-(\d{2}))?\.xlsx$", f)
    start = int(m.group(1)) if m.group(2) else int(m.group(1)) - 1
    x = pd.read_excel(f)
    ml_col = "ML" if sport == "nba" else "Close"
    for i in range(0, len(x) - 1, 2):
        a, b = x.iloc[i], x.iloc[i + 1]
        if str(a.VH) == "H" and str(b.VH) == "V":
            a, b = b, a
        d = int(a.Date)
        mo, dy = d // 100, d % 100
        yr = start if mo >= 8 else start + 1
        try:
            date = pd.Timestamp(yr, mo, dy)
            mv, mh = float(a[ml_col]), float(b[ml_col])
        except (ValueError, TypeError):
            continue
        if not (abs(mv) >= 100 and abs(mh) >= 100):
            continue
        dv, dh = M.american_to_decimal([mv, mh])
        rows.append(dict(date=date, home=MAP.get(norm(b.Team)), away=MAP.get(norm(a.Team)), p_market=float(M.devig(dh, dv)),
                         neutral=str(b.VH) == "N"))
O = pd.DataFrame(rows).dropna(subset=["home", "away"])
P = pd.read_csv(ratings_csv, parse_dates=["date"])
J = []
for shift in (0, -1, 1):
    J.append(P.merge(O.assign(date=O.date + pd.Timedelta(days=shift)), on=["date", "home", "away"], how="inner"))
J = pd.concat(J).drop_duplicates(["date", "home", "away"])
print(sport, "rated games", len(P), "odds rows", len(O), "matched", len(J), "seasons", J.season.min(), "-", J.season.max())
out, R = M.analyse(J[["season", "frac", "y", "p_model", "p_market"]])
out["matched_games"] = int(len(J))
out["source"] = "Sportsbook Reviews Online closing moneylines (via the Internet Archive)"
J.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), f"match_{sport}.csv"), index=False)
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(os.path.dirname(HERE), "model", f"match_vs_market_{sport}.json"), "w"), indent=1)
