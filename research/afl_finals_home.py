"""AFL finals home edge (research/AFL_FINALS_HOME_RULE.md). Usage: python afl_finals_home.py <afltables.parquet>"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "pipeline")
import afl, afl_site as A
base = afl._load_frame(sys.argv[1], list(dict.fromkeys(afl.BASE_MATCH_COLS + afl.BASE_PLAYER_COLS))); base = base[base.Season.ge(2012)].copy()
_, tg = afl._matches_and_team_games(base)
rows = []
for y in sorted({r["season"] for r in tg}):
    g = A.team_games({"team_games": [r for r in tg if r["season"] == y]}, y)
    if g is None or g.empty: continue
    reg, fin = g[g.season_type == "REG"], g[(g.season_type == "FIN") & (g.ha == "H")]
    if not len(fin) or not len(reg): continue
    R = A.srs(reg)
    for r in fin.itertuples():
        rows.append(dict(season=y, rnd=r.rnd, margin=r.margin, pred=R.get(r.team, 0.0) - R.get(r.opp, 0.0), venue=r.venue))
F = pd.DataFrame(rows); F["res"] = F.margin - F.pred; F["gf"] = F.rnd.astype(str).str.upper().isin(["GF"])
print("finals rows (home-listed)", len(F), "rounds", F.rnd.value_counts().to_dict(), "HGA live", A.HGA)
rng = np.random.default_rng(1)
def ci(x):
    x = np.asarray(x, float); b = [rng.choice(x, len(x)).mean() for _ in range(4000)]
    return f"{x.mean():+.2f} [{np.percentile(b,5):+.2f}, {np.percentile(b,95):+.2f}] n={len(x)}"
for lab, X in (("non-GF discovery 2012-19", F[(~F.gf) & (F.season <= 2019)]), ("non-GF evaluation 2020-25", F[(~F.gf) & (F.season >= 2020)]),
               ("non-GF evaluation excl 2020", F[(~F.gf) & (F.season >= 2021)]), ("non-GF all", F[~F.gf]),
               ("GF discovery", F[F.gf & (F.season <= 2019)]), ("GF evaluation", F[F.gf & (F.season >= 2020)]), ("GF all", F[F.gf])):
    print(lab, ci(X.res) if len(X) > 1 else "n<2")
