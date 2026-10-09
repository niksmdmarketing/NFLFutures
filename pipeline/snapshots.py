"""Point-in-time team snapshots + final outcome labels (private research dataset, never published).

For every completed and in-progress season, each team is described at five checkpoints: 20 / 40 / 60 / 80 % of the
league's regular-season games and the end of the regular season. A checkpoint is a calendar date (the date of the
game at that fraction of the league's schedule); a snapshot uses ONLY games on or before that date, so nothing from
later in the season can leak backwards. Each row is then joined to the season's final labels (playoffs, rounds won,
finalist, champion, division winner, top seed, final ladder rank), which are the only columns that look forward.

Outputs (git-ignored, under data/research/): snapshots_<sport>.csv.gz and COVERAGE.json (the validation report).
Run:  python pipeline/snapshots.py [sport ...]
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trends as T_
import trends_engine as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "research")
CHECKPOINTS = (0.2, 0.4, 0.6, 0.8, 1.0)
LABELS = ["playoffs", "rounds_won", "finalist", "champ", "div_win", "top_seed", "final_wp", "final_pd", "final_lg_rank"]


def cutoff_dates(G):
    """{(season, f): (as_of_date, league_games_played)} from the league-wide game calendar."""
    out = {}
    for s, g in G.groupby("season"):
        d = g.drop_duplicates("gid").sort_values("date")
        n = len(d)
        for f in CHECKPOINTS:
            k = min(n, max(1, math.ceil(f * n)))
            out[(s, f)] = (d.date.iloc[k - 1], k)
    return out


def snapshot_rows(G, cuts, cfg):
    """One row per season, checkpoint and team using only games dated on or before the checkpoint."""
    e = cfg["pyth"]
    rows = []
    for s, g in G.groupby("season"):
        for f in CHECKPOINTS:
            as_of, lg_games = cuts[(s, f)]
            x = g[g.date <= as_of]
            for t, y in x.groupby("team"):
                y = y.sort_values("date")
                n = len(y)
                pf, pa = y.pf.sum(), y.pa.sum()
                wp = y.pts.sum() / y.maxpts.sum()
                last = y.iloc[-max(1, min(n, 10)):]
                h, a = y[y.home], y[~y.home]
                c = y[(y.pf - y.pa).abs() <= cfg["close"]]
                rows.append(dict(
                    sport=cfg["sport"], season=s, checkpoint=f, as_of=as_of, league_games=lg_games, team=t, gp=n,
                    last_game=y.date.iloc[-1], wp=wp, pd_pg=(pf - pa) / n, pf_pg=pf / n, pa_pg=pa / n,
                    pyth=E._pyth(pf, pa, e), last10_wp=last.pts.sum() / last.maxpts.sum(),
                    home_wp=h.pts.sum() / h.maxpts.sum() if len(h) else np.nan,
                    road_wp=a.pts.sum() / a.maxpts.sum() if len(a) else np.nan,
                    close_n=len(c), close_wp=c.pts.sum() / c.maxpts.sum() if len(c) else np.nan))
    D = pd.DataFrame(rows)
    D["luck"] = D.wp - D.pyth
    k = ["season", "checkpoint"]
    D["lg_rank"] = D.groupby(k).apply(lambda z: (z.wp + z.pd_pg * 1e-4).rank(ascending=False, method="min"),
                                      include_groups=False).reset_index(level=[0, 1], drop=True)
    D["pd_rank"] = D.groupby(k).pd_pg.rank(ascending=False, method="min")
    D["att_rank"] = D.groupby(k).pf_pg.rank(ascending=False, method="min")
    D["def_rank"] = D.groupby(k).pa_pg.rank(ascending=True, method="min")
    return D


def build_sport(sport):
    G, P, M, cfg = T_.LOADERS[sport]()
    cfg = dict(cfg, sport=sport)
    G = G.copy()
    G["date"] = pd.to_datetime(G.date).dt.normalize()
    P = P.copy()
    P["date"] = pd.to_datetime(P.date).dt.normalize()
    cuts = cutoff_dates(G)
    D = snapshot_rows(G, cuts, cfg)
    # final labels from the same engine the Trends tab uses
    FT = E.team_table(G, M, cfg)
    if cfg.get("post"):
        FT = cfg["post"](FT)
    S = E.series(P, cfg.get("min_games", 1), cfg.get("after"))
    FT = E.outcomes(FT, S, cfg)
    lab = FT[["season", "team", "complete", "playoffs", "rounds_won", "finalist", "champ", "div_win", "top_seed",
              "wp", "pd", "lg_rank", "conf", "div"]].rename(columns={"wp": "final_wp", "pd": "final_pd",
                                                                       "lg_rank": "final_lg_rank"})
    D = D.merge(lab, on=["season", "team"], how="left")
    for c in LABELS:                                 # labels exist only for finished seasons
        D.loc[~D.complete.fillna(False).astype(bool), c] = np.nan
    return D, G, cfg


def validate(sport, D, G, cfg):
    """Leakage and quality checks. Returns (report dict, list of problems)."""
    bad = []
    # 1. leakage: recompute from raw games with an independent filter and compare
    rng = np.random.default_rng(1)
    for i in rng.choice(len(D), size=min(300, len(D)), replace=False):
        r = D.iloc[i]
        x = G[(G.season == r.season) & (G.team == r.team) & (G.date <= r.as_of)]
        if len(x) != r.gp or (len(x) and x.date.max() > r.as_of):
            bad.append(f"leak/count mismatch {r.season} {r.team} f={r.checkpoint}")
            break
    # 2. monotone: games played never shrink across checkpoints, as-of dates increase
    for (s, t), z in D.sort_values("checkpoint").groupby(["season", "team"]):
        if (z.gp.diff().dropna() < 0).any() or (pd.to_datetime(z.as_of).diff().dropna() < pd.Timedelta(0)).any():
            bad.append(f"non-monotone {s} {t}")
            break
    # 3. end-of-season snapshot must equal the trends engine's full-season table
    end = D[D.checkpoint == 1.0].dropna(subset=["final_wp"])
    if len(end) and (abs(end.wp - end.final_wp).max() > 1e-9 or abs(end.pd_pg - end.final_pd).max() > 1e-9):
        bad.append("end-of-season snapshot differs from full-season table")
    # 4. labels: one champion per finished season, champion made the playoffs
    fin = D[(D.checkpoint == 1.0) & D.complete.fillna(False).astype(bool)]
    ch = fin.groupby("season").champ.sum()
    for s in ch[ch != 1].index:
        bad.append(f"{s}: {int(ch[s])} champions")
    if (fin[fin.champ == 1].playoffs != 1).any():
        bad.append("champion without playoffs flag")
    seasons = sorted(D.season.unique())
    rep = dict(sport=sport, seasons=f"{seasons[0]}-{seasons[-1]}", n_seasons=len(seasons), rows=len(D),
               finished_seasons=int(fin.season.nunique()), in_progress=[int(s) for s in D[~D.complete.fillna(False).astype(bool)].season.unique()],
               teams_per_season=int(D[D.checkpoint == 1.0].groupby("season").team.size().median()),
               games_per_team=float(D[D.checkpoint == 1.0].groupby("season").gp.median().median()),
               empty_cols=[c for c in D.columns if D[c].isna().all()], problems=bad,
               checks=["no future games in any snapshot (300 sampled rows recomputed)", "games and dates monotone",
                       "end snapshot == full-season table", "one champion per finished season"])
    return rep, bad


def build_all(sports=None):
    os.makedirs(OUT, exist_ok=True)
    reports = {}
    for sp in sports or list(T_.LOADERS):
        try:
            D, G, cfg = build_sport(sp)
            rep, bad = validate(sp, D, G, cfg)
            D.to_csv(os.path.join(OUT, f"snapshots_{sp}.csv.gz"), index=False)
            reports[sp] = rep
            print(f"[snapshots] {sp}: {rep['rows']} rows, {rep['n_seasons']} seasons {rep['seasons']}, "
                  f"problems={bad or 'none'}", flush=True)
        except Exception as ex:                      # one sport must not stop the others
            reports[sp] = dict(sport=sp, error=repr(ex))
            print(f"[snapshots] {sp} FAILED: {ex!r}", flush=True)
    path = os.path.join(OUT, "COVERAGE.json")
    json.dump(reports, open(path, "w"), indent=1, default=str)
    return reports


if __name__ == "__main__":
    build_all(sys.argv[1:] or None)
