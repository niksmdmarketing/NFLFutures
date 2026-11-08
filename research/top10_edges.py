"""Top-10 backtest edges (rule: research/TOP10_BACKTEST_EDGES_RULE.md, Amendment 1). Usage: python research/top10_edges.py <qb_prior.csv> <out dir>"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M
from common import games, FIX
import ratings
S = ratings.S


def build(path):
    D = pd.read_csv(path)
    g = games()
    cols = [c for c in ("game_id", "season", "week", "gameday", "spread_line", "home_moneyline", "away_moneyline", "result", "home_team", "away_team", "location", "home_rest", "away_rest") if c in g.columns]
    g = g[g.game_type == "REG"][cols]
    D = D.merge(g.rename(columns={"game_id": "game", "result": "result_g", "home_team": "home_g", "away_team": "away_g"}), on=["game", "season", "week"], how="left")
    D = D[D.result != 0]
    D["y"] = (D.result > 0).astype(float)
    lam = S["qb"]["lambda"]
    sigma = (S["sim"]["sigma"] ** 2 + 2 * S["sim"]["tau"] ** 2) ** 0.5
    D["p_model"] = M.phi((D.base + lam * D.qdiff) / sigma)
    ml = D.home_moneyline.notna() & D.away_moneyline.notna()
    D["market_src"] = np.where(ml, "moneyline", "spread")
    D["p_market"] = np.where(ml, M.devig(M.american_to_decimal(D.home_moneyline.fillna(-110)), M.american_to_decimal(D.away_moneyline.fillna(-110))),
                             M.phi(D.spread_line / 13.4))
    D = D[D.week >= 2].dropna(subset=["p_model", "p_market"])
    D["gap"] = D.p_model - D.p_market
    D = D[D.gap != 0].copy()
    D["side"] = np.where(D.gap > 0, "home", "away")
    D["edge"] = D.gap.abs()
    D["pm_side"] = np.where(D.gap > 0, D.p_model, 1 - D.p_model)
    D["pk_side"] = np.where(D.gap > 0, D.p_market, 1 - D.p_market)
    D["y_side"] = np.where(D.gap > 0, D.y, 1 - D.y)
    return D


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def cohort(D, frac):
    k = int(round(len(D) * frac))
    A = D.sort_values("edge", ascending=False).head(k)             # model above market
    mirror = D.assign(gap2=-D.gap).sort_values("gap2", ascending=False)
    return A, mirror.head(k)


def main():
    D = build(sys.argv[1]); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    D.to_csv(os.path.join(out, "edges_all.csv"), index=False)
    print("games", len(D), "seasons", D.season.nunique(), "moneyline share", round((D.market_src == "moneyline").mean(), 3))
    print("all games model LL", round(ll(D.p_model, D.y).mean(), 4), "market LL", round(ll(D.p_market, D.y).mean(), 4))
    disc = D[D.season <= 2019]
    top = disc.sort_values("edge", ascending=False).head(10)
    keep = [c for c in ("season", "week", "game", "home", "away", "side", "pm_side", "pk_side", "edge", "base", "qdiff", "market_src", "spread_line", "home_moneyline", "away_moneyline", "result", "y_side") if c in top.columns]
    print(top[keep].to_string(index=False))
    top[keep].to_csv(os.path.join(out, "top10_discovery.csv"), index=False)
    print("top10 pm_side mean", round(top.pm_side.mean(), 3), "all games |p_model-.5| mean", round((D.p_model - .5).abs().mean(), 3))


if __name__ == "__main__":
    main()
