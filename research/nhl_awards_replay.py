"""Point-in-time replay of NHL award chances (Hart, Vezina, Norris, Calder) and the Art Ross / Rocket Richard races.

Season-to-date snapshots every 21 days (research/nhl_award_snapshots.py, fetched in GitHub Actions) are turned into the
same tables nhl_awards.season_tables builds, the previous season comes from the published final tables, and the live
method (nhl_awards.current_chances: forward simulation + conditional logit) is rerun with weights fitted leave-one-season-out
(lambda chosen as live, inside the training seasons). Limits: aggregated snapshots carry no team, so each player's team is
the one he finished the season with (only used for team strength); rookie flags come from the final table (known before
the season). Temperatures on the logit (1 = live) are scored alongside.
Score: -log(probability given to the eventual winner), plus favourite calibration.
Usage: python research/nhl_awards_replay.py <dir with published nhl season files> [first] [last]
"""
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nhl  # noqa: E402
import nhl_awards as A  # noqa: E402

SNAP = os.path.join(ROOT, "model", "replay", "nhl_award_snapshots")
TEMPS = [0.6, 0.8, 1.0, 1.25, 1.6]
AWARDS = ["Hart", "Vezina", "Norris", "Calder"]


def snapshot_tables(snap, final):
    """(sk, gl, tm) at a checkpoint, shaped like nhl_awards.season_tables."""
    fsk, fgl, ftm = final
    team_of = {**dict(zip(fsk.name, fsk.team)), **dict(zip(fgl.name, fgl.team))}
    rook = {**dict(zip(fsk.name, fsk.rookie)), **dict(zip(fgl.name, fgl.rookie))}
    name_to_abbr = {v: k for k, v in ftm["name"].items()} if "name" in ftm else {}
    tm = pd.DataFrame(snap["team"])
    tm["team"] = tm.teamFullName.map(name_to_abbr)
    tm = tm.dropna(subset=["team"]).set_index("team")
    tm_pp = tm.pointPct.astype(float)
    sk = pd.DataFrame(snap["skater"])
    gl = pd.DataFrame(snap["goalie"])
    base_sk = pd.DataFrame({"name": sk.skaterFullName, "team": sk.skaterFullName.map(team_of), "pos": sk.positionCode, "isG": 0.0,
                            "gp": sk.gamesPlayed.astype(float), "pts": sk.points.astype(float), "goals": sk.goals.astype(float),
                            "toi": sk.timeOnIcePerGame.astype(float), "saa": 0.0, "rookie": sk.skaterFullName.map(rook).fillna(0.0)})
    lg = gl.saves.sum() / max(gl.shotsAgainst.sum(), 1)
    base_gl = pd.DataFrame({"name": gl.goalieFullName, "team": gl.goalieFullName.map(team_of), "pos": "G", "isG": 1.0,
                            "gp": gl.gamesPlayed.astype(float), "pts": 0.0, "goals": 0.0, "toi": 0.0,
                            "saa": gl.saves.astype(float) - gl.shotsAgainst.astype(float) * lg, "rookie": gl.goalieFullName.map(rook).fillna(0.0),
                            "wins": gl.wins.astype(float)})
    out = []
    for d in (base_sk, base_gl):
        d = d.dropna(subset=["team"]).reset_index(drop=True)
        d["tm_pp"] = d.team.map(tm_pp).fillna(0.5)
        d["tm_gp"] = d.team.map(tm.gamesPlayed.astype(float)).fillna(tm.gamesPlayed.max())
        d["tm_pts"] = d.team.map(tm.points.astype(float)).fillna(0.0)
        out.append(d)
    return out[0], out[1], tm


def main(first, last):
    T = {}
    for y in range(nhl.FIRST, last + 1):
        t = A.season_tables(y)
        if t:
            T[y] = t
    rows = []
    for y in range(first, last + 1):
        p = os.path.join(SNAP, f"{y}.json.gz")
        if not os.path.exists(p) or y not in T or (y - 1) not in T:
            continue
        snaps = json.load(gzip.open(p, "rt"))
        done = [z for z in T if z != y and z <= last]
        for award in ([] if os.environ.get("AW_RACES_ONLY") else AWARDS):
            if y not in A.WINNERS[award]:
                continue
            data = A.train(award, done, T)
            scores = {lam: A.loso(data, lam) for lam in A.LAMBDAS}
            lam = min(scores, key=lambda l: scores[l]["logloss"])
            beta = A.fit([d[2] for d in data], [d[3] for d in data], lam)
            win = A.norm(A.WINNERS[award][y])
            for ci, (day, snap) in enumerate(sorted(snaps.items())):
                Tc = {y: snapshot_tables(snap, T[y]), y - 1: T[y - 1]}
                frac = float(np.median(Tc[y][2].gamesPlayed.astype(float))) / A.SEASON_GAMES
                for temp in TEMPS:
                    res = A.current_chances(award, y, Tc, beta / temp)
                    pm = {}
                    for d in res:
                        pm[A.norm(d["name"])] = pm.get(A.norm(d["name"]), 0) + d["prob"]
                    pw = pm.get(win, 0.0)
                    fav = max(pm.values()) if pm else 0.0
                    rows.append(dict(season=y, award=award, ck=ci, frac=round(frac, 3), method=f"T{temp}", p_winner=pw, fav=fav,
                                     fav_won=int(bool(pm) and max(pm, key=pm.get) == win), nll=-np.log(max(pw, 0.002))))
            print(y, award, flush=True)
        # point and goal races (no model weights involved)
        for key, lab in (("pts", "ArtRoss"), ("goals", "Richard")):
            fin = T[y][0]
            winner = A.norm(fin.sort_values(key, ascending=False).iloc[0]["name"])
            for ci, (day, snap) in enumerate(sorted(snaps.items())):
                Tc = {y: snapshot_tables(snap, T[y]), y - 1: T[y - 1]}
                frac = float(np.median(Tc[y][2].gamesPlayed.astype(float))) / A.SEASON_GAMES
                res = A.leaders_race(key, y, Tc, S=2000)
                pm = {A.norm(d["name"]): d["prob"] for d in res}
                pw = pm.get(winner, 0.0)
                rows.append(dict(season=y, award=lab, ck=ci, frac=round(frac, 3), method="T1.0", p_winner=pw, fav=max(pm.values()) if pm else 0,
                                 fav_won=int(bool(pm) and max(pm, key=pm.get) == winner), nll=-np.log(max(pw, 0.002))))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    A.K_PTS = float(os.environ.get("AW_K_PTS", A.K_PTS))
    A.K_GOALS = float(os.environ.get("AW_K_GOALS", A.K_GOALS))
    A.TALENT_SHAPE = float(os.environ.get("AW_SHAPE", A.TALENT_SHAPE))
    nhl.NHL_OUT = A.nhl.NHL_OUT = sys.argv[1]
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 2011
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
    R = main(first, last)
    out = os.environ.get("AW_OUT") or os.path.join(ROOT, "model", "replay", "nhl_awards_replay.csv")
    R.to_csv(out, index=False)
    print(R.pivot_table(index="award", columns="method", values="nll").round(3).to_string())
