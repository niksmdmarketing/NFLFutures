"""NBA availability: does a possession-based player impact beat the box-score player value? (research, shadow only)

Live player value (pipeline/nba_avail.py): Game Score per 36 minutes above replacement, three seasons, shrunk 400 minutes.
Challenger: our own point-in-time ridge-regression plus-minus (RAPM-style) built from SportsDataverse's NBA Stats
possession files (nba_stats_possessions: points and the ten players on the floor for every possession).

Point-in-time construction (nothing from the game being predicted or later):
  * One row per possession: +1 for each of the five offensive players, -1 for each of the five defensive players;
    target = points x 100 minus that season's league average per 100 possessions.
  * Fitted by ridge (lambda fixed at LAMBDA, a conventional value, never tuned on the test seasons) on the three previous
    regular seasons (weights 1 / 0.6 / 0.36, the same weights as the box-score ability) plus the current season's
    possessions from games dated before the snapshot. Snapshots are weekly; a game uses the latest snapshot dated on or
    before its own date, so its own possessions can never enter.
  * A player with under MIN_POSS weighted possessions is set to replacement level (like the box-score shrink).
  * value = 2 x (beta - replacement) x minutes / 48, replacement = 30th percentile of established players' betas.
Variants differ ONLY in the player's value; the baseline, status miss chances, observations, rating engine, scoring and
the walk-forward points scale are identical to research/nba_shrink_compare.py (L-live rule):
  L-live   box-score value (live)
  L-rapm   possession-impact value
  L-blend  half box-score (x0.45 to points) and half impact
Name matching between NBA Stats ids and ESPN ids is by normalised name, unique on both sides.

Usage: python research/nba_impact_test.py <ratings_nba.csv> <dir with pregame_*.csv.gz> <research cache root> <out.json>
"""
import collections
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import match_vs_market as M  # noqa: E402
import nba as N  # noqa: E402
import nba_availability2 as V2  # noqa: E402
import nba_official as O  # noqa: E402
import nba_shrink_compare as S  # noqa: E402

LAMBDA = float(os.environ.get("IMPACT_LAMBDA", 2500))
MIN_POSS = 500.0
WEIGHTS = {1: 1.0, 2: 0.6, 3: 0.36}
FIRST_POSS, LAST_POSS = 2016, 2026
VARIANTS = ["L-live", "L-rapm", "L-blend"]


def load_possessions(cache):
    """-> {season: (dates array, csr X, y)} for regular-season possessions, plus the player index."""
    glog = {}
    for y in range(FIRST_POSS, LAST_POSS + 1):
        g = pd.read_csv(os.path.join(cache, "nba_stats_player_game_logs", f"player_game_logs_{y}.csv"), usecols=["game_id", "game_date", "season_type"])
        g = g[g.season_type == "regular-season"].drop_duplicates("game_id")
        glog[y] = dict(zip(g.game_id.astype(int), pd.to_datetime(g.game_date)))
    frames = {}
    ids = set()
    cols = ["game_id", "points", "count_as_possession"] + [f"off_player_{i}" for i in range(1, 6)] + [f"def_player_{i}" for i in range(1, 6)]
    for y in range(FIRST_POSS, LAST_POSS + 1):
        p = pd.read_csv(os.path.join(cache, "nba_stats_possessions", f"nba_possessions_{y}.csv.gz"), usecols=cols, low_memory=False)
        p = p[p.count_as_possession.astype(str).str.lower().eq("true")]
        p["date"] = p.game_id.astype(int).map(glog[y])
        p = p[p.date.notna()]
        frames[y] = p.sort_values("date", kind="stable").reset_index(drop=True)
        for c in cols[3:]:
            ids.update(frames[y][c].unique())
    index = {int(k): i for i, k in enumerate(sorted(ids))}
    out = {}
    for y, p in frames.items():
        n = len(p)
        rows = np.repeat(np.arange(n), 10)
        cidx = np.stack([p[c].map(index).to_numpy() for c in cols[3:]], axis=1).reshape(-1)
        sign = np.tile(np.array([1] * 5 + [-1] * 5, dtype=float), n)
        X = sp.csr_matrix((sign, (rows, cidx)), shape=(n, len(index)))
        yv = p.points.to_numpy(float) * 100.0
        yv = yv - yv.mean()
        out[y] = (p.date.to_numpy("datetime64[D]"), X, yv)
        print("possessions", y, n, "games", p.game_id.nunique(), flush=True)
    return out, index


def snapshots(data, index, last_test):
    """{season: [(snapshot_date, {nba_id: beta}, replacement)]} weekly, each using only earlier possessions."""
    inv = {i: k for k, i in index.items()}
    full = {y: (X.T @ X, X.T @ yv) for y, (_, X, yv) in data.items()}
    out = {}
    for Y in range(FIRST_POSS + 3, last_test + 1):
        dates, X, yv = data[Y]
        start, end = dates.min(), dates.max()
        prior_A = sum(w * full[Y - k][0] for k, w in WEIGHTS.items())
        prior_b = sum(w * full[Y - k][1] for k, w in WEIGHTS.items())
        snaps, t = [], start
        while t <= end + np.timedelta64(7, "D"):
            m = dates < t
            Xp, yp = X[m], yv[m]
            A = prior_A + (Xp.T @ Xp)
            b = prior_b + (Xp.T @ yp)
            diag = A.diagonal()
            act = np.where(diag > 0)[0]
            sub = A[act][:, act].toarray() + LAMBDA * np.eye(len(act))
            beta = np.linalg.solve(sub, b[act])
            poss = diag[act]                          # weighted possessions the player was on the floor for
            keep = poss >= MIN_POSS
            rep = float(np.percentile(beta[poss >= 4 * MIN_POSS], 30)) if (poss >= 4 * MIN_POSS).any() else 0.0
            d = {int(inv[a]): (float(bb) if k else rep) for a, bb, k in zip(act, beta, keep)}
            snaps.append((pd.Timestamp(t), d, rep))
            t = t + np.timedelta64(7, "D")
        out[Y] = snaps
        print("snapshots", Y, len(snaps), "players", len(snaps[-1][1]), flush=True)
    return out


def name_map(cache, d):
    """ESPN athlete_id -> NBA Stats person id, by normalised name (unique on both sides)."""
    nba_names = collections.defaultdict(set)
    for y in range(FIRST_POSS, LAST_POSS + 1):
        n = pd.read_parquet(os.path.join(cache, "nba_stats_leaguedash", f"player_stats_advanced_{y}.parquet"), columns=["player_id", "player_name"])
        for r in n.itertuples():
            nba_names[O.name_key(r.player_name)].add(int(r.player_id))
    espn_names = collections.defaultdict(set)
    for r in d.drop_duplicates("athlete_id").itertuples():
        espn_names[O.name_key(r.athlete_display_name)].add(r.athlete_id)
    out = {}
    for k, e in espn_names.items():
        nb = nba_names.get(k, set())
        if len(e) == 1 and len(nb) == 1:
            out[next(iter(e))] = next(iter(nb))
    return out


def attach(Ob, snaps, mapping):
    """Add each observation's snapshot impact (beta - replacement, in points per game units) as column 'rapm_value'."""
    starts = {Y: np.array([s[0].to_datetime64() for s in v]) for Y, v in snaps.items()}
    vals = []
    hit = 0
    for r in Ob.itertuples():
        nid = mapping.get(r.pid)
        sn = snaps.get(r.season)
        if nid is None or sn is None:
            vals.append(np.nan)
            continue
        i = np.searchsorted(starts[r.season], np.datetime64(r.date, "D"), side="right") - 1
        if i < 0:
            vals.append(np.nan)
            continue
        _, d, rep = sn[i]
        b = d.get(nid)
        if b is None:
            vals.append(np.nan)
            continue
        hit += 1
        vals.append(2.0 * (b - rep) * r.mins / 48.0)
    Ob = Ob.copy()
    Ob["rapm_value"] = vals
    return Ob, hit


def variant_adjust(Ob, pm):
    parts = []
    for name, val in (("L-live", Ob.value), ("L-rapm", Ob.rapm_value.fillna(Ob.value * 0.45)),
                      ("L-blend", 0.5 * 0.45 * Ob.value + 0.5 * Ob.rapm_value.fillna(Ob.value * 0.45))):
        o = Ob.assign(value=val)
        S.VARIANTS = ["L-live"]
        A = S.team_adjust(o, pm)
        # team_adjust needs ability/mins for L-depth; only L-live is kept here
        parts.append(A[["game_id", "team", "L-live", "long_term", "returning"]].rename(columns={"L-live": name}))
    A = parts[0]
    for p in parts[1:]:
        A = A.merge(p[["game_id", "team", p.columns[2]]], on=["game_id", "team"])
    return A


def load_pregame_v3(d, folder):
    """Corrected (v3) official-report rows: a game counts as covered when both teams' coverage is 'listed' or 'no_rows'
    (printed game, nobody listed); 'not_yet_submitted' / 'game_not_in_report' / 'report_unavailable' games are dropped."""
    def read(kind):
        fs = [os.path.join(folder, f"{kind}_v3_{y}.csv.gz") for y in range(2020, 2027)]
        return pd.concat([pd.read_csv(f) for f in fs if os.path.exists(f)], ignore_index=True)
    P, C = read("pregame"), read("coverage")
    ok = C.assign(ok=C.coverage.isin(["listed", "no_rows"])).groupby("game_id").agg(n=("ok", "size"), ok=("ok", "all"))
    covered = {str(g) for g, r in ok.iterrows() if r.n == 2 and r.ok}
    names = d.drop_duplicates(["season", "athlete_id"])
    key = collections.defaultdict(set)
    for r in names.itertuples():
        key[(r.season, O.name_key(r.athlete_display_name))].add(r.athlete_id)
    rep = {g: {"teams": collections.defaultdict(dict), "report": "x"} for g in covered}
    hit = miss = 0
    for r in P.itertuples():
        gid = str(r.game_id)
        if gid not in rep or r.status not in S.STATUSES:
            continue
        ids = key.get((int(r.season), O.player_key(r.player)), set())
        if len(ids) == 1:
            rep[gid]["teams"][r.team][next(iter(ids))] = r.status
            hit += 1
        else:
            miss += 1
    print("v3 rows matched", hit, "unmatched", miss, "covered games", len(covered), flush=True)
    return rep, covered, {"rows_matched": hit, "rows_unmatched": miss, "games_with_report": len(covered), "source": "pregame_v3 + coverage_v3"}


def main(ratings_csv, folder, cache, out_path):
    d = V2.load()
    d["athlete_id"] = d.athlete_id.astype(str)
    rep, covered, meta = load_pregame_v3(d, folder)
    Ob = S.run(d, rep, covered)
    seasons = sorted(Ob.season.unique())
    data, index = load_possessions(cache)
    snaps = snapshots(data, index, int(max(seasons)))
    mapping = name_map(cache, d)
    Ob, hit = attach(Ob, snaps, mapping)
    cov = {"observations": int(len(Ob)), "with_impact": int(hit), "rotation_with_impact": float(Ob[Ob.rot].rapm_value.notna().mean()),
           "espn_ids_mapped": len(mapping), "lambda": LAMBDA, "min_weighted_possessions": MIN_POSS}
    print(cov, flush=True)
    R = pd.read_csv(ratings_csv, parse_dates=["date"])
    from scipy.stats import norm
    s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
    R["m"] = norm.ppf(R.p_model.clip(1e-4, 1 - 1e-4)) * s_eff
    games = d.drop_duplicates("game_id")[["game_id", "date"]].assign(game_id=lambda x: x.game_id.astype(str))
    rows, calib = [], {}
    for y in seasons[1:]:
        pm = S.p_miss_table(Ob, [s for s in seasons if s < y])
        calib[int(y)] = pm
        A = variant_adjust(Ob[Ob.season <= y], pm).merge(games, on="game_id")
        A["date"] = pd.to_datetime(A.date).dt.normalize()
        suf = lambda df, s: df.rename(columns={v: v + s for v in VARIANTS + ["long_term", "returning"]})   # noqa: E731
        h = suf(A.rename(columns={"team": "home"}), "_h")
        a = suf(A.rename(columns={"team": "away"}), "_a").drop(columns="date")
        J = R.merge(h, on=["date", "home"]).merge(a, on=["game_id", "away"]).dropna(subset=["m", "y"])
        J["long_term"] = J.long_term_h.astype(bool) | J.long_term_a.astype(bool)
        J["returning"] = J.returning_h.astype(bool) | J.returning_a.astype(bool)
        rows.append(J.assign(test_season=y))
    T = pd.concat(rows)
    T = T[T.season == T.test_season].reset_index(drop=True)
    res = {"data": meta, "impact": cov, "status_miss_by_test_season": calib, "variants": {}, "note": __doc__.split("Usage")[0].strip()}
    for v in VARIANTS:
        T["d"] = T[v + "_h"] - T[v + "_a"]
        per = []
        for y in sorted(T.season.unique()):
            tr, te = T[T.season < y], T[T.season == y]
            beta = 0.45 if not len(tr) else max(np.arange(0, 2.01, 0.05), key=lambda b: -M.ll(M.phi((tr.m - b * tr.d) / s_eff), tr.y.values))
            if v != "L-live" and not len(tr):
                beta = 1.0
            T.loc[te.index, "p_" + v] = M.phi((te.m - beta * te.d) / s_eff)
            per.append(dict(season=int(y), beta=float(beta), games=int(len(te))))
        res["variants"][v] = {"by_season": per}
    out = {}
    for name, mask in (("all", np.ones(len(T), bool)), ("long_term_absence", T.long_term.values), ("returning_player", T.returning.values)):
        x = T[mask]
        e = {"games": int(len(x)), "no_adjustment": round(M.ll(M.phi(x.m / s_eff), x.y.values), 4)}
        for v in VARIANTS:
            e[v] = round(M.ll(x["p_" + v].values, x.y.values), 4)
        e["by_season"] = {int(s): {"games": int(len(z)), "no_adjustment": round(M.ll(M.phi(z.m / s_eff), z.y.values), 4),
                                   **{v: round(M.ll(z["p_" + v].values, z.y.values), 4) for v in VARIANTS}} for s, z in x.groupby("season")}
        out[name] = e
    res["scores"] = out
    json.dump(res, open(out_path, "w"), indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "by_season"} for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
