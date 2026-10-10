"""Model vs Polymarket on past US-sports futures (scorecard only; never feeds a projection).

At the same dates as the point-in-time back-tests, compare the model's probabilities with Polymarket's prices (normalised
to sum to 1 within each market) and score both against what happened. Also scores a 50/50 blend: if the blend beats the
market, the model carries information the market did not already have.
Usage: python research/market_benchmark.py <market-data dir>   (reads model/*.csv and the NFL per-team back-test file)
"""
import datetime as dt
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
MD = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "polymarket", "events")


def names():
    from common import NAMES as NFL
    import nba
    site = os.environ.get("SITE_DIR", os.path.join(ROOT, "site"))
    meta = os.path.join(site, "nhl", "data", "meta.json")
    if os.path.exists(meta):
        nhl = json.load(open(meta))["teams"]
    else:                                  # the daily workflow only has the published futures files
        nhl = {t["team"]: t["name"] for t in json.load(open(os.path.join(site, "nhl", "data", "futures.json")))["teams"]}
    nhl = dict(nhl, UTA="Utah Mammoth")
    return {"nfl": NFL, "nba": nba.NAMES, "nhl": nhl}


NM = names()
ALIAS = {"nhl": {"UTA": ["Utah Hockey Club", "Utah HC", "Mammoth", "Utah"]}, "nba": {"LAC": ["Clippers"], "LAL": ["Lakers"]},
         "nfl": {"LA": ["Rams"], "LAC": ["Chargers"], "NYG": ["Giants"], "NYJ": ["Jets"]}}


def team_of(sport, text):
    text = (text or "").lower()
    hits = []
    for code, full in NM[sport].items():
        cands = [full, full.split()[-1]] + ALIAS.get(sport, {}).get(code, [])
        if full.split()[-1] in ("Sox", "Jackets", "Wings", "Leafs", "Knights", "Blazers"):
            cands.append(" ".join(full.split()[-2:]))
        for c in cands:
            if c.lower() in text:
                hits.append((len(c), code))
    return max(hits)[1] if hits else None


def market(slug, sport):
    """team -> list of (t, p) for the event's YES prices."""
    out = {}
    for f in glob.glob(os.path.join(MD, slug, "*.json")):
        if f.endswith("event.json"):
            continue
        h = json.load(open(f))
        t = team_of(sport, (h.get("team") or "") + " " + (h.get("question") or ""))
        if t and h.get("history"):
            out[t] = sorted((x["t"], x["p"]) for x in h["history"])
    return out


def price_at(series, when):
    ts = dt.datetime.combine(when, dt.time(23, 59), tzinfo=dt.timezone.utc).timestamp()
    if not series or series[0][0] > ts + 3 * 86400:
        return None
    best = None
    for t, p in series:
        if t <= ts:
            best = p
    return best if best is not None else series[0][1]


def score(rows):
    """rows: list of dict(group, model, market, won). Multi-class log-loss of the winner within each group."""
    out = {"model": [], "market": [], "blend": []}
    for _, G in pd.DataFrame(rows).groupby("group"):
        if G.won.sum() != 1 or G.market.isna().mean() > 0.3:
            continue
        mk = G.market.fillna(0.002).clip(lower=0.002).values
        mo = G.model.clip(lower=0.002).values
        mk, mo = mk / mk.sum(), mo / mo.sum()
        bl = np.sqrt(mk * mo)
        bl /= bl.sum()
        w = G.won.values == 1
        for k, v in (("model", mo), ("market", mk), ("blend", bl)):
            out[k].append(float(-np.log(v[w][0])))
    return {k: (round(float(np.mean(v)), 3) if v else None) for k, v in out.items()} | {"events": len(out["model"])}


def nfl():
    from common import games, FIX
    g = games()
    T = pd.read_csv(os.environ.get("NFL_TEAMS_CSV", os.path.join(ROOT, "model", "nfl_bt_teams.csv")))
    T = T[T.model == "v4 (live)"]
    div_of = {}
    import simulate as SIM
    from common import TEAMS
    for d, ts in enumerate(SIM.DIV_TEAMS):
        for t in ts:
            div_of[TEAMS[t]] = d
    conf_of = {TEAMS[t]: c for c, ds in SIM.CONF_DIVS.items() for d in ds for t in SIM.DIV_TEAMS[d]}
    ev = {2024: {"sb": ["superbowl-champion-2025"], "conf": ["afc-champion", "nfc-champion"],
                 "div": ["afc-east-champion", "afc-north-winner", "afc-south", "afc-west-winner", "nfc-east-winner", "nfc-north-winner-1",
                         "nfc-south-winner-1", "nfc-west-winner"], "playoff": ["which-nfl-teams-will-make-the-playoffs"]},
          2025: {"sb": ["super-bowl-champion-2026-731"], "conf": ["afc-champion-1", "nfc-champion-1"],
                 "div": [f"{c}-winner-11" if c in ("afc-east", "nfc-north", "nfc-south") else f"{c}-winner-1" for c in
                         ("afc-east", "afc-north", "afc-south", "afc-west", "nfc-east", "nfc-north", "nfc-south", "nfc-west")],
                 "playoff": ["which-nfl-teams-will-make-the-playoffs-167"]}}
    res = {}
    for k in ("sb", "conf", "div", "playoff"):
        for wk in (0, 4, 9, 13):
            rows, brier = [], []
            for y in (2024, 2025):
                reg = g[(g.season == y) & (g.game_type == "REG")]
                when = (pd.to_datetime(reg.gameday.min()) - pd.Timedelta(days=1)).date() if wk == 0 else \
                    (pd.to_datetime(reg[reg.week == wk].gameday.max()) + pd.Timedelta(days=1)).date()
                M = {}
                for slug in ev[y][k]:
                    M.update(market(slug, "nfl"))
                X = T[(T.season == y) & (T.week == wk)]
                for r in X.itertuples():
                    p = price_at(M.get(r.team), when)
                    grp = {"sb": f"{y}", "conf": f"{y}-{conf_of[r.team]}", "div": f"{y}-{div_of[r.team]}", "playoff": None}[k]
                    if k == "playoff":
                        if p is not None:
                            brier.append((getattr(r, k), p, getattr(r, "y_" + k)))
                    else:
                        rows.append(dict(group=grp, model=getattr(r, k), market=p, won=getattr(r, "y_" + k)))
            if k == "playoff":
                if brier:
                    a = np.array(brier)
                    res[f"playoff wk{wk}"] = {"model": round(float(((a[:, 0] - a[:, 2]) ** 2).mean()), 4), "market": round(float(((a[:, 1] - a[:, 2]) ** 2).mean()), 4),
                                              "blend": round(float((((a[:, 0] + a[:, 1]) / 2 - a[:, 2]) ** 2).mean()), 4), "teams": len(a), "metric": "brier"}
            else:
                res[f"{k} wk{wk}"] = score(rows)
    return res


def nba():
    import nba as N
    D = pd.read_csv(os.path.join(ROOT, "model", "nba_title_backtest.csv"))
    ev = {2025: {"title": ["nba-champion-2024-2025"], "conf": ["nba-eastern-conference-champion", "nba-western-conference-champion"]},
          2026: {"title": ["2026-nba-champion"], "conf": ["nba-playoffs-eastern-conference-champion", "nba-playoffs-western-conference-champion"]}}
    res = {}
    for k in ("title", "conf"):
        for c in sorted(D.check.unique()):
            rows = []
            for y in (2025, 2026):
                X = D[(D.season == y) & (D.check == c)]
                when = pd.to_datetime(X.date.iloc[0]).date()
                M = {}
                for slug in ev[y][k]:
                    M.update(market(slug, "nba"))
                for r in X.itertuples():
                    grp = f"{y}" if k == "title" else f"{y}-{'E' if r.team in N.EAST else 'W'}"
                    rows.append(dict(group=grp, model=getattr(r, "p_" + k), market=price_at(M.get(r.team), when), won=getattr(r, "y_" + k)))
            res[f"{k} {int(c * 100)}%"] = score(rows)
    return res


def nhl():
    D = pd.read_csv(os.path.join(ROOT, "model", "nhl_backtest_rows.csv"))
    meta = json.load(open(os.path.join(ROOT, "site", "nhl", "data", "meta.json")))
    conf = {t: meta["conf"][d] for d, ts in meta["divisions"].items() for t in ts}
    ev = {2024: {"cup": ["stanley-cup-winner"]}, 2025: {"cup": ["2026-nhl-stanley-cup-champion"],
                                                       "conf": ["nhl-eastern-conference-champion-198", "nhl-western-conference-champion-865"]}}
    res = {}
    for y in ev:
        p = json.load(open(os.path.join(ROOT, "site", "nhl", "data", f"games_{y}p.json")))
        last = p["rows"][-1]
        champ = last[1] if last[4] == "W" else last[2]
        fin = {last[1], last[2]}
        g0 = json.load(open(os.path.join(ROOT, "site", "nhl", "data", f"games_{y}.json")))
        start = min(r[0] for r in g0["rows"])
        for N_ in (0, 20):
            X = D[(D.season == y) & (D.N == N_)]
            when = (pd.to_datetime(start) - pd.Timedelta(days=1)).date() if N_ == 0 else pd.to_datetime(X.date.iloc[0]).date()
            for k, col, won in (("cup", "p_cup", lambda t: t == champ), ("conf", "p_final", lambda t: t in fin)):
                if k not in ev[y]:
                    continue
                M = {}
                for slug in ev[y][k]:
                    M.update(market(slug, "nhl"))
                rows = [dict(group=f"{y}" if k == "cup" else f"{y}-{conf.get(r.team)}", model=getattr(r, col), market=price_at(M.get(r.team), when),
                             won=int(won(r.team))) for r in X.itertuples()]
                res[f"{k} {y} N{N_}"] = score(rows)
    return res


if __name__ == "__main__":
    out = {"nfl": nfl(), "nba": nba(), "nhl": nhl(), "note": "mean -log(probability given to the eventual winner), lower is better; "
           "playoff rows use Brier score per team; blend = geometric mean of model and market"}
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(ROOT, "model", "market_benchmark.json"), "w"), indent=1)
