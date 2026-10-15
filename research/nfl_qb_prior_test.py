"""Does a QB-availability correction of the previous-season prior improve NFL game predictions? (research, v5 candidate)

The v4 rating blends this season's play-by-play components with the whole previous season. If the current starter
missed games last season (e.g. Lamar Jackson 12/17 starts in 2025), the prior partly describes the backups. Candidate:
  qp(team) = w_prior x (value of this season's reference QB - dropback-weighted value of last season's QBs)
with w_prior = k_pass / (dropbacks so far + k_pass), the prior's weight in the passing components, and the same QB values
the live QB layer uses. Prediction = v4 base + 0.5 x existing QB change term + L x (qp_home - qp_away).
Point-in-time: every week, ratings and QB values from earlier weeks only (same as pipeline/nfl_qb_backtest.py).
Usage: python research/nfl_qb_prior_test.py [first] [last] [max_week]    -> $TMPDIR/qb_prior.csv and a summary
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import ratings  # noqa: E402
from common import FIX, TEAMS, games, load_pbp, scrimmage  # noqa: E402
from nfl_qb_backtest import main_qb, starters  # noqa: E402

FIRST, LAST = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2008, 2025)
MAXW = int(sys.argv[3]) if len(sys.argv) > 3 else 10
GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)


def qb_mix(pbp):
    """team -> {qb: share of the team's dropbacks} for one season."""
    s = scrimmage(pbp)
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    c = s.groupby(["posteam", "qb"]).size()
    out = {}
    for (t, q), n in c.items():
        out.setdefault(t, {})[q] = n
    return {t: {q: n / sum(d.values()) for q, n in d.items()} for t, d in out.items()}


def run():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    S = ratings.S
    scale, hfa = S["sim"].get("rating_scale", 1.0), S["sim"]["hfa"]
    kp = ratings.P["k"]["pass"]
    rows = []
    for y in range(FIRST, LAST + 1):
        cur_all, pri, pri2 = load_pbp(y), load_pbp(y - 1), load_pbp(y - 2)
        st = starters(cur_all)
        pri_main, mix = main_qb(pri), qb_mix(pri)
        reg = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
        for w in sorted(reg.week.unique()):
            if w > MAXW:
                continue
            cur = cur_all[cur_all.week < w]
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.week >= w), "result"] = np.nan
            base, comp = ratings.base_ratings(cur, pri, gg, y)
            vals, low, _ = ratings.qb_values(cur, pri, pri2)
            ref = {**pri_main, **(main_qb(cur) if len(cur) else {})}
            B = dict(zip(TEAMS, base))
            ndb = comp.n_db_off.to_dict() if "n_db_off" in comp else {}
            qp = {}
            for t in TEAMS:
                r_id = ref.get(t)
                m = mix.get(t)
                if not r_id or not m:
                    qp[t] = 0.0
                    continue
                prior_val = sum(sh * vals.get(q, low) for q, sh in m.items())
                wp = kp / (ndb.get(t, 0.0) + kp)
                qp[t] = wp * (vals.get(r_id, low) - prior_val)
            for r in reg[reg.week == w].itertuples():
                d = {}
                for side, t in (("h", r.home_team), ("a", r.away_team)):
                    s_id, r_id = st.get((r.game_id, t)), ref.get(t)
                    d[side] = vals.get(s_id, low) - vals.get(r_id, low) if s_id and r_id and s_id != r_id else 0.0
                rows.append(dict(season=y, week=w, game=r.game_id, home=r.home_team, away=r.away_team, result=r.result,
                                 base=scale * (B[r.home_team] - B[r.away_team]) + hfa, qdiff=scale * (d["h"] - d["a"]),
                                 qpdiff=scale * (qp[r.home_team] - qp[r.away_team]), qp_h=qp[r.home_team], qp_a=qp[r.away_team]))
        print("season", y, flush=True)
    return pd.DataFrame(rows)


def summary(D):
    lam = ratings.S["qb"]["lambda"]
    D = D.copy()
    D["base2"] = D.base + lam * D.qdiff
    out = []
    for L in GRID:
        e = D.result - (D.base2 + L * D.qpdiff)
        out.append((L, float(np.sqrt((e ** 2).mean())), D.assign(se=e ** 2).groupby("season").se.mean()))
    print("all weeks <=", MAXW, "games", len(D))
    for L, rm, _ in out:
        print(f"  L {L:<5} RMSE {rm:.4f}")
    x, r = D.qpdiff.values, (D.result - D.base2).values
    b = float((x * r).sum() / (x * x).sum()); se = float(np.sqrt(((r - b * x) ** 2).sum() / (len(x) - 1) / (x * x).sum()))
    print("free slope on qpdiff", round(b, 3), "se", round(se, 3))
    # walk-forward: choose L on earlier seasons, score the next
    seasons = sorted(D.season.unique())
    tab = pd.DataFrame({L: s for L, _, s in out})
    wf = []
    for i, y in enumerate(seasons):
        if i < 3:
            continue
        best = tab.loc[seasons[:i]].mean().idxmin()
        wf.append((y, best, tab.loc[y, best], tab.loc[y, 0.0]))
    W = pd.DataFrame(wf, columns=["season", "L", "mse_wf", "mse_base"])
    d = W.mse_base - W.mse_wf
    print("walk-forward picks", W.L.tolist(), "MSE gain", round(d.mean(), 3), "better", int((d > 0).sum()), "/", len(d))
    big = D[D.qpdiff.abs() > 1.0]
    if len(big):
        for L in (0.0, 0.5, 1.0):
            e = big.result - (big.base2 + L * big.qpdiff)
            print(f"  games with |qp gap| > 1 point ({len(big)}): L {L} RMSE {np.sqrt((e ** 2).mean()):.3f}")


if __name__ == "__main__":
    D = run()
    D.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), "qb_prior.csv"), index=False)
    summary(D)
