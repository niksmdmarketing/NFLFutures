"""Test power (research/TEST_POWER_RULE.md with Amendment 1; inputs fixed in research/TEST_POWER_INPUTS.md).
Part A: per comparison and sport, sd of per-season combined futures gain, normal and paired-t MDE, seasons needed; approximate
probability of passing the three common gates under a uniform true gain (comparisons with per-market season gains).
Part B (exploratory): NBA final-wins squared error vs futures log loss on the joint-test arms.
Output: research/test_power_results.json (printed summary)."""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy import optimize, stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
Z = 1.645 + 0.842
DELTAS = [0.001, 0.002, 0.003, 0.005]


def jload(p):
    return json.load(open(os.path.join(ROOT, p)))


def from_branch(branch, path):
    out = subprocess.run(["git", "-C", ROOT, "show", f"origin/{branch}:{path}"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def nba_joint_tables():
    import nba_joint_score as SC
    d = os.path.join(ROOT, "model", "replay", "nba_joint")
    arms = {a: SC.load(d, a, SC.TEST) for a in ("A0", "A1", "A2", "A2_noscale", "A1_noleak", "A2_noleak")}
    pairs = {"NBA joint A2 vs A1": ("A1", "A2"), "NBA joint A2 vs A0": ("A0", "A2"), "NBA rosters A1 vs A0": ("A0", "A1"),
             "NBA joint no scalar vs A1": ("A1", "A2_noscale"), "NBA joint vs A1, absence rosters": ("A1_noleak", "A2_noleak")}
    out = {}
    for name, (b, c) in pairs.items():
        G = SC.pair(arms[b], arms[c])
        out[name] = G.groupby("season")[list(SC.MK)].mean()     # season x market
    return out, arms, pairs


def inputs():
    """name -> (sport, season x market DataFrame or None, per-season combined Series)."""
    C = {}
    def add(name, sport, by_season, per_market=None):
        s = pd.Series({int(k): float(v) for k, v in by_season.items()}).sort_index()
        C[name] = (sport, per_market, s)
    add("NFL efficiency weight", "NFL", jload("research/nfl_efficiency_weight_results.json")["stage2"]["per_season"])
    add("NFL non-QB injuries", "NFL", jload("research/nfl_nonqb_injury_results.json")["stage2"]["per_season"])
    add("NFL recalibration", "NFL", jload("research/nfl_recalibration_results.json")["primary"]["by_season"])
    add("NFL tau fade", "NFL", jload("research/nfl_tau_fade_results.json")["results"]["average"]["by_season"])
    add("NFL v5 promotion", "NFL", jload("research/nfl_v5_promotion_results.json")["results"]["average"]["by_season"])
    ss = from_branch("claude/nfl-state-space-test", "research/nfl_state_space_results.json")
    add("NFL state-space", "NFL", ss["stage2"]["arms"]["SS"]["gain_by_season"])
    for f, name in (("research/nhl_goalie_roster_results.json", "NHL goalie roster prior"), ("research/nhl_goalie_canonical_results.json", "NHL goalie canonical")):
        d = jload(f)["per_season_gain"]
        M = pd.DataFrame({int(k): v for k, v in d.items()}).T.sort_index()
        add(name, "NHL", M.mean(axis=1).to_dict(), M)
    add("NBA player term (corrected)", "NBA", jload("research/nba_player_first_futures2_results.json")["by_season"])
    J, _, _ = nba_joint_tables()
    for name, M in J.items():
        add(name, "NBA", M.mean(axis=1).to_dict(), M)
    return C


def t_mde(sd, S):
    df = S - 1
    tc = stats.t.ppf(0.95, df)
    f = lambda d: stats.nct.sf(tc, df, d * np.sqrt(S)) - 0.8
    return float(optimize.brentq(f, 1e-6, 50.0) * sd)


def seasons_needed(sd, target):
    return int(np.ceil((Z * sd / target) ** 2))


def rule_power(M, delta, outer=1000, inner=1000, seed=1):
    """Pass probability of G1 (season-bootstrap 5th percentile > 0), G2 (>= 70% seasons better), G3 (no market mean < -0.0005)
    when the season x market gains are centred per market and shifted by delta."""
    rng = np.random.default_rng(seed)
    X = M.to_numpy(float)
    X = X - X.mean(axis=0, keepdims=True) + delta
    S = X.shape[0]
    p_all = p_g1 = 0
    for _ in range(outer):
        Y = X[rng.integers(0, S, S)]
        c = Y.mean(axis=1)
        boots = c[rng.integers(0, S, (inner, S))].mean(axis=1)
        g1 = np.percentile(boots, 5) > 0
        g2 = (c > 0).mean() >= 0.7
        g3 = (Y.mean(axis=0) >= -0.0005).all()
        p_g1 += g1
        p_all += g1 and g2 and g3
    return round(p_g1 / outer, 3), round(p_all / outer, 3)


def part_a():
    C = inputs()
    rows, by_sport = [], {}
    for name, (sport, M, s) in C.items():
        S, sd = len(s), float(s.std(ddof=1))
        r = dict(comparison=name, sport=sport, seasons=S, mean_gain=round(float(s.mean()), 5), sd=round(sd, 5),
                 mde_normal=round(Z * sd / np.sqrt(S), 5), mde_t=round(t_mde(sd, S), 5),
                 seasons_for_0_002=seasons_needed(sd, 0.002), seasons_for_0_005=seasons_needed(sd, 0.005))
        if M is not None:
            r["rule_power"] = {str(d): dict(zip(("p_mean_gate", "p_three_gates"), rule_power(M, d))) for d in DELTAS}
        rows.append(r)
        by_sport.setdefault(sport, []).append(sd)
    sports = {}
    usual = {"NFL": 4, "NHL": 9, "NBA": 10}
    for sp, sds in by_sport.items():
        med = float(np.median(sds))
        S = usual[sp]
        sports[sp] = dict(comparisons=len(sds), sd_median=round(med, 5), sd_min=round(min(sds), 5), sd_max=round(max(sds), 5),
                          usual_seasons=S, mde_normal=round(Z * med / np.sqrt(S), 5), mde_t=round(t_mde(med, S), 5),
                          seasons_for_0_002=seasons_needed(med, 0.002), seasons_for_0_005=seasons_needed(med, 0.005))
    return rows, sports


def part_b():
    import nba_backtest as B
    import nba as N
    import nba_joint_score as SC
    _, arms, pairs = nba_joint_tables()
    boxes = B.load_boxes(2026)
    wins = {}
    for y in SC.TEST:
        g = B.season_games(boxes, y)
        w = {t: 0 for t in N.TEAMS}
        for h, a, m in zip(g.home, g.away, g.margin):
            w[h if m > 0 else a] += 1
        wins[y] = w
    cont = {}
    for a, D in arms.items():
        D = D.assign(actual=[wins[s][t] for s, t in zip(D.season, D.team)])
        D["se"] = (D.mean_wins - D.actual) ** 2
        cont[a] = D.groupby(["season", "week"]).se.mean().groupby("season").mean()
    pts, per_pair = [], {}
    for name, (b, c) in pairs.items():
        M = SC.pair(arms[b], arms[c]).groupby("season")[list(SC.MK)].mean()
        fut = M.mean(axis=1)
        cg = cont[b] - cont[c]
        S = len(fut)
        t_f = float(fut.mean() / (fut.std(ddof=1) / np.sqrt(S)))
        t_c = float(cg.mean() / (cg.std(ddof=1) / np.sqrt(S)))
        per_pair[name] = dict(futures_mean=round(float(fut.mean()), 5), wins_mse_gain_mean=round(float(cg.mean()), 3),
                              t_futures=round(t_f, 2), t_wins=round(t_c, 2),
                              within_pair_corr=round(float(np.corrcoef(fut.to_numpy(), cg.reindex(fut.index).to_numpy())[0, 1]), 3),
                              wins_mse_gain_by_season={int(k): round(float(v), 3) for k, v in cg.items()})
        for s in fut.index:
            pts.append((name, s, float(fut[s]), float(cg[s])))
    P = pd.DataFrame(pts, columns=["pair", "season", "fut", "cont"])
    pooled = float(np.corrcoef(P.fut, P.cont)[0, 1])
    rng = np.random.default_rng(1)
    seasons = np.array(sorted(P.season.unique()))
    bs = []
    for _ in range(4000):
        pick = rng.choice(seasons, len(seasons), replace=True)
        Q = pd.concat([P[P.season == s] for s in pick])
        if Q.fut.std() > 0 and Q.cont.std() > 0:
            bs.append(np.corrcoef(Q.fut, Q.cont)[0, 1])
    base_mse = {a: round(float(v.mean()), 2) for a, v in cont.items()}
    return dict(per_pair=per_pair, pooled_corr=round(pooled, 3), pooled_corr_90=[round(float(np.percentile(bs, 5)), 3), round(float(np.percentile(bs, 95)), 3)],
                arm_mean_wins_mse=base_mse, note="exploratory; nothing adopted (Amendment 1 item 3)")


if __name__ == "__main__":
    rows, sports = part_a()
    pb = part_b()
    R = dict(part_a_comparisons=rows, part_a_sports=sports, part_b=pb)
    json.dump(R, open(os.path.join(ROOT, "research", "test_power_results.json"), "w"), indent=1)
    print(json.dumps(sports, indent=1))
    for r in rows:
        print({k: r[k] for k in r if k != "rule_power"}, r.get("rule_power", ""))
    print(json.dumps({k: v for k, v in pb.items() if k != "per_pair"}, indent=1))
    for k, v in pb["per_pair"].items():
        print(k, {x: v[x] for x in v if x != "wins_mse_gain_by_season"})
