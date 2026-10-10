"""NFL: our point-in-time match ratings (frozen v4 engine, incl. QB layer) vs closing lines, 2006-2025."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import match_vs_market as M
from common import games, FIX
import ratings
S = ratings.S
files = sys.argv[1:]
D = pd.concat([pd.read_csv(f) for f in files], ignore_index=True).drop_duplicates("game")
g = games()
g = g[g.game_type == "REG"][["game_id", "season", "week", "spread_line", "home_moneyline", "away_moneyline", "result"]]
D = D.merge(g.rename(columns={"game_id": "game"}), on=["game", "season", "week"], how="left", suffixes=("", "_g"))
D = D[D.result != 0]
D["y"] = (D.result > 0).astype(float)
lam = S["qb"]["lambda"]
sigma = (S["sim"]["sigma"] ** 2 + 2 * S["sim"]["tau"] ** 2) ** 0.5     # game spread + rating uncertainty, as in the simulation
D["p_model"] = M.phi((D.base + lam * D.qdiff) / sigma)
ml = D.home_moneyline.notna() & D.away_moneyline.notna()
D["p_market"] = np.where(ml, M.devig(M.american_to_decimal(D.home_moneyline.fillna(-110)), M.american_to_decimal(D.away_moneyline.fillna(-110))),
                         M.phi(D.spread_line / 13.4))
nweeks = D.groupby("season").week.transform("max")
D["frac"] = (D.week - 1) / nweeks
D.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), "match_nfl.csv"), index=False)
out, R = M.analyse(D[["season", "frac", "y", "p_model", "p_market"]])
out["note"] = "weeks 2+; rating weights were trained on 2010-2021, so those seasons are in-sample for our model"
oos = D[(D.season >= 2022) | (D.season < 2010)]
out["outside_training_years"] = {"model": M.ll(oos.p_model.values, oos.y.values), "market": M.ll(oos.p_market.values, oos.y.values), "games": int(len(oos))}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model", "match_vs_market_nfl.json"), "w"), indent=1)
