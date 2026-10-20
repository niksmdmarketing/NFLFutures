"""Freeze points version D (research/NBA_POINTS_DISPERSION_RULE.md) for the forward test: log r(mu) = a + b log mu, fitted on the
appearances of 2017..season-1 (corrected rows) with the points rate exactly as in the frozen props parameters (P+T).
python research/nba_points_d_freeze.py 2027 -> model/nba_points_d_params_2027.json
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nba_minutes_tail_test as T  # noqa: E402
import nba_props_simple_test as P  # noqa: E402
import nba_points_dispersion_test as DT  # noqa: E402

season = int(sys.argv[1])
pp = json.load(open(os.path.join(ROOT, "model", f"nba_props_live_params_{season}b.json")))["props"]
D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
D = D[D.fallback == 0].reset_index(drop=True)
D = T.features(D)
FA = D[(D.season < season) & (D.season >= 2017) & D.app]
gr = {"pts": pd.Series(pp["grp_rate"]["pts"])}
rate = P.adjust(FA, "pts", P.rates(FA, "pts", pp["pts"]["m0"], gr), b=pp["pts"]["b"], tag="1")
(a, b), ll = DT.fit_ab(FA.pts.to_numpy(), rate * FA.minutes.to_numpy())
out = dict(version="pts-D1", season=season, a=a, b=b, form="negative binomial size r(mu) = exp(a + b log max(mu, 0.01)), mu = rate x minutes",
           rate="P+T as in model/nba_props_live_params_%db.json" % season, fit_rows=int(len(FA)), loglik=ll,
           rule="research/NBA_POINTS_DISPERSION_RULE.md")
path = os.path.join(ROOT, "model", f"nba_points_d_params_{season}.json")
json.dump(out, open(path, "w"), indent=1)
print(path, hashlib.sha256(open(path, "rb").read()).hexdigest(), a, b)
