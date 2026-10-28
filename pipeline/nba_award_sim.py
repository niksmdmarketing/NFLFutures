"""Forward simulation of NBA award chances (shared by the live site and research/nba_awards_replay.py).

Each candidate's season is simulated to the end from his numbers to date: per-game rates shrunk toward last season's
(K_RATE games), games played drawn from his share of team games (shrunk toward 85%, with health noise), talent noise on
the remaining games, and team win% from the record to date. Every simulated finish is scored by the conditional logit
(award_model weights fitted on final season lines) within that simulation's top-N pool, and from 2023-24 the 65-game rule
zeroes players short of 65 games of 15+ minutes. Probabilities are averaged over the simulations.
Replay 2010-2026 (every 14 days, weights leave-one-season-out): -log p(winner) 0.09 better than scoring stats to date
(90% interval 0.03 to 0.15), all four awards better on average; adopted 14 Oct 2026 (TypeSafe 67%).
"""
import os

import numpy as np
import pandas as pd

from nba_site import CANON, CUP, TEAMS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "nba")
SIMS = int(os.environ.get("AW_SIMS", "300"))
K_RATE = float(os.environ.get("AW_K_RATE", "10"))      # games of weight on last season's per-game rates
K_AVAIL = float(os.environ.get("AW_K_AVAIL", "10"))    # team games of weight on the 85% availability prior
AVAIL_SD = float(os.environ.get("AW_AVAIL_SD", "0.12"))
TALENT_SD = float(os.environ.get("AW_TALENT_SD", "0.08"))
RULE65 = os.environ.get("AW_RULE65", "1") == "1"
BUGFIXES = os.environ.get("AW_BUGFIXES", "0") == "1"  # opt-in candidate, never early-season shrink
STATS = ["pts", "reb", "dreb", "ast", "stl", "blk", "tov", "pm", "fga", "fta", "mins", "start", "m20", "m15"]

SPECS = {   # same pools and features as nba_site.awards
    "MVP": (lambda D: D.gshare >= .5, "eff_g", 25, ["eff_g", "ppg", "pm_g", "wp", "gshare", "ts"]),
    "DPOY": (lambda D: D.gshare >= .5, "def_g", 20, ["def_g", "bpg", "spg", "rpg", "wp", "gshare"]),
    "ROY": (lambda D: D.rookie & (D.gshare >= .3), "eff_g", 15, ["eff_g", "ppg", "mpg", "gshare", "wp"]),
    "6MOY": (lambda D: D.bench & (D.gshare >= .5), "ppg", 15, ["ppg", "mpg", "pm_g", "wp", "gshare"]),
}


def boxes(y, replay=None):
    replay = BUGFIXES if replay is None else replay
    p = os.path.join(DATA, f"player_box_{y}.csv")
    if not os.path.exists(p):
        return None
    b = pd.read_csv(p, low_memory=False)
    b = b[(b.season_type == 2) & ~b.game_id.isin(CUP.get(y, set()))]
    if "did_not_play" in b:
        b = b[~b.did_not_play.astype(str).str.lower().eq("true")]
    b = b.copy()
    b["mins"] = pd.to_numeric(b.minutes, errors="coerce").fillna(0)
    b = b[b.mins > 0]
    b["team"] = b.team_abbreviation.replace(CANON)
    for c, k in {"points": "pts", "rebounds": "reb", "defensive_rebounds": "dreb", "assists": "ast", "steals": "stl", "blocks": "blk",
                 "turnovers": "tov", "plus_minus": "pm", "field_goals_attempted": "fga", "free_throws_attempted": "fta"}.items():
        b[k] = pd.to_numeric(b[c], errors="coerce").fillna(0)
    b["start"] = b.starter.astype(str).str.lower().eq("true").astype(float)
    b["m20"] = (b.mins >= 20).astype(float)
    b["m15"] = (b.mins >= 15).astype(float)   # the rule counts 20-minute games plus up to two of 15-20 minutes; box minutes are rounded
    b["win"] = b.team_winner.astype(str).str.lower().eq("true").astype(float)
    b["date"] = pd.to_datetime(b.game_date)
    if replay:
        b = b[b.team.isin(TEAMS)]  # explicit franchises, never eventual games-played coverage
    if not replay:  # preserve the displayed model; research must not select teams using future coverage
        games_per_team = b.groupby("team").game_id.nunique()
        b = b[b.team.isin(games_per_team[games_per_team >= 40].index)]
    return b[["game_id", "date", "athlete_id", "athlete_display_name", "team", "win"] + STATS]


def team_table(b, cutoff=None):
    x = b if cutoff is None else b[b.date <= cutoff]
    g = x.drop_duplicates(["game_id", "team"])
    return g.groupby("team").agg(tg=("game_id", "nunique"), tw=("win", "sum"))


def season_lines(b, cutoff=None):
    """Per player totals to `cutoff` (team = most games), with team games and wins to date."""
    x = b if cutoff is None else b[b.date <= cutoff]
    a = x.groupby("athlete_id").agg(name=("athlete_display_name", "last"), team=("team", lambda s: s.value_counts().index[0]),
                                    gp=("game_id", "nunique"), **{k: (k, "sum") for k in STATS})
    T = team_table(b, cutoff)
    a = a.join(T, on="team")
    return a


def features(A, L):
    """Season features from totals A (per-row arrays or DataFrame columns) with league games L."""
    G = np.maximum(A["gp"], 1)
    f = {"ppg": A["pts"] / G, "rpg": A["reb"] / G, "apg": A["ast"] / G, "spg": A["stl"] / G, "bpg": A["blk"] / G,
         "tpg": A["tov"] / G, "pm_g": A["pm"] / G, "mpg": A["mins"] / G}
    f["eff_g"] = f["ppg"] + f["rpg"] + f["apg"] + f["spg"] + f["bpg"] - f["tpg"]
    f["def_g"] = f["spg"] + f["bpg"] + .3 * A["dreb"] / G
    f["ts"] = A["pts"] / np.maximum(2 * (A["fga"] + .44 * A["fta"]), 1)
    f["gshare"] = A["gp"] / L
    f["wp"] = A["wp"]
    return f


def simulate(a, prev, D, award, feats, beta, L, y, rng=None, pre=False, replay=None, diagnostics=None):
    """Average award probabilities over SIMS simulated finishes of the season (pre=True: D is a ready preseason pool)."""
    replay = BUGFIXES if replay is None else replay
    rng = rng or np.random.default_rng(y * 7 + len(award))
    poolf, rank, n, _ = SPECS[award]
    if pre:
        C = D.copy()
    else:
        # candidates: generous to-date pool (3x) so late risers are not excluded
        C = D[(D.gp >= 1)].copy()
        if award == "ROY":
            C = C[C.rookie]
        if award == "6MOY":
            C = C[(C.start / C.gp) < .6]
        C = C.sort_values(rank, ascending=False).head(3 * n)
    if C.empty:
        return {}
    m = len(C)
    tg, tw = C.tg.values.astype(float), C.tw.values.astype(float)
    rem = np.maximum(L - tg, 0)
    # per-game rates shrunk to last season's
    gp = C.gp.values.astype(float)
    rates = {}
    for k in STATS:
        r_now = C[k].values / np.maximum(gp, 1)
        pr = prev.reindex(C.index)
        r_prev = (pr[k] / pr.gp.clip(lower=1)).values if k in pr else np.full(m, np.nan)
        ok = np.isfinite(r_prev) & (pr.gp.fillna(0).values >= 10)
        rates[k] = np.where(ok, (gp * r_now + K_RATE * np.nan_to_num(r_prev)) / (gp + K_RATE), r_now)
    avail = (gp + 0.85 * K_AVAIL) / (tg + K_AVAIL)
    if pre and "avail0" in C:      # owner minutes overrides (preseason only)
        a0 = C.avail0.values.astype(float)
        avail = np.where(np.isfinite(a0), a0, avail)
    wp0 = C.wp_prior.values.astype(float) if "wp_prior" in C else np.full(m, 0.5)
    wp_hat = (tw + wp0 * 15) / (tg + 15)
    S = SIMS
    a_s = np.clip(avail[None, :] + rng.normal(0, AVAIL_SD, (S, m)), 0.0, 1.0)
    g_rem = rng.binomial(rem.astype(int)[None, :].repeat(S, 0), a_s)
    talent = 1 + rng.normal(0, TALENT_SD, (S, m))
    tot = {k: C[k].values[None, :] + g_rem * rates[k][None, :] * (talent if k not in ("mins", "start", "m20", "m15") else 1) for k in STATS}
    G = gp[None, :] + g_rem
    team_w = tw[None, :] + rng.binomial(rem.astype(int)[None, :].repeat(S, 0), np.clip(wp_hat[None, :] + rng.normal(0, .05, (S, m)), 0, 1))
    A = {**tot, "gp": G, "wp": team_w / L}
    f = features(A, L)
    rook = C.rookie.values
    bench = (tot["start"] / np.maximum(G, 1)) < .5
    elig = np.ones((S, m), bool)
    if RULE65 and y >= 2024 and (not replay or award in ("MVP", "DPOY")):
        counted = tot["m20"] + np.minimum(2, np.maximum(0, tot["m15"] - tot["m20"])) if replay else tot["m15"]
        elig = counted >= 65 - 0.5  # legacy counts all 15+; replay caps sub-20 games at two
    from nba_site import AM_norm
    names = C.name.map(AM_norm).values
    acc = np.zeros(m)
    valid_draws = 0
    rank_v = f[rank]
    for s in range(S):
        Ds = pd.DataFrame({k: np.asarray(v[s], float) for k, v in f.items()})
        Ds["rookie"], Ds["bench"] = rook, bench[s]
        okp = poolf(Ds).values
        idx = np.where(okp)[0]
        if not len(idx):
            continue
        idx = idx[np.argsort(-rank_v[s][idx])][:n]
        X = Ds.iloc[idx][feats].astype(float)
        X = ((X - X.mean()) / X.std().replace(0, np.nan)).fillna(0).values
        e = X @ beta
        w = np.exp(e - e.max()) * elig[s][idx]
        if w.sum() <= 0:
            continue
        acc[idx] += w / w.sum()
        valid_draws += 1
    if diagnostics is not None:
        diagnostics.update(draws=S, valid_draws=valid_draws, invalid_draws=S-valid_draws)
    if replay:
        if not valid_draws:
            return {}
        acc /= valid_draws  # condition both research arms on a valid award winner
        result = {}
        for name, probability in zip(names, acc):
            result[name] = result.get(name, 0.0) + float(probability)
        return result
    acc /= S
    return dict(zip(names, acc))




def live_probs(cur, award, feats, beta, rookies, games_in_season=82):
    """Award chances for the current season (end year `cur`): {normalised name: probability}. Empty before any games."""
    from nba_site import AM_norm  # noqa: F401  (simulate keys names with it)
    b = boxes(cur)
    if b is None or b.empty:
        return {}
    pb = boxes(cur - 1)
    prev = season_lines(pb) if pb is not None and not pb.empty else season_lines(b).iloc[0:0]
    a = season_lines(b)
    a["rookie"] = a.index.isin(rookies)
    a["wp"] = a.tw / a.tg.clip(lower=1)
    Lc = float(a.tg.max())
    f = features(a, Lc)
    D = a.assign(**{k: np.asarray(v, float) for k, v in f.items()})
    D["bench"] = (D.start / D.gp) < .5
    return simulate(a, prev, D, award, feats, np.asarray(beta, float), float(games_in_season), cur)


RETURN = os.environ.get("AW_RETURN", "0") == "1"     # research: players back from a near-lost season use the season before
RET_GP, RET_PREV_GP = 30, 60


def _aid(x):
    """athlete id as text without a trailing '.0' (box-score ids are read as floats)."""
    return str(x)[:-2] if str(x).endswith(".0") else str(x)


def preseason_pool(prev, award, team_wp=None, prev2=None, cur_team=None, avail0=None):
    """Preseason candidates: last season's leaders (30+ games) with zero games so far; team strength from `team_wp`
    ({team: projected win%}, e.g. the futures page) or last season's win% regressed halfway to .500.
    cur_team {athlete_id: team}: the team a player is on now (trades), used for team strength and display.
    avail0 {athlete_id: share of games}: owner minutes overrides turned into expected availability.
    prev2 + AW_RETURN=1: players under 30 games last season after 60+ the season before enter on the season before."""
    if award == "ROY" or prev is None or prev.empty:
        return None
    P = prev[prev.gp >= 30].copy()
    if RETURN and prev2 is not None and len(prev2):
        back = prev2[(prev2.gp >= RET_PREV_GP) & ~prev2.index.isin(P.index)]
        short = prev.gp.reindex(back.index).fillna(0) < RET_GP
        P = pd.concat([P, back[short.values]])
    P["wp"] = P.tw / P.tg.clip(lower=1)
    if cur_team:
        P["team"] = [cur_team.get(_aid(i), t) for i, t in zip(P.index, P.team)]
    f = features(P, float(P.tg.max()))
    rank = SPECS[award][1]
    P["_rank"] = np.asarray(f[rank], float)
    if award == "6MOY":
        P = P[(P.start / P.gp) < .6]
    P = P.sort_values("_rank", ascending=False).head(3 * SPECS[award][2])
    C0 = P[["name", "team"]].copy()
    for k in STATS:
        C0[k] = 0.0
    C0["gp"], C0["tg"], C0["tw"], C0["rookie"] = 0.0, 0.0, 0.0, False
    C0["wp_prior"] = [(team_wp or {}).get(t, 0.5 + 0.5 * (w - 0.5)) for t, w in zip(P.team, P.wp)]
    if avail0:
        C0["avail0"] = [avail0.get(_aid(i), np.nan) for i in P.index]
    return C0


def preseason_probs(prev, award, feats, beta, L, y, team_wp=None, prev2=None, cur_team=None, avail0=None, replay=None, diagnostics=None):
    C0 = preseason_pool(prev, award, team_wp, prev2, cur_team, avail0)
    if C0 is None or C0.empty:
        return {}
    return simulate(C0, prev, C0, award, feats, np.asarray(beta, float), float(L), y, pre=True, replay=replay, diagnostics=diagnostics)
