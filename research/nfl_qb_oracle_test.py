"""QB perfect-knowledge futures replay (research/NFL_QB_ORACLE_RULE.md). Research only; nothing deployed.
Usage: python research/nfl_qb_oracle_test.py            (full run)
       QB_ORACLE_IDENTITY=1 python research/nfl_qb_oracle_test.py   (none arm only, checked against the v5-promotion rows)
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nfl_backtest as B  # noqa: E402
import nfl_engine as E  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, games, load_pbp, scrimmage  # noqa: E402
from nfl_futures_diagnosis import WF, V4, V5, eng_weights  # noqa: E402
from nfl_qb_backtest import starters  # noqa: E402
from nfl_v5_promotion_test import bll, slope  # noqa: E402

SEASONS = range(2013, 2026)
CHECKS = (4, 9, 13)
N = 5000
SEEDS = {"A": lambda y, w: 1000 * y + w, "B": lambda y, w: 7000 * y + w}
MK = ("div", "playoff", "seed1", "conf", "sb")
PRIMARY = [(m, w) for m in ("div", "playoff") for w in CHECKS]
LAMBDAS = (0.5, 1.0)
OUT = os.path.join(ROOT, "research")
IDENTITY = os.environ.get("QB_ORACLE_IDENTITY") == "1"


def main_qb(cur):
    s = scrimmage(cur)
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    return s.groupby("posteam").qb.agg(lambda x: x.value_counts().index[0]).to_dict()


def rows_for(g):
    rows, audit = [], []
    for y in SEASONS:
        cur_all, pri, pri2 = load_pbp(y), load_pbp(y - 1), load_pbp(y - 2)
        st = starters(cur_all[cur_all.season_type == "REG"])
        out = B.outcomes(g, y)
        ew = eng_weights(y)
        for w in CHECKS:
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            cur = cur_all[(cur_all.week <= w) & (cur_all.season_type == "REG")]
            ratings.P["coef"] = WF[str(y)]["coef"]
            b4, _ = ratings.base_ratings(cur, pri, gg, y)
            _, XT = E.team_features(cur, pri, gg, y, w + 1, 4.0, 0, False)
            b5 = XT @ ew
            greg = gg[(gg.season == y) & (gg.game_type == "REG")].sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
            vals, low, _ = ratings.qb_values(cur, pri, pri2)
            ref = main_qb(cur)

            def gap(game_id, t):
                s, r = st.get((game_id, t)), ref.get(t)
                return float(vals.get(s, low) - vals.get(r, low)) if s and r and s != r else 0.0

            fut = greg[greg.week > w]
            gh = np.array([gap(r.game_id, r.home_team) for r in fut.itertuples()])
            ga = np.array([gap(r.game_id, r.away_team) for r in fut.itertuples()])
            miss = sum(st.get((r.game_id, t)) is None for r in fut.itertuples() for t in (r.home_team, r.away_team))
            nxt = {}
            for t in TEAMS:
                f = fut[(fut.home_team == t) | (fut.away_team == t)]
                nxt[t] = gap(f.game_id.iloc[0], t) if len(f) else 0.0
            nxt_v = np.array([nxt[t] for t in TEAMS])
            audit.append(dict(season=y, week=w, future_team_games=int(2 * len(fut)), missing_starters=int(miss),
                              teams_next_gap=int((nxt_v != 0).sum()), team_games_pergame_gap=int((gh != 0).sum() + (ga != 0).sum())))
            for core, base, P in (("v4", b4, V4), ("v5", b5, V5)):
                R0 = P["scale"] * (base - base.mean())
                arms = [("none", 0.0)] if IDENTITY else [("none", 0.0)] + [(a, l) for a in ("next", "pergame") for l in LAMBDAS]
                for arm, lam in arms:
                    R, G = R0, greg
                    if arm == "next":
                        R = R0 + P["scale"] * lam * nxt_v
                    elif arm == "pergame":
                        G = greg.copy()
                        G["margin_adj"] = 0.0
                        G.loc[G.week > w, "margin_adj"] = P["scale"] * lam * (gh - ga)
                    for sset, fn in SEEDS.items():
                        res = simulate.simulate(G, R, N, P["tau"], P["sigma"], P["hfa"], seed=fn(y, w), hfa_post=P["hfa_post"],
                                                n_seeds=7 if y >= 2020 else 6)
                        for i, t in enumerate(TEAMS):
                            rows.append(dict(season=y, week=w, core=core, arm=arm, lam=lam, seedset=sset, team=t,
                                             **{"p_" + k: float(res[k][i]) for k in MK}, **{"y_" + k: float(out[k][i]) for k in MK}))
            print(y, w, audit[-1], flush=True)
    return pd.DataFrame(rows), pd.DataFrame(audit)


def identity(df):
    old = pd.read_csv(os.path.join(OUT, "nfl_v5_promotion_rows.csv.gz"))
    old = old[old.week.isin(CHECKS)].rename(columns={"arm": "core"})
    new = df[df.arm == "none"]
    m = old.merge(new, on=["season", "week", "core", "seedset", "team"], suffixes=("_o", "_n"))
    diff = max(float((m["p_" + k + "_o"] - m["p_" + k + "_n"]).abs().max()) for k in MK)
    return dict(rows_old=int(len(old)), rows_new=int(len(new)), matched=int(len(m)), max_abs_diff=diff,
                ok=bool(len(m) == len(old) == len(new) and diff < 1e-9))


def loss_table(df):
    L = {}
    for (s, w), z in df.groupby(["season", "week"]):
        for m in MK:
            L[(s, w, m)] = float(bll(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()).mean())
    return L


def evaluate(D, core, lam):
    """D: rows of one seed set (or averaged). Gains positive = second arm better."""
    seasons = list(SEASONS)
    sub = lambda arm, l: D[(D.core == core) & (D.arm == arm) & (D.lam == l)]
    L = {"none": loss_table(sub("none", 0.0)), "next": loss_table(sub("next", lam)), "pergame": loss_table(sub("pergame", lam))}
    gain = lambda a, b, cells=PRIMARY: np.array([np.mean([L[a][(s, w, m)] - L[b][(s, w, m)] for m, w in cells]) for s in seasons])
    rng = np.random.default_rng(20261027)
    idx = rng.integers(0, len(seasons), (10000, len(seasons)))
    recent = np.array(seasons) >= 2020
    out = {}
    for name, (a, b) in {"G1_none_minus_pergame": ("none", "pergame"), "G2_next_minus_pergame": ("next", "pergame"),
                         "G3_none_minus_next": ("none", "next")}.items():
        g = gain(a, b)
        out[name] = dict(mean=float(g.mean()), lower90=float(np.quantile(g[idx].mean(1), .10)), seasons_better=int((g > 0).sum()),
                         by_season={str(s): float(v) for s, v in zip(seasons, g)},
                         leave_one_out={str(s): float(np.delete(g, i).mean()) for i, s in enumerate(seasons)},
                         gain_2020_25=float(g[recent].mean()),
                         by_cell={f"{m}_w{w}": float(gain(a, b, [(m, w)]).mean()) for m, w in PRIMARY},
                         secondary={f"{m}_w{w}": float(gain(a, b, [(m, w)]).mean()) for m in ("seed1", "conf", "sb") for w in CHECKS})
    cal = {}
    for arm, l in (("none", 0.0), ("next", lam), ("pergame", lam)):
        z = sub(arm, l)
        for m, w in PRIMARY:
            zz = z[z.week == w]
            a_, b_ = slope(zz["p_" + m].to_numpy(), zz["y_" + m].to_numpy())
            cal[f"{arm}_{m}_w{w}"] = dict(intercept=float(a_), slope=float(b_))
    out["calibration"] = cal
    G1, G2 = out["G1_none_minus_pergame"], out["G2_next_minus_pergame"]
    out["gates"] = {"G1_lower90_pos": bool(G1["lower90"] > 0), "G1_ge_0.001": bool(G1["mean"] >= 0.001), "G2_lower90_pos": bool(G2["lower90"] > 0)}
    return out


def decide(g):
    if not (g["G1_lower90_pos"] and g["G1_ge_0.001"]):
        return "stop QB work for futures"
    return "build news-based per-game input" if g["G2_lower90_pos"] else "keep live whole-season logic; no per-game build"


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    df, audit = rows_for(g)
    idc = identity(df)
    print("identity", idc, flush=True)
    if IDENTITY or not idc["ok"]:
        audit.to_csv(os.path.join(OUT, "nfl_qb_oracle_audit.csv"), index=False)
        json.dump(dict(identity=idc, stopped=not idc["ok"]), open(os.path.join(OUT, "nfl_qb_oracle_identity.json"), "w"), indent=2)
        return
    df.to_csv(os.path.join(OUT, "nfl_qb_oracle_rows.csv.gz"), index=False)
    audit.to_csv(os.path.join(OUT, "nfl_qb_oracle_audit.csv"), index=False)
    avg = df.groupby(["season", "week", "core", "arm", "lam", "team"], as_index=False).mean(numeric_only=True)
    res = {}
    for core in ("v5", "v4"):
        for lam in LAMBDAS:
            k = f"{core}_lam{lam}"
            res[k] = {s: evaluate(df[df.seedset == s], core, lam) for s in SEEDS}
            res[k]["average"] = evaluate(avg, core, lam)
            agree = all(res[k]["A"]["gates"][x] == res[k]["B"]["gates"][x] for x in res[k]["A"]["gates"])
            res[k]["seed_sets_agree"] = agree
            res[k]["decision"] = decide(res[k]["average"]["gates"]) if agree else "inconclusive"
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    outj = dict(rule="research/NFL_QB_ORACLE_RULE.md", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
                identity=idc, primary="v5_lam0.5", decision=res["v5_lam0.5"]["decision"], results=res,
                code_sha256=sha(__file__), rule_sha256=sha(os.path.join(OUT, "NFL_QB_ORACLE_RULE.md")))
    open(os.path.join(OUT, "nfl_qb_oracle_results.json"), "w").write(json.dumps(outj, indent=2))
    print(json.dumps({k: dict(decision=v["decision"], **{n: {x: v["average"][n][x] for x in ("mean", "lower90", "seasons_better")}
                      for n in ("G1_none_minus_pergame", "G2_next_minus_pergame", "G3_none_minus_next")}) for k, v in res.items()}, indent=2))


if __name__ == "__main__":
    main()
