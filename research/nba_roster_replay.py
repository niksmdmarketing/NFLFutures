"""Preseason test of the NBA roster adjustment (research).

For each season Y: the live preseason rating (_fit_ratings on games before Y) plus a roster adjustment
c x (new strength - old strength), where strength = sum(impact x minutes) / (82 x 48) over a 12-man rotation, impact and
minutes from season Y-1 box scores (nba._player_values). 'Old' team = the player's last Y-1 team; 'new' team = the team he
first played for in season Y (known by opening night, apart from players who miss the whole season). Option RETURN uses
season Y-2 values for players with under 500 minutes in Y-1 (back from a long injury). Scored against the season's actual
regular-season net rating per 100 possessions and wins.
Usage: python research/nba_roster_replay.py [first] [last]
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402

D = N.NBA_DATA
MULTI = float(os.environ.get("RR_MULTI", "0"))
MINAVG = os.environ.get("RR_MINAVG") == "1"   # injury-shortened season: minutes = max(last, two-season average)
GAMES = float(os.environ.get("RR_GAMES", "0"))   # checkpoint: games per team played (0 = preseason); target = rest of season
GW = float(os.environ.get("RR_GW", "0.24"))   # weight on game score per 36 above average (live 0.24)
PW = float(os.environ.get("RR_PW", "0.045"))  # weight on plus-minus per 36 (live 0.045)
_orig_values = N._player_values


def _values(players):
    a = _orig_values(players)
    if GW == 0.24 and PW == 0.045:
        return a
    league = np.average(a.gmsc36, weights=a.minutes)
    rel = np.minimum(1, a.minutes / 1200)
    a["impact"] = (((a.gmsc36 - league) * GW + a.pm36 * PW) * rel).clip(-4, 6)
    return a


N._player_values = _values   # weight of last season vs the season before in player impact (0 = last season only)


def load(name):
    p = os.path.join(D, name)
    return pd.read_csv(p, low_memory=False) if os.path.exists(p) else pd.DataFrame()


def strength(assign, vals, return_fix, vals2):
    """assign: athlete_id -> team. Returns team -> strength (points per 48 relative to average)."""
    v = vals.sort_values("minutes", ascending=False).drop_duplicates("athlete_id").set_index("athlete_id")
    v2 = vals2.sort_values("minutes", ascending=False).drop_duplicates("athlete_id").set_index("athlete_id") if len(vals2) else None
    rows = []
    for a, t in assign.items():
        m, im = float(v.minutes.get(a, 0.0)), float(v.impact.get(a, 0.0))
        m2, im2 = (float(v2.minutes.get(a, 0.0)), float(v2.impact.get(a, 0.0))) if v2 is not None else (0.0, 0.0)
        if return_fix and m < 500 and m2 >= 1000:
            m, im = m2, im2
        elif MULTI and m + m2 > 0:
            im = (MULTI * m * im + m2 * im2) / (MULTI * m + m2)
            if MINAVG and m2 >= 1000:
                m = max(m, (m + m2) / 2)
        rows.append((t, a, min(m, 2600), im))
    r = pd.DataFrame(rows, columns=["team", "a", "minutes", "impact"])
    r = r.sort_values(["team", "minutes"], ascending=[True, False]).groupby("team").head(12)

    def one(g):
        mins = g.minutes.to_numpy(float)
        if mins.sum() > 82 * 240:
            mins = mins * (82 * 240) / mins.sum()
        return float(np.sum(g.impact.to_numpy(float) * mins) / (82 * 48))
    return r.groupby("team").apply(one, include_groups=False)


def main(first, last):
    boxes = pd.concat([load(f"team_box_{y}.csv") for y in range(first - 5, last + 1)], ignore_index=True)
    pb = {y: load(f"player_box_{y}.csv") for y in range(first - 2, last + 1)}
    out = []
    for y in range(first, last + 1):
        if not len(pb.get(y, [])) or not len(pb.get(y - 1, [])):
            continue
        seas = pd.to_numeric(boxes.season, errors="coerce")
        pre = boxes[seas < y]
        cut = None
        if GAMES:
            cy = N._regular_boxes(boxes[seas == y]).sort_values("game_date")
            gd = sorted(cy.game_date.astype(str).str[:10].unique())
            cnt = cy.assign(d=cy.game_date.astype(str).str[:10]).groupby("d").size().cumsum() / 30
            cut = next((d for d in gd if cnt[d] >= GAMES), gd[-1])
            cur_part = boxes[(seas == y) & (boxes.game_date.astype(str).str[:10] <= cut)]
            pre = pd.concat([pre, cur_part], ignore_index=True)
        ratings, _ = N._fit_ratings(pre, y)
        base = ratings.set_index("team").raw_net if "raw_net" in ratings else ratings.set_index("team").rating
        vals = N._player_values(pb[y - 1])
        vals2 = N._player_values(pb[y - 2]) if len(pb.get(y - 2, [])) else pd.DataFrame()
        p1 = pb[y - 1][(pd.to_numeric(pb[y - 1].season_type, errors="coerce") == 2) & (pd.to_numeric(pb[y - 1].minutes, errors="coerce") > 0)]
        p1 = p1.assign(athlete_id=p1.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)).sort_values("game_date")
        old = p1.groupby("athlete_id").team_abbreviation.last()
        p0 = pb[y][(pd.to_numeric(pb[y].season_type, errors="coerce") == 2) & (pd.to_numeric(pb[y].minutes, errors="coerce") > 0)]
        p0 = p0.assign(athlete_id=p0.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)).sort_values("game_date")
        new = p0.groupby("athlete_id").team_abbreviation.first()
        # actual season net rating per 100 possessions and wins
        cur = N._regular_boxes(boxes[pd.to_numeric(boxes.season, errors="coerce") == y])
        if cut is not None:
            cur = cur[cur.game_date.astype(str).str[:10] > cut]
        if not len(cur):
            continue
        cur = cur.copy()
        cur["opp_ortg"] = cur.groupby("game_id").ortg.transform("sum") - cur.ortg
        cur["netg"] = cur.ortg - cur.opp_ortg
        net = cur.groupby("team_abbreviation").netg.mean()
        win = (cur.team_score > cur.groupby("game_id").team_score.transform("sum") - cur.team_score).astype(int)
        wins = win.groupby(cur.team_abbreviation).sum()
        for ret in (False, True):
            so = strength(old.to_dict(), vals, ret, vals2)
            sn = strength(new.to_dict(), vals, ret, vals2)
            diff = (sn.reindex(N.TEAMS).fillna(0) - so.reindex(N.TEAMS).fillna(0))
            for c in (0.0, 0.55, 1.0, 1.5, 2.0):
                adj = (c * diff)
                adj = adj - adj.mean()
                pred = base.reindex(N.TEAMS).fillna(0) + adj
                pred = pred - pred.mean()
                for t in N.TEAMS:
                    if t in net.index:
                        out.append(dict(season=y, team=t, ret=ret, c=c, pred=pred[t], net=net[t], wins=wins.get(t, np.nan), adj=adj[t]))
        print(y, flush=True)
    return pd.DataFrame(out)


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2014
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    R = main(first, last)
    R.to_csv(os.environ.get("RR_OUT") or os.path.join(ROOT, "model", "replay", "nba_roster_replay.csv"), index=False)
    R["err"] = (R.pred - R.net).abs()
    print(R.groupby(["ret", "c"]).err.mean().unstack().round(3).to_string())
    print(R.groupby(["ret", "c"]).apply(lambda g: np.corrcoef(g.pred, g.net)[0, 1], include_groups=False).unstack().round(3).to_string())
