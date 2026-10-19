"""NBA DARKO test (rule: research/NBA_DARKO_RULE.md). Run on the user's computer or after staging the private DARKO archive:
  DARKO_ARCHIVE=<dir with darko_dpm_YYYY-MM-DD.csv> FORECAST_ARCHIVE=<forecast-archive checkout> python research/nba_darko_test.py [--mechanics]
--mechanics: plumbing check only (ignores the snapshot-date rule, uses 0.5 as 'our' probability, 2025-26 results). Its numbers mean nothing."""
import csv
import glob
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import live_check as L  # noqa: E402

HFA, SD, K = 2.3, 12.0, 1.0
TEAM_CODE = {"Atlanta Hawks": "ATL", "Brooklyn Nets": "BKN", "Boston Celtics": "BOS", "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
             "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET", "Golden State Warriors": "GS",
             "Houston Rockets": "HOU", "Indiana Pacers": "IND", "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
             "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO",
             "New York Knicks": "NY", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
             "Portland Trail Blazers": "POR", "San Antonio Spurs": "SA", "Sacramento Kings": "SAC", "Toronto Raptors": "TOR", "Utah Jazz": "UTAH",
             "Washington Wizards": "WSH"}
phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
lg = lambda p: math.log(min(max(p, 1e-4), 1 - 1e-4) / (1 - min(max(p, 1e-4), 1 - 1e-4)))
sg = lambda z: 1 / (1 + math.exp(-z))


def strengths(path):
    S, asof = {}, None
    for r in csv.DictReader(open(path, encoding="utf-8")):
        name = r["team_name"]
        if not name or name not in TEAM_CODE:
            if name:
                raise SystemExit(f"unmatched DARKO team name: {name}")
            continue
        try:
            S[TEAM_CODE[name]] = S.get(TEAM_CODE[name], 0.0) + float(r["x_minutes"]) / 48 * float(r["dpm"])
        except (ValueError, KeyError):
            continue
        asof = r.get("as_of_utc") or asof
    return S, asof


def snapshots(d):
    out = []
    for p in sorted(glob.glob(os.path.join(d, "darko_dpm_*.csv"))):
        S, asof = strengths(p)
        if asof and len(S) == 30:
            out.append((asof[:10], S))
    return out


def ours(fa, season):
    """{(day, home, away): our pre-game probability} from the forecast archive, latest snapshot strictly before the game date."""
    raw = L._snapshots(os.path.join(fa, "nba", str(season)))
    pred = {}
    for x in raw:
        d0 = x["generated_utc"][:10]
        for day, h, a, p in x.get("games") or []:
            if d0 < day:
                pred[(day, h, a)] = p / 1000
    return pred


def main(mech=False):
    d, fa = os.environ["DARKO_ARCHIVE"], os.environ["FORECAST_ARCHIVE"]
    snaps = snapshots(d)
    season = 2026 if mech else 2027
    res = L._results("nba", season) if not mech else L._results("nba", 2026)
    pred = {k: 0.5 for k in res} if mech else ours(fa, season)
    rows = []
    for (day, h, a), y in sorted(res.items()):
        if (day, h, a) not in pred:
            continue
        ok = [s for s in snaps if (True if mech else s[0] < day)]
        if not ok:
            continue
        S = ok[-1][1]
        pD = phi(((S[h] - S[a]) * K + HFA) / SD)
        pO = pred[(day, h, a)]
        rows.append((day, h, a, y, pO, pD, sg(0.5 * lg(pO) + 0.5 * lg(pD))))
    if not rows:
        print("no games with both predictions yet"); return
    # games per team (regular-season games completed)
    gp = {}
    for day, h, a, *_ in rows:
        gp[h] = gp.get(h, 0) + 1; gp[a] = gp.get(a, 0) + 1
    ll = lambda p, y: -(y * math.log(min(max(p, 1e-4), 1 - 1e-4)) + (1 - y) * math.log(1 - min(max(p, 1e-4), 1 - 1e-4)))
    Y = np.array([r[3] for r in rows], float)
    P = {k: np.array([r[i] for r in rows]) for k, i in (("ours", 4), ("darko", 5), ("blend", 6))}
    L_ = {k: np.array([ll(p, y) for p, y in zip(v, Y)]) for k, v in P.items()}
    days = np.array([r[0] for r in rows]); ud = sorted(set(days))
    rng = np.random.default_rng(7)
    diff = L_["ours"] - L_["blend"]
    bs = []
    for _ in range(2000):
        pick = rng.choice(ud, len(ud))
        m = np.concatenate([diff[days == q] for q in pick])
        bs.append(m.mean())
    half = len(rows) // 2
    X = np.array([lg(p) for p in P["blend"]])
    b = 1.0
    for _ in range(30):
        mu = 1 / (1 + np.exp(-b * X)); b += float(np.sum((Y - mu) * X) / max(np.sum(mu * (1 - mu) * X * X), 1e-9))
    rep = {"games": len(rows), "min_games_per_team": min(gp.values()) if len(gp) == 30 else None,
           **{f"logloss_{k}": round(float(v.mean()), 4) for k, v in L_.items()},
           "gain_blend_vs_ours": round(float(diff.mean()), 4), "gain_ci90": [round(float(np.percentile(bs, 5)), 4), round(float(np.percentile(bs, 95)), 4)],
           "gain_first_half": round(float(diff[:half].mean()), 4), "gain_second_half": round(float(diff[half:].mean()), 4),
           "blend_calibration_slope": round(b, 3), "darko_minus_ours": round(float(L_["darko"].mean() - L_["ours"].mean()), 4),
           "mechanics_only": mech}
    print(json.dumps(rep, indent=1))
    if not mech:
        g1 = rep["gain_blend_vs_ours"] > 0 and rep["gain_ci90"][0] > 0
        g2 = rep["gain_first_half"] > 0 and rep["gain_second_half"] > 0
        g3 = 0.8 <= rep["blend_calibration_slope"] <= 1.2
        g4 = rep["darko_minus_ours"] <= 0.010
        print("GATES", dict(G1=g1, G2=g2, G3=g3, G4=g4), "(valid only at the 20- or 41-games-per-team checkpoint)")


if __name__ == "__main__":
    main("--mechanics" in sys.argv)
