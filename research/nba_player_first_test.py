"""NBA player-first game model test per research/NBA_PLAYER_FIRST_RULE.md.
Step 1 (build): python research/nba_player_first_test.py build   -> data/research/nba_player_first_rows.csv
Step 2 (score): python research/nba_player_first_test.py score   -> research/nba_player_first_results.json
"""
import collections
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
os.environ.setdefault("BT_INS_W", "1.0")
ROWS = os.path.join(ROOT, "data", "research", "nba_player_first_rows.csv")
FIRST, LAST = int(os.environ.get("NPF_FIRST", 2014)), int(os.environ.get("NPF_LAST", 2026))


def player_box(y):
    d = pd.read_csv(os.path.join(ROOT, "data", "nba", f"player_box_{y}.csv"), low_memory=False,
                    usecols=["game_id", "season_type", "game_date", "athlete_id", "team_abbreviation", "minutes", "did_not_play"])
    d = d[pd.to_numeric(d.season_type, errors="coerce") == 2].copy()
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0)
    d = d[(d.minutes > 0) & ~d.did_not_play.astype(str).str.lower().eq("true")]
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    d = d.dropna(subset=["athlete_id"])
    d["athlete_id"] = d.athlete_id.astype(int)
    d["date"] = pd.to_datetime(d.game_date)
    return d


def build():
    import nba as N
    import nba_backtest as B
    import replay_nba as R
    N.OVERRIDES_PATH = ""
    boxes = B.load_boxes(LAST)
    last_lineup = {}                                   # team -> [athlete ids] of its latest game
    recent = collections.defaultdict(lambda: collections.deque(maxlen=10))   # athlete -> minutes of last 10 games played
    # warm up the player state with the season before FIRST
    for y in (FIRST - 1,):
        pb = player_box(y)
        for (dte, gid), G in pb.sort_values(["date", "game_id"]).groupby(["date", "game_id"], sort=True):
            for t, x in G.groupby("team_abbreviation"):
                last_lineup[t] = x.athlete_id.tolist()
            for a, m in zip(G.athlete_id, G.minutes):
                recent[a].append(m)
    out = []
    for y in range(FIRST, LAST + 1):
        g = B.season_games(boxes, y)
        if len(g) < 500:
            continue
        g["wk"] = ((g.date - g.date.min()).dt.days // 7).astype(int)
        pb = player_box(y)
        pb_by_game = {gid: x for gid, x in pb.groupby("game_id")}
        prior_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
        cur_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") == y]
        gp = collections.Counter()
        for w in range(int(g.wk.max()) + 1):
            G = g[g.wk == w]
            if G.empty:
                continue
            start = G.date.min()
            past_ids = set(g[g.date < start].gid)
            tr = pd.concat([prior_boxes, cur_boxes[cur_boxes.game_id.isin(past_ids)]]) if past_ids else prior_boxes
            RT, fit = N._fit_ratings(tr, y)
            hca = fit["home_offense_points_per_100"] if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            r = RT.set_index("team")
            pr = R._player_ratings(y, cutoff=start - pd.Timedelta(days=1))
            rating = lambda a: pr.get(int(a), -1.0)

            def strength(ids, mins):
                tot = sum(mins)
                if not ids or tot <= 0:
                    return 0.0
                return float(sum(rating(a) * m * 240.0 / tot for a, m in zip(ids, mins)) / 48.0)

            for dte, D in G.groupby("date", sort=True):
                # predict every game of this date from state before this date
                for x in D.itertuples():
                    if x.home not in r.index or x.away not in r.index:
                        continue
                    pace = (r.pace[x.home] + r.pace[x.away]) / 200
                    mA = (r.raw_net[x.home] - r.raw_net[x.away] + hca) * pace
                    rows = {}
                    for side, t in (("h", x.home), ("a", x.away)):
                        ids = last_lineup.get(t, [])
                        mins = [np.mean(recent[a]) if len(recent[a]) else 10.0 for a in ids]
                        rows["s_prev_" + side] = strength(ids, mins)
                        act = pb_by_game.get(x.gid)
                        act = act[act.team_abbreviation == t] if act is not None else None
                        rows["s_act_" + side] = strength(act.athlete_id.tolist(), act.minutes.tolist()) if act is not None and len(act) else np.nan
                    out.append(dict(season=y, week=w, date=str(dte.date()), gid=x.gid, home=x.home, away=x.away, margin=float(x.margin),
                                    pace=float(pace), mA=float(mA), gp_h=gp[x.home], gp_a=gp[x.away], **rows))
                # then update state with this date's games
                for x in D.itertuples():
                    act = pb_by_game.get(x.gid)
                    gp[x.home] += 1
                    gp[x.away] += 1
                    if act is None:
                        continue
                    for t, z in act.groupby("team_abbreviation"):
                        last_lineup[t] = z.athlete_id.tolist()
                    for a, m in zip(act.athlete_id, act.minutes):
                        recent[a].append(m)
        print("season", y, len(out), flush=True)
        pd.DataFrame(out).to_csv(ROWS, index=False)


def score():
    D = pd.read_csv(ROWS)
    D["sB"] = (D.s_prev_h - D.s_prev_a) * D.pace
    D["sB_act"] = (D.s_act_h - D.s_act_a) * D.pace
    D["early"] = (D[["gp_h", "gp_a"]].min(axis=1) < 20)
    specs = {"A": ["mA"], "B": ["sB"], "C": ["mA", "sB"], "B_actual": ["sB_act"], "C_actual": ["mA", "sB_act"]}
    preds = {k: np.full(len(D), np.nan) for k in specs}
    sds = {k: np.full(len(D), np.nan) for k in specs}
    weights = {}
    for t in range(FIRST + 1, LAST + 1):
        tr, te = (D.season < t).to_numpy(), (D.season == t).to_numpy()
        for k, cols in specs.items():
            ok = tr & D[cols].notna().all(axis=1).to_numpy()
            X = np.column_stack([np.ones(ok.sum())] + [D.loc[ok, c].to_numpy() for c in cols])
            b = np.linalg.lstsq(X, D.margin[ok].to_numpy(), rcond=None)[0]
            res = D.margin[ok].to_numpy() - X @ b
            Xt = np.column_stack([np.ones(te.sum())] + [D.loc[te, c].to_numpy() for c in cols])
            preds[k][te] = Xt @ b
            sds[k][te] = res.std()
            weights.setdefault(k, {})[t] = [round(float(v), 3) for v in b]
    T = D[D.season >= FIRST + 1].copy()
    idx = T.index.to_numpy()
    out = {"n_games": int(len(T)), "weights_by_test_season": weights}
    se, ll = {}, {}
    y = (T.margin > 0).astype(float).to_numpy()
    for k in specs:
        p = preds[k][idx]
        se[k] = (T.margin.to_numpy() - p) ** 2
        q = np.clip(norm.cdf(p / sds[k][idx]), 1e-4, 1 - 1e-4)
        ll[k] = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    out["mse"] = {k: round(float(np.nanmean(v)), 3) for k, v in se.items()}
    out["logloss"] = {k: round(float(np.nanmean(v)), 4) for k, v in ll.items()}
    seasons = sorted(T.season.unique())
    rng = np.random.default_rng(9)
    for k in ("B", "C", "B_actual", "C_actual"):
        d = se["A"] - se[k]
        ok = ~np.isnan(d)
        bys = {int(s): round(float(np.nanmean(d[(T.season == s).to_numpy()])), 3) for s in seasons}
        per = {s: d[(T.season == s).to_numpy() & ok] for s in seasons}
        bs = [np.concatenate([per[s] for s in rng.choice(seasons, len(seasons))]).mean() for _ in range(2000)]
        p = preds[k][idx]
        slope = float(np.polyfit(p[ok], T.margin.to_numpy()[ok], 1)[0])
        e = T.early.to_numpy()
        g = {"1_mse_lower_2.5pct_above_0": float(np.percentile(bs, 2.5)) > 0, "2_8_of_12": sum(v > 0 for v in bys.values()) >= 8,
             "3_logloss": out["logloss"][k] < out["logloss"]["A"], "4_early_and_late": np.nanmean(d[e]) > 0 and np.nanmean(d[~e]) > 0,
             "5_slope": 0.8 <= slope <= 1.2}
        out[f"{k}_vs_A"] = {"gain_mse": round(float(np.nanmean(d)), 3), "gain_pct": round(float(np.nanmean(d) / np.nanmean(se['A']) * 100), 2),
                            "lower_2.5pct": round(float(np.percentile(bs, 2.5)), 3), "by_season": bys,
                            "early": round(float(np.nanmean(d[e])), 3), "late": round(float(np.nanmean(d[~e])), 3), "slope": round(slope, 3),
                            "gates": {a: bool(b) for a, b in g.items()}, "all_pass": bool(all(g.values())) if k in ("B", "C") else None}
    json.dump(out, open(os.path.join(HERE, "nba_player_first_results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "weights_by_test_season"}, indent=1))


if __name__ == "__main__":
    build() if sys.argv[1] == "build" else score()
