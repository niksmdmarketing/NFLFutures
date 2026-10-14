"""Game-level walk-forward test: does the player-based team strength (research/nfl_player_ratings.py) add to the
recency engine ratings? Stage 1: engine prediction for season t from ridge on 2010..t-1 (as nfl_engine.score). Stage 2:
margin = engine + b x (home player net - away player net) x PLAYS, b fitted on seasons 2018..t-1 only (test 2019-2025).
Usage: python research/nfl_player_test.py <engine tag> <player feature csv>"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
from common import FIX, games  # noqa: E402


def game_rows():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows = []
    for y in range(2010, 2026):
        reg = g[(g.season == y) & (g.game_type == "REG")]
        for w in sorted(reg.week.unique()):
            for r in reg[reg.week == w].itertuples():
                if pd.isna(r.result):
                    continue
                rows.append((r.game_id, y, int(w), r.home_team, r.away_team))
    return pd.DataFrame(rows, columns=["game_id", "season", "week", "home", "away"])


def main(tag, feat):
    d = np.load(os.path.join(ROOT, "data", "research", f"nfl_eng_{tag}.npz"), allow_pickle=True)
    X, y, s = d["X"], d["y"], d["s"]
    G = game_rows()
    assert len(G) == len(y), (len(G), len(y))
    F = pd.read_csv(feat)
    net = F.set_index(["game_id", "team"])[os.environ.get("PT_COL", "net")]
    G["pdiff"] = [net.get((gid, h), np.nan) - net.get((gid, a), np.nan) for gid, h, a in zip(G.game_id, G.home, G.away)]
    sd = X[s < 2013].std(0)
    sd[sd == 0] = 1
    Xs = X / sd
    eng = np.full(len(y), np.nan)
    sig = {}
    for t in range(2013, 2026):
        tr, te = s < t, s == t
        m = Ridge(alpha=ratings.P["alpha"], fit_intercept=True).fit(Xs[tr], y[tr])
        eng[te] = m.predict(Xs[te])
        sig[t] = (y[tr] - m.predict(Xs[tr])).std()
    G["y"], G["eng"] = y, eng
    out = []
    for t in range(2019, 2026):
        tr = (G.season >= 2018) & (G.season < t) & G.pdiff.notna() & G.eng.notna()
        te = (G.season == t)
        r = G.y[tr] - G.eng[tr]
        b = float(np.sum(r * G.pdiff[tr]) / np.sum(G.pdiff[tr] ** 2))
        p0 = G.eng[te]
        p1 = G.eng[te] + b * G.pdiff[te].fillna(0)
        yy = G.y[te]
        keep = yy != 0
        def ll(p):
            q = norm.cdf(p / sig[t])
            yw = (yy > 0).astype(float)
            return float(-np.mean((yw * np.log(q) + (1 - yw) * np.log(1 - q))[keep]))
        out.append(dict(season=t, b=b, rmse0=float(np.sqrt(np.mean((yy - p0) ** 2))), rmse1=float(np.sqrt(np.mean((yy - p1) ** 2))),
                        ll0=ll(p0), ll1=ll(p1), coverage=float(G.pdiff[te].notna().mean())))
    R = pd.DataFrame(out)
    print(R.round(4).to_string(index=False))
    d_ll = R.ll0 - R.ll1
    print("log loss gain %.4f better %d/%d | rmse gain %.3f" % (d_ll.mean(), (d_ll > 0).sum(), len(R), (R.rmse0 - R.rmse1).mean()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
