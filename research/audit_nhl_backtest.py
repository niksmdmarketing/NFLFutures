"""GPT audit item 2 (research only): NHL back-test checkpoint partition and outcome labels, paired against the
current back-test. Live code is imported unchanged; nothing is written outside the scratch output path.

Current back-test (nhl_model.backtest): each team's first N games count as played (per team), remaining = home
team's games after its Nth; state treats every win as a regulation win (ROW = RW); labels rank points, wins, GD.
Fixed variant: one league-wide checkpoint DATE (the first date by which teams average N games played); each game is
played or remaining for both sides at once; RW = wins where the loser did not take an OT loss, ROW = RW + OT/SO wins
(shootout wins cannot be separated per game: ROW is an upper bound); labels = teams that actually appear in that
season's playoff games, division winners by points, RW, ROW, wins, GD from the official season table.
Both variants use the same settings (params_before: earlier seasons only), the same simulator and the same seeds.
Usage: python research/audit_nhl_backtest.py <published nhl/data dir> <out.json>
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nhl  # noqa: E402
import nhl_model as M  # noqa: E402

nhl.NHL_OUT = M.nhl.NHL_OUT = sys.argv[1]
SEEDS = (3, 11, 29)
SIMS = 3000


def ll(p, y, lo=0.005):
    p = np.clip(p, lo, 1 - lo)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def official_labels(y, T, teams):
    po_games = M.read_games(f"{y}p") if os.path.exists(os.path.join(sys.argv[1], f"games_{y}p.json")) else pd.DataFrame()
    po = set(po_games.team) if len(po_games) else set()
    key = {t: (M.numcol(T, "points")[t], M.numcol(T, "winsInRegulation")[t], M.numcol(T, "regulationAndOtWins")[t],
               M.numcol(T, "wins")[t], M.numcol(T, "goalDiff")[t]) for t in teams}
    divwin = {d: max([t for t in teams if M.ALIGN[t] == d], key=lambda t: key[t]) for d in set(M.ALIGN[t] for t in teams)}
    return po, divwin


def main():
    cur = nhl.start_year()
    TT, GG = {}, {}
    for y in range(nhl.FIRST, cur + 1):
        t = M.read_team(y)
        if not t.empty:
            TT[y] = t
        g = M.read_games(y)
        if not g.empty:
            GG[y] = g
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    fit_years = [y for y in done if y - 1 in TT]
    rows, checks = [], {}
    for y in [z for z in done if z >= 2021]:
        beta_y, k, tau, total, hfa = M.params_before(TT, GG, fit_years, done, y)
        T = TT[y]
        teams = sorted(T.index)
        if len(teams) != 32 or any(t not in M.ALIGN for t in teams):
            continue
        g = GG[y].copy()
        g["date"] = pd.to_datetime(g.date)
        g["gd"] = M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")
        g["pts"] = g.res.map({"W": 2, "OTL": 1, "L": 0}).fillna(0)
        # ---- as in the current code (game numbers assigned in file order, then sorted)
        g_cur = g.copy()
        g_cur["n"] = g_cur.groupby("team").cumcount() + 1
        g_cur = g_cur.sort_values(["date", "team"])
        order_ok = bool((g.groupby("team").date.apply(lambda s: s.is_monotonic_increasing)).all())
        # ---- labels
        fin = g.groupby("team").agg(pts=("pts", "sum"), wins=("res", lambda r: (r == "W").sum()), gd=("gd", "sum"))
        comp = fin.pts * 1e6 + fin.wins * 1e3 + fin.gd
        po_cur = set()
        for d in set(M.ALIGN[t] for t in teams):
            po_cur |= set(sorted([t for t in teams if M.ALIGN[t] == d], key=lambda t: -comp[t])[:3])
        for c in ("East", "West"):
            rest = [t for t in teams if M.CONF_OF[M.ALIGN[t]] == c and t not in po_cur]
            po_cur |= set(sorted(rest, key=lambda t: -comp[t])[:2])
        div_cur = {d: max([t for t in teams if M.ALIGN[t] == d], key=lambda t: comp[t]) for d in set(M.ALIGN[t] for t in teams)}
        po_off, div_off = official_labels(y, T, teams)
        # opponent result per game (to tell regulation from OT/SO wins)
        opp_res = g.set_index(["date", "team"]).res
        g["opp_otl"] = [opp_res.get((d, o)) == "OTL" for d, o in zip(g.date, g.opp)]
        prior = pd.Series(M.prior_features(y, TT).reindex(teams).fillna(0).values @ beta_y, index=teams)
        info = {"order_monotonic_per_team": order_ok,
                "playoff_label_disagreements": sorted(po_cur ^ po_off) if po_off else "no playoff file",
                "division_label_disagreements": {d: [div_cur[d], div_off[d]] for d in div_cur if div_cur[d] != div_off[d]}}
        for N in (0, 20):
            # current partition
            played = g_cur[g_cur.n <= N]
            rem = g_cur[(g_cur.n > N) & (g_cur.ha == "H")]
            # count consistency: per team, played + remaining (both sides) should equal its season total
            tot = g.groupby("team").size()
            rem_ct = pd.concat([rem.team, rem.opp]).value_counts().reindex(teams).fillna(0)
            pl_ct = played.groupby("team").size().reindex(teams).fillna(0)
            mism = int((pl_ct + rem_ct != tot.reindex(teams)).sum())
            # fixed partition by date
            if N == 0:
                cut = g.date.min()
            else:
                gp_by_date = g.sort_values("date").groupby("date").size().cumsum() / len(teams)
                cut = gp_by_date[gp_by_date >= N].index[0] + pd.Timedelta(days=1)
            played_f = g[g.date < cut]
            rem_f = g[(g.date >= cut) & (g.ha == "H")]
            rem_ct_f = pd.concat([rem_f.team, rem_f.opp]).value_counts().reindex(teams).fillna(0)
            pl_ct_f = played_f.groupby("team").size().reindex(teams).fillna(0)
            mism_f = int((pl_ct_f + rem_ct_f != tot.reindex(teams)).sum())
            info[f"N{N}"] = {"current_partition_teams_with_count_mismatch": mism, "fixed_partition_teams_with_count_mismatch": mism_f,
                             "fixed_checkpoint_date": str(cut.date()), "fixed_gp_range": [int(pl_ct_f.min()), int(pl_ct_f.max())]}

            def setup(pl, rm, real_rw):
                gp = pl.groupby("team").size().reindex(teams).fillna(0)
                cur = pl.groupby("team").gd.mean().reindex(teams).fillna(0) if len(pl) else pd.Series(0.0, index=teams)
                cur = cur - cur.mean()
                rating = (gp * cur + k * prior) / (gp + k)
                rating = rating - rating.mean()
                w = (pl.res == "W")
                rw = (w & ~pl.opp_otl) if real_rw else w
                state = pd.DataFrame({"points": pl.groupby("team").pts.sum().reindex(teams).fillna(0),
                                      "rw": pl.assign(x=rw.astype(float)).groupby("team").x.sum().reindex(teams).fillna(0),
                                      "gd": pl.groupby("team").gd.sum().reindex(teams).fillna(0)}, index=teams)
                state["row"] = pl.assign(x=w.astype(float)).groupby("team").x.sum().reindex(teams).fillna(0) if real_rw else state.rw
                return rating, state, list(zip(rm.team, rm.opp)), float(gp.mean())
            for variant, (pl, rm, real) in (("current", (played.merge(g[["date", "team", "opp_otl"]], on=["date", "team"]), rem, False)),
                                             ("fixed", (played_f, rem_f, True))):
                rating, state, games, n_avg = setup(pl, rm, real)
                for s in SEEDS:
                    sim = M.simulate(teams, state, games, rating.to_dict(), M.tau_at(tau, N if variant == "current" else n_avg), total, hfa, SIMS, seed=s)
                    for i, t in enumerate(teams):
                        rows.append(dict(season=y, N=N, variant=variant, seed=s, team=t, p_po=sim["playoffs"][i], p_div=sim["div"][i],
                                         po_cur=int(t in po_cur), div_cur=int(div_cur[M.ALIGN[t]] == t),
                                         po_off=int(t in po_off) if po_off else None, div_off=int(div_off[M.ALIGN[t]] == t)))
        checks[y] = info
        print("season", y, flush=True)
    D = pd.DataFrame(rows)
    res = {"checks": checks, "scores": {}}
    for N, x in D.groupby("N"):
        r = {}
        for v in ("current", "fixed"):
            z = x[x.variant == v]
            for lab in ("cur", "off"):
                zz = z.dropna(subset=[f"po_{lab}"])
                r[f"{v}_sim__{lab}_labels"] = {"playoffs": round(ll(zz.groupby(["season", "team"]).p_po.mean().values, zz.groupby(["season", "team"])[f"po_{lab}"].first().values), 4),
                                               "division": round(ll(zz.groupby(["season", "team"]).p_div.mean().values, zz.groupby(["season", "team"])[f"div_{lab}"].first().values, 0.003), 4),
                                               "by_seed_playoffs": [round(ll(q.p_po.values, q[f"po_{lab}"].values), 4) for _, q in zz.groupby("seed")]}
        r["max_abs_prob_change_current_vs_fixed"] = round(float((x[x.variant == "fixed"].groupby(["season", "team"]).p_po.mean()
                                                               - x[x.variant == "current"].groupby(["season", "team"]).p_po.mean()).abs().max()), 4)
        res["scores"][f"N{N}"] = r
    json.dump(res, open(sys.argv[2], "w"), indent=1, default=str)
    print(json.dumps(res["scores"], indent=1))


if __name__ == "__main__":
    main()
