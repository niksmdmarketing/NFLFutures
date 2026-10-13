"""Point-in-time replay of the NFL award chances (MVP, OPOY, DPOY, OROY, DROY, CPOY), seasons 2012-2025.

At weeks 4, 6, ..., 16 of each season the live method is rerun with only that week's stats: candidates' final lines are
projected (awards.project: rates shrunk to last season, 90% availability, rate noise), team win% is simulated from the
record to date, and the conditional logit scores every simulation. Historical injury reports are not available, so the
'Out this week' and reserve-list terms are off. Weights:
  frozen : model/settings.json (fitted offline on 2010-2025, so in-sample for every replayed season)
  loso   : refitted here on final season lines with the test season left out (honest)
  loso_T : loso with a temperature chosen leave-one-season-out from {0.6, 0.8, 1, 1.25, 1.6, 2}
Score: -log(probability given to the eventual winner), plus how often the favourite won.
Usage: python research/nfl_awards_replay.py [first] [last]
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import awards as AW  # noqa: E402
from common import FIX, TEAMS, TIX, games  # noqa: E402
from trends_awards import NFL_AW as _OLD  # noqa: E402
from award_race import WINNERS, ALIAS  # noqa: E402

NFL_AW = {k: {**_OLD.get(k, {}), **WINNERS[k]} for k in WINNERS}

AWARDS = ["MVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY"]
WEEKS = [4, 6, 8, 10, 12, 14, 16]
NS = int(os.environ.get("AW_SIMS", "400"))
TEMPS = [0.6, 0.8, 1.0, 1.25, 1.6, 2.0]


def norm(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s+(jr|sr|ii|iii|iv)\.?$", "", s.strip())
    s = ALIAS.get(re.sub(r"[^a-z ]", "", s).strip(), s)
    return re.sub(r"[^a-z]", "", s)


def weekly(y):
    path = AW.download(f"stats_player/stats_player_week_{y}.csv", max_age_h=24 * 365)
    d = pd.read_csv(path, low_memory=False)
    d = d[d.season_type == "REG"].copy()
    d["team"] = d.team.replace(FIX)
    for c in AW.COUNT + AW.EPA:
        if c not in d.columns:
            d[c] = 0.0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    return d


def lines(d):
    a = d.groupby("player_id").agg(name=("player_display_name", "first"), pos=("position", "first"), grp=("position_group", "first"),
                                   team=("team", lambda s: s.iloc[-1]), games=("week", "nunique"),
                                   **{c: (c, "sum") for c in AW.COUNT + AW.EPA}).reset_index()
    a["is_qb"] = (a.pos == "QB").astype(float)
    a["scrim"] = a.rushing_yards + a.receiving_yards
    a["tds"] = a.passing_tds + a.rushing_tds + a.receiving_tds
    a["epa"] = a.passing_epa + a.rushing_epa + a.receiving_epa
    a["tackles"] = a.def_tackles_solo + a.def_tackle_assists
    a["is_def"] = a.grp.isin(["DL", "LB", "DB"]).astype(float)
    a["nonqb_scrim"] = a.scrim * (1 - a.is_qb)
    return a


def fit(rows, feats):
    """Conditional logit on pools (season, win, feats), global standardisation; returns (b, mu, sd)."""
    X = rows[feats].astype(float).values
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    seasons = rows.season.values
    y = rows.win.values
    groups = [np.where(seasons == s)[0] for s in np.unique(seasons)]

    def nll(b):
        e = Z @ b
        return -sum(e[g][y[g] == 1].sum() - logsumexp(e[g]) for g in groups) + 0.5 * (b ** 2).sum()

    return minimize(nll, np.zeros(len(feats)), method="BFGS").x, mu, sd


def main(first, last):
    G = games()
    for c in ("home_team", "away_team"):
        G[c] = G[c].replace(FIX)
    years = list(range(2010, last + 1))
    W = {y: weekly(y) for y in range(2009, last + 1)}
    final, rook = {}, {}
    for y in years:
        r, _ = AW.roster_info(y)
        rook[y] = r
        a = lines(W[y])
        prev = lines(W[y - 1]).set_index("player_id")
        a["prev_games"] = a.player_id.map(prev.games).fillna(0.0)
        a["rookie"] = a.player_id.isin(r).astype(float)
        pct, _ = AW.team_record(G, y)
        a["wpct"] = a.team.map(pct).fillna(0.5)
        final[y] = a
    pools = {}
    for aw in AWARDS:
        P = []
        for y in years:
            if y not in NFL_AW.get(aw, {}):
                continue
            c = AW.pool(final[y], aw, s=1.0).copy()
            c["season"] = y
            c["win"] = (c.name.map(norm) == norm(NFL_AW[aw][y])).astype(float)
            if c.win.sum() == 1:
                P.append(c)
        pools[aw] = pd.concat(P, ignore_index=True)
    rows = []
    rng = np.random.default_rng(5)
    for y in range(first, last + 1):
        prev = lines(W[y - 1]).set_index("player_id")
        g = G[(G.season == y) & (G.game_type == "REG")]
        ngames = {t: int(((g.home_team == t) | (g.away_team == t)).sum()) for t in TEAMS}
        for wk in WEEKS:
            d = W[y][W[y].week <= wk]
            cur = lines(d)
            cur = cur[cur.team.isin(TIX)].reset_index(drop=True)
            cur["prev_games"] = cur.player_id.map(prev.games).fillna(0.0)
            cur["rookie"] = cur.player_id.isin(rook[y]).astype(float)
            cur["reserve"], cur["out_now"] = 0, 0
            gg = g[g.week <= wk]
            played = {t: int((((gg.home_team == t) | (gg.away_team == t)) & gg.result.notna()).sum()) for t in TEAMS}
            _, wins = AW.team_record(G[(G.season != y) | (G.week <= wk)], y)
            wp_hat = np.array([(wins[t] + 0.5 * 4) / (played[t] + 4) for t in TEAMS])
            rem = np.array([ngames[t] - played[t] for t in TEAMS])
            WS = (np.array([wins[t] for t in TEAMS])[None, :] + rng.binomial(rem[None, :].repeat(NS, 0), np.clip(wp_hat[None, :] + rng.normal(0, .08, (NS, len(TEAMS))), 0, 1)))
            WPCT = WS / np.maximum(np.array([ngames[t] for t in TEAMS]), 1)[None, :]
            ctx = {"prev": prev, "games": ngames, "played": played, "WPCT": WPCT}
            for aw in AWARDS:
                if y not in NFL_AW.get(aw, {}):
                    continue
                light = AW.project(cur, ctx, 150, rng)
                e = cur.copy()
                for k in ("attempts", "def_sacks", "def_interceptions", "def_tackles_for_loss", "passing_yards"):
                    e[k] = light[k].mean(1)
                e["scrim"], e["tds"], e["tackles"] = light["scrim"].mean(1), light["tds"].mean(1), light["tackles"].mean(1)
                c = cur.loc[AW.pool(e, aw).index].reset_index(drop=True)
                win = norm(NFL_AW[aw][y])
                if c.empty:
                    continue
                sim = AW.project(c, ctx, NS, rng)
                p_fz = AW.AW[aw]
                train = pools[aw][pools[aw].season != y]
                b, mu, sd = fit(train, p_fz["feats"])
                out = {}
                Xf = np.stack([(sim[f] - p_fz["mu"][i]) / p_fz["sd"][i] for i, f in enumerate(p_fz["feats"])], axis=-1)
                ef = (Xf @ np.array(p_fz["b"])) / p_fz["T"]
                out["frozen"] = np.exp(ef - logsumexp(ef, axis=0, keepdims=True)).mean(1)
                for T in (0.5, 0.7, 0.85):
                    out[f"frozen_T{T}"] = np.exp(ef / T - logsumexp(ef / T, axis=0, keepdims=True)).mean(1)
                Xl = np.stack([(sim[f] - mu[i]) / sd[i] for i, f in enumerate(p_fz["feats"])], axis=-1)
                el = Xl @ b
                for T in TEMPS:
                    out[f"loso_T{T}"] = np.exp(el / T - logsumexp(el / T, axis=0, keepdims=True)).mean(1)
                names = c.name.map(norm).values
                for m, p in out.items():
                    pw = float(p[names == win].sum())
                    rows.append(dict(season=y, week=wk, award=aw, method=m, p_winner=pw, fav=float(p.max()),
                                     fav_won=int(names[int(np.argmax(p))] == win), nll=-np.log(max(pw, 0.002))))
            print(y, wk, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2018
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    R = main(first, last)
    out = os.environ.get("AW_OUT") or os.path.join(ROOT, "model", "replay", "nfl_awards_replay.csv")
    R.to_csv(out, index=False)
    print(R.pivot_table(index="award", columns="method", values="nll").round(3).to_string())
