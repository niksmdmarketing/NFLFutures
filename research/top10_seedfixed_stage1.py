"""Amendment 3 of research/TOP10_BACKTEST_EDGES_RULE.md: Stage 1 (5 Nov method) for strict-locked, seed-fixed-not-locked, and union, 2002-2025."""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import nfl_week18_rest as W
import top10_seedfixed as F
from common import games


def main():
    g = games(); out = sys.argv[1]
    G = g[(g.game_type == "REG") & g.result.notna() & (g.season >= 2002) & (g.season <= 2025)]
    rows = []
    for y, gy in G.groupby("season"):
        last = gy.week.max(); before, fin = gy[gy.week < last], gy[gy.week == last]
        w, s = W.wins(before), W.srs(before)
        strict = W.locked(w)
        flag, _ = F.fixed_clubs(g, y)
        fixed = {t for t, v in flag.items() if v}
        for r in fin.itertuples():
            neutral = str(getattr(r, "location", "Home")).lower() == "neutral"
            res = r.result - (s[r.home_team] - s[r.away_team] + (0.0 if neutral else W.HFA))
            for grp, S_ in (("strict", strict), ("fixed_not_locked", fixed - strict), ("union", fixed | strict)):
                lh, la = r.home_team in S_, r.away_team in S_
                if lh == la: continue
                rows.append(dict(season=y, group=grp, club=r.home_team if lh else r.away_team, side=res if lh else -res))
    D = pd.DataFrame(rows); D.to_csv(os.path.join(out, "seedfixed_stage1_rows.csv"), index=False)
    rng = np.random.default_rng(1); res = {}
    seasons = sorted(G.season.unique())
    for grp, X in D.groupby("group"):
        by = X.groupby("season").side.agg(["sum", "count"]).reindex(seasons).fillna(0); b = []
        for _ in range(4000):
            pick = rng.choice(seasons, len(seasons)); n = by.loc[pick, "count"].sum()
            b.append(by.loc[pick, "sum"].sum() / n if n else np.nan)
        lo, hi = np.nanpercentile(b, [5, 95])
        res[grp] = {"n": int(len(X)), "mean": round(float(X.side.mean()), 2), "90": [round(float(lo), 2), round(float(hi), 2)], "pass": bool(hi < 0)}
    print(json.dumps(res, indent=1)); json.dump(res, open(os.path.join(out, "seedfixed_stage1.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
