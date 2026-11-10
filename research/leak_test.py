"""Perturbation leakage test (projexions learning; TypeSafe 96%). For a season y and a cut point, scramble every result AFTER the cut
to extreme random values, re-run the replay, and require every forecast column at checkpoints AT OR BEFORE the cut to be unchanged
(outcome columns y_* and checkpoints after the cut are allowed to differ). A difference means future results leak into past forecasts.
Usage: python research/leak_test.py afl 2024 12      (AFL: cut = round)
       python research/leak_test.py nba 2024 60      (NBA: cut = day of season)
       python research/leak_test.py nfl 2024 9       (NFL: cut = week)"""
import os, sys, importlib
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
RNG = np.random.default_rng(7)


def compare(A, B, keep):
    a, b = A[keep(A)].reset_index(drop=True), B[keep(B)].reset_index(drop=True)
    cols = [c for c in a.columns if c.startswith(("p_", "mean_", "w_", "rating", "n_")) and not c.startswith("y_") and c in b.columns]
    if len(a) != len(b):
        return False, f"row count differs {len(a)} vs {len(b)}"
    bad = [(c, float(np.nanmax(np.abs(pd.to_numeric(a[c], errors='coerce') - pd.to_numeric(b[c], errors='coerce'))))) for c in cols
           if not np.allclose(pd.to_numeric(a[c], errors='coerce'), pd.to_numeric(b[c], errors='coerce'), equal_nan=True, atol=1e-12)]
    return (not bad), (f"{len(a)} rows x {len(cols)} forecast columns identical" if not bad else f"LEAK: {bad[:6]}")


def afl(y, cut):
    R = importlib.import_module("replay_afl")
    G = R.season_frames()
    A = R.run_season(G, y)
    g = G[y].copy(); r = pd.to_numeric(g.rnd, errors="coerce")
    fut = (g.season_type == "REG") & (r > cut)
    mids = g.loc[fut, "match_id"].unique()
    sc = {m: RNG.integers(0, 250, 2) for m in mids}
    for i in g.index[fut]:
        m = g.at[i, "match_id"]; s = sc[m]; first = g.at[i, "team"] == g[g.match_id == m].team.iloc[0]
        pf, pa = (s[0], s[1]) if first else (s[1], s[0])
        g.at[i, "points_for"], g.at[i, "points_against"] = pf, pa
        g.at[i, "win"] = 1.0 if pf > pa else (0.5 if pf == pa else 0.0)
        if "margin" in g.columns: g.at[i, "margin"] = pf - pa
    G2 = dict(G); G2[y] = g
    B = R.run_season(G2, y)
    return compare(A, B, lambda D: D.week <= cut)


def nba(y, cut):
    """cut = day of the season (days after the first game). Scrambles team scores of later games in the box table."""
    R = importlib.import_module("replay_nba")
    boxes = R.B.load_boxes(y)
    A = R.run_season(boxes, y)
    b = boxes.copy()
    sy = pd.to_numeric(b.season, errors="coerce") == y
    dcol = "game_date" if "game_date" in b.columns else "date"
    dd = pd.to_datetime(b[dcol].astype(str).str[:10])
    first = dd[sy & (pd.to_numeric(b.season_type, errors="coerce") == 2)].min()
    fut = sy & (dd > first + pd.Timedelta(days=cut))
    pts = [c for c in ("team_score", "opponent_team_score") if c in b.columns]
    assert pts, b.columns.tolist()
    for gid, idx in b[fut].groupby("game_id").groups.items():
        s1, s2 = RNG.integers(40, 200, 2)
        for i in idx:
            home = str(b.at[i, "team_home_away"]).lower() == "home" if "team_home_away" in b.columns else True
            b.at[i, "team_score"], b.at[i, "opponent_team_score"] = (s1, s2) if home else (s2, s1)
            if "team_winner" in b.columns: b.at[i, "team_winner"] = (s1 > s2) == home
    B_ = R.run_season(b, y)
    cutdate = first + pd.Timedelta(days=cut)
    weeks = A.drop_duplicates("week")
    keepw = set(A.week[A.week <= (cut - 1) // 7])   # weekly checkpoints at first-1, first+6, +13, ...
    return compare(A, B_, lambda D: D.week.isin(keepw))


def nfl(y, cut):
    """cut = week. Scrambles scores of games after week cut."""
    R = importlib.import_module("replay_nfl")
    g = R.games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(R.FIX)
    A = R.run_season(g, y)
    g2 = g.copy()
    fut = (g2.season == y) & (g2.week > cut)
    g2.loc[fut, "home_score"] = RNG.integers(0, 80, fut.sum())
    g2.loc[fut, "away_score"] = RNG.integers(0, 80, fut.sum())
    if "result" in g2.columns: g2.loc[fut, "result"] = g2.loc[fut, "home_score"] - g2.loc[fut, "away_score"]
    if "total" in g2.columns: g2.loc[fut, "total"] = g2.loc[fut, "home_score"] + g2.loc[fut, "away_score"]
    B_ = R.run_season(g2, y)
    return compare(A, B_, lambda D: D.week <= cut)


def mlb(y, cut):
    """cut = day of season. Scrambles runs of later games in the private MLB tables (path in MLB_DATA)."""
    sys.path.insert(0, os.environ.get("MLB_RESEARCH", "/home/claude/nflfutures-private-data/research"))
    M = importlib.import_module("mlb_steps123"); R = importlib.import_module("mlb_replay")
    data = os.environ.get("MLB_DATA", "/home/claude/nflfutures-private-data/collected_data/mlb_savant")
    def run(reg):
        tg = M.team_games(reg); seasons = sorted(int(s) for s in tg.season.dropna().unique())
        obs, parks, fits = M.build_ratings(tg, seasons)
        gr = M.game_ratings(tg, obs, parks, fits).merge(reg[["game_pk", "date", "season"]], on="game_pk")
        g = reg; po = {}
        return pd.DataFrame(R.run_season(y, po, reg, tg, gr, obs, parks, fits, 300, list(range(0, 189, 7)), False))
    g, reg, pit, bat, rep = M.load_and_check(data)
    A = run(reg)
    r2 = reg.copy(); d0 = r2[r2.season == y].date.min()
    fut = (r2.season == y) & (r2.date > d0 + pd.Timedelta(days=cut))
    r2.loc[fut, "hs"] = RNG.integers(0, 30, fut.sum()); r2.loc[fut, "as_"] = RNG.integers(0, 30, fut.sum())
    tie = fut & (r2.hs == r2.as_)
    r2.loc[tie, "as_"] = r2.loc[tie, "hs"] + 1   # keep the schedule identical (no dropped games)
    B_ = run(r2)
    return compare(A, B_, lambda D: D.week <= cut)


if __name__ == "__main__":
    sport, y, cut = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    ok, msg = {"afl": afl, "nba": nba, "nfl": nfl, "mlb": mlb}[sport](y, cut)
    print(sport, y, "cut", cut, "PASS" if ok else "FAIL", msg)
    sys.exit(0 if ok else 1)
