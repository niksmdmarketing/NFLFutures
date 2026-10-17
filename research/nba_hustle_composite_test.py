"""NBA hustle composites vs future margin (rule: model/replay/NBA_HUSTLE_COMPOSITE_RULE.md, written before any result).

Usage: python research/nba_hustle_composite_test.py [data/nba directory]
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "nba")
rng = np.random.default_rng(11)


def load_box():
    parts = []
    for f in sorted(glob.glob(os.path.join(D, "team_box_*.csv"))):
        d = pd.read_csv(f, low_memory=False)
        d = d[d.season_type == 2]
        parts.append(d)
    b = pd.concat(parts, ignore_index=True)
    b["fga"], b["fta"], b["orb"], b["tov"], b["reb"] = (b[c] for c in ("field_goals_attempted", "free_throws_attempted", "offensive_rebounds", "total_turnovers", "total_rebounds"))
    b = b.dropna(subset=["fga", "fta", "reb", "team_score", "opponent_team_score", "orb", "tov"])
    b = b[(b.fga > 0) & (b.reb > 0)]   # some provider rows carry empty box-score fields (zero shots): not usable
    own = b[["game_id", "season", "game_date", "team_id", "team_display_name", "team_score", "opponent_team_score", "fga", "fta", "orb", "tov", "reb"]]
    opp = own.rename(columns={"team_id": "opponent_team_id", "team_score": "o_score", "opponent_team_score": "_x", "fga": "o_fga", "fta": "o_fta", "orb": "o_orb",
                              "tov": "o_tov", "reb": "o_reb", "team_display_name": "_n"})[["game_id", "opponent_team_id", "o_fga", "o_fta", "o_orb", "o_tov", "o_reb"]]
    g = own.merge(b[["game_id", "team_id", "opponent_team_id"]], on=["game_id", "team_id"]).merge(opp, on=["game_id", "opponent_team_id"])
    g["margin"] = g.team_score - g.opponent_team_score
    g["poss"] = g.fga + 0.44 * g.fta - g.orb + g.tov
    g["o_poss"] = g.o_fga + 0.44 * g.o_fta - g.o_orb + g.o_tov
    g["game_date"] = pd.to_datetime(g.game_date)
    return g.sort_values(["season", "team_id", "game_date"])


def z(s):
    return (s - s.mean()) / s.std(ddof=0)


def season_rows(g, N):
    """One row per team-season: features over the first N games, margin over the rest."""
    rows = []
    for (yr, tid), t in g.groupby(["season", "team_id"]):
        if len(t) < N + 20:
            continue
        a, r = t.iloc[:N], t.iloc[N:]
        rows.append(dict(season=yr, team=tid, name=t.team_display_name.iloc[0], margin=a.margin.mean(), reb=a.reb.mean(), fta=a.fta.mean(),
                         nreb=(a.reb - a.o_reb).mean(), nfta=(a.fta - a.o_fta).mean(),
                         ortg=100 * a.team_score.sum() / a.poss.sum(), drtg=100 * a.opponent_team_score.sum() / a.o_poss.sum(), fut=r.margin.mean()))
    d = pd.DataFrame(rows)
    d["H1"] = d.groupby("season", group_keys=False).reb.transform(z) + d.groupby("season", group_keys=False).fta.transform(z)
    d["H2"] = d.groupby("season", group_keys=False).nreb.transform(z) + d.groupby("season", group_keys=False).nfta.transform(z)
    return d


def full_rows(g):
    rows = []
    for (yr, tid), t in g.groupby(["season", "team_id"]):
        if len(t) < 60:
            continue
        rows.append(dict(season=yr, team=tid, name=t.team_display_name.iloc[0], margin=t.margin.mean(), reb=t.reb.mean(), fta=t.fta.mean(),
                         nreb=(t.reb - t.o_reb).mean(), nfta=(t.fta - t.o_fta).mean(),
                         ortg=100 * t.team_score.sum() / t.poss.sum(), drtg=100 * t.opponent_team_score.sum() / t.o_poss.sum()))
    d = pd.DataFrame(rows)
    d["H1"] = d.groupby("season", group_keys=False).reb.transform(z) + d.groupby("season", group_keys=False).fta.transform(z)
    d["H2"] = d.groupby("season", group_keys=False).nreb.transform(z) + d.groupby("season", group_keys=False).nfta.transform(z)
    return d


def design(d, base, extra):
    X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in base + extra])
    return X


def loso(d, y, base, extra):
    """held-out squared errors for A (base) and B (base+extra), per season; plus pooled coefficient on the first extra column."""
    out = []
    for yr in sorted(d.season.unique()):
        tr, te = d[d.season != yr], d[d.season == yr]
        res = []
        for ex in ([], extra):
            Xt, Xe = design(tr, base, ex), design(te, base, ex)
            beta = np.linalg.lstsq(Xt, tr[y].to_numpy(float), rcond=None)[0]
            res.append(((te[y].to_numpy(float) - Xe @ beta) ** 2))
        out.append((yr, res[0].mean(), res[1].mean(), len(te)))
    beta = np.linalg.lstsq(design(d, base, extra), d[y].to_numpy(float), rcond=None)[0]
    return pd.DataFrame(out, columns=["season", "mseA", "mseB", "n"]), beta[1 + len(base)]


def report(label, d, y, base, extra, skip=()):
    d = d[~d.season.isin(skip)]
    t, c = loso(d, y, base, extra)
    gain = (t.mseA - t.mseB)
    boot = [gain.sample(len(gain), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(2000)]
    print(f"{label:<44} gain {gain.mean():+.4f} (90% {np.percentile(boot, 5):+.4f}..{np.percentile(boot, 95):+.4f})  better {int((gain > 0).sum())}/{len(gain)}  c={c:+.3f}  MSE_A {t.mseA.mean():.2f}")
    return gain.mean(), np.percentile(boot, 5), (gain > 0).mean(), c


def main():
    g = load_box()
    print("seasons", g.season.min(), "-", g.season.max(), "team-games", len(g))
    res = {}
    for N in (20, 41):
        d = season_rows(g, N)
        for H in ("H1", "H2"):
            for skip, tag in ((), ""), ((2020, 2021), " no 2020-21"):
                res[(N, H, tag)] = report(f"(a) rest of season, N={N}, {H}{tag}", d, "fut", ["margin"], [H], skip)
        report(f"(a) N={N}, H1 with ortg/drtg split", d, "fut", ["ortg", "drtg"], ["H1"])
        report(f"(a) N={N}, H2 with ortg/drtg split", d, "fut", ["ortg", "drtg"], ["H2"])
    f = full_rows(g)
    nxt = f[["season", "team", "margin"]].copy()
    nxt["season"] -= 1
    nf = f.merge(nxt.rename(columns={"margin": "next"}), on=["season", "team"])
    for H in ("H1", "H2"):
        for skip, tag in ((), ""), ((2019, 2020), " no 2019-20/2020-21"):
            report(f"(b) next season, {H}{tag}", nf, "next", ["margin"], [H], skip)
    report("(b) next season, H1 with ortg/drtg split", nf, "next", ["ortg", "drtg"], ["H1"])
    report("(b) next season, H2 with ortg/drtg split", nf, "next", ["ortg", "drtg"], ["H2"])

    # tracking composite T, season totals only, scored against next season's margin
    rows = []
    for fpath in sorted(glob.glob(os.path.join(D, "leaguehustlestatsteam_regular-season_pergame_*.parquet"))):
        yr = int(os.path.basename(fpath).split("_")[-1].split(".")[0])
        if yr == 2016:   # provider copy of 2016-17
            continue
        t = pd.read_parquet(fpath)
        t = t.assign(season=yr)
        rows.append(t[["season", "team_name", "deflections", "loose_balls_recovered", "contested_shots", "charges_drawn", "box_outs"]])
    if rows:
        T = pd.concat(rows, ignore_index=True)
        T["T"] = sum(T.groupby("season", group_keys=False)[c].transform(z) for c in ("deflections", "loose_balls_recovered", "contested_shots", "charges_drawn", "box_outs"))
        name_by_team = f.groupby(["season", "team"]).name.first().reset_index()
        ff = f.merge(T[["season", "team_name", "T"]], left_on=["season", "name"], right_on=["season", "team_name"])
        ff = ff.merge(nxt.rename(columns={"margin": "next"}), on=["season", "team"])
        print("tracking transitions:", sorted(ff.season.unique()), "rows", len(ff))
        if len(ff) > 60:
            report("(b) next season, tracking T", ff, "next", ["margin"], ["T"])
            report("(b) next season, tracking T with ortg/drtg split", ff, "next", ["ortg", "drtg"], ["T"])


if __name__ == "__main__":
    main()
