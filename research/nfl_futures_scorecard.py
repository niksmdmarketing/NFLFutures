"""NFL in-season futures: frozen v4 against Polymarket, plus a flat-$100 paper-bet record (research/NFL_FUTURES_PAPER_BET_RULE.md).
Proxy profit test against an exchange price, not bookmaker profit. Prices never feed the model.
Usage: python research/nfl_futures_scorecard.py <market-data dir with polymarket/events> <shiv-archive dir with records>
"""
import datetime as dt
import glob
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import NAMES, DIVS, TEAMS, games  # noqa: E402

CHECKS = (4, 9, 13)
EV_THRESHOLD, STAKE, SPREAD_ALLOWANCE = 0.10, 100.0, 0.01
ALIAS = {"LA": ["Rams"], "LAC": ["Chargers"], "NYG": ["Giants"], "NYJ": ["Jets"]}
DIV_OF = {t: d for d, ts in DIVS.items() for t in ts}
BACKFILL = {2024: {"div": ["afc-east-champion", "afc-north-winner", "afc-south", "afc-west-winner", "nfc-east-winner", "nfc-north-winner-1",
                           "nfc-south-winner-1", "nfc-west-winner"], "playoff": ["which-nfl-teams-will-make-the-playoffs"]},
            2025: {"div": [f"{c}-winner-11" if c in ("afc-east", "nfc-north", "nfc-south") else f"{c}-winner-1" for c in
                           ("afc-east", "afc-north", "afc-south", "afc-west", "nfc-east", "nfc-north", "nfc-south", "nfc-west")],
                   "playoff": ["which-nfl-teams-will-make-the-playoffs-167"]}}


def team_of(text):
    text = (text or "").lower(); hits = []
    for code, full in NAMES.items():
        for c in [full, full.split()[-1]] + ALIAS.get(code, []):
            if c.lower() in text:
                hits.append((len(c), code))
    return max(hits)[1] if hits else None


def history(md, slug):
    out = {}
    for f in glob.glob(os.path.join(md, "polymarket", "events", slug, "*.json")):
        if f.endswith("event.json"):
            continue
        h = json.load(open(f))
        t = team_of((h.get("team") or "") + " " + (h.get("question") or ""))
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


def fee(p, rate=0.03, exponent=1.0):
    return rate * (p * (1 - p)) ** exponent


def checkpoint_dates(g, season):
    reg = g[(g.season == season) & (g.game_type == "REG")]
    return {w: (pd.to_datetime(reg[reg.week == w].gameday.max()) + pd.Timedelta(days=1)).date() for w in CHECKS if (reg.week == w).any()}


def outcomes(g, season):
    """Final division winners and playoff teams, only once every regular-season game has a result."""
    reg = g[(g.season == season) & (g.game_type == "REG")]
    if not len(reg) or reg.result.isna().any():
        return None
    import nfl_backtest as B
    out = B.outcomes(g, season)
    return {t: dict(div=float(out["div"][i]), playoff=float(out["playoff"][i])) for i, t in enumerate(TEAMS)}


def backfill_rows(md, g):
    T = pd.read_csv(os.path.join(ROOT, "model", "nfl_bt_teams.csv"))
    T = T[T.model == "v4 (live)"]
    rows = []
    for season, ev in BACKFILL.items():
        dates = checkpoint_dates(g, season)
        for market, slugs in ev.items():
            M = {}
            for s in slugs:
                M.update(history(md, s))
            for w, when in dates.items():
                for r in T[(T.season == season) & (T.week == w)].itertuples():
                    p = price_at(M.get(r.team), when)
                    rows.append(dict(mdl="v4", season=season, week=w, market=market, team=r.team, source="backfill (daily price + 1c + fee, approximate)",
                                     snapshot=str(when), model=float(getattr(r, market)), price=p,
                                     cost=None if p is None or p <= 0 else p + SPREAD_ALLOWANCE + fee(p + SPREAD_ALLOWANCE),
                                     won=float(getattr(r, "y_" + market))))
    return rows


RETRO_2026 = {"div": [f"pro-football-{c}-champion" for c in ("afc-east", "afc-north", "afc-south", "afc-west",
                                                             "nfc-east", "nfc-north", "nfc-south", "nfc-west")],
              "playoff": ["nfl-team-to-make-postseason"]}


def retro_rows(md, g, season=2026, mdl="v4"):
    """Retrospective model at the 2026 week-4 checkpoint (rule amendments of 26 and 27 Oct 2026); daily prices as in the backfill."""
    path = os.path.join(ROOT, "research", "nfl_futures_2026_w4_retrospective.csv" if mdl == "v4" else "nfl_futures_2026_w4_retrospective_v5.csv")
    if not os.path.exists(path):
        return []
    T = pd.read_csv(path)
    res = outcomes(g, season)
    when = checkpoint_dates(g, season)[4]
    rows = []
    for market, slugs in RETRO_2026.items():
        M = {}
        for s_ in slugs:
            M.update(history(md, s_))
        for r in T.itertuples():
            p = price_at(M.get(r.team), when)
            rows.append(dict(mdl=mdl, season=season, week=4, market=market, team=r.team, source="2026 retrospective (daily price + 1c + fee, approximate)",
                             snapshot=str(when), model=float(getattr(r, market)), price=p,
                             cost=None if p is None or p <= 0 else p + SPREAD_ALLOWANCE + fee(p + SPREAD_ALLOWANCE),
                             won=None if res is None else res[r.team][market]))
    return rows


def live_rows(shiv, g, season=2026):
    recs = []
    for f in sorted(glob.glob(os.path.join(shiv, "records", "*", "*.json.gz"))):
        d = json.load(gzip.open(f))
        recs.append((pd.Timestamp(d["taken_utc"]), d))
    dates = checkpoint_dates(g, season)
    res = outcomes(g, season)
    rows, missing = [], []
    for w, when in dates.items():
        start = pd.Timestamp(dt.datetime.combine(when, dt.time(12, 0)), tz="UTC")
        if recs and recs[0][0] > start:
            missing.append(dict(week=w, reason=f"checkpoint {start.isoformat()} is before the first archive record"))
            continue
        after = [d for t, d in recs if t >= start]
        if not after:
            continue                                           # checkpoint not reached yet
        d = after[0]
        for m in d["markets"]:
            if m.get("sport") != "nfl" or m["group"] not in ("Division", "Make playoffs"):
                continue
            market = "div" if m["group"] == "Division" else "playoff"
            fs = m.get("fee") or {}
            for r in m["rows"]:
                ask = r.get("ask")
                cost = None if not ask or ask <= 0 else ask + fee(ask, fs.get("rate", .03), fs.get("exponent", 1.))
                rows.append(dict(mdl="v4", season=season, week=w, market=market, team=r["team"], source="live (ask + taker fee)",
                                 snapshot=d["taken_utc"], checkpoint_utc=start.isoformat(), model=float(r["model"]), price=r.get("mid"), ask=ask, cost=cost,
                                 won=None if res is None else res[r["team"]][market]))
    return rows, missing


def core_backfill_rows(md, g):
    """v5-core and v4-core backfill 2024-25 from research/nfl_v5_promotion_rows.csv.gz (seed sets averaged); amendment of 27 Oct 2026."""
    path = os.path.join(ROOT, "research", "nfl_v5_promotion_rows.csv.gz")
    if not os.path.exists(path):
        return []
    T = pd.read_csv(path)
    T = T[T.season.isin(list(BACKFILL)) & T.week.isin(list(CHECKS))].groupby(["season", "week", "arm", "team"], as_index=False).mean(numeric_only=True)
    rows = []
    for season, ev in BACKFILL.items():
        dates = checkpoint_dates(g, season)
        for market, slugs in ev.items():
            M = {}
            for s_ in slugs:
                M.update(history(md, s_))
            for w, when in dates.items():
                for r in T[(T.season == season) & (T.week == w)].itertuples():
                    p = price_at(M.get(r.team), when)
                    rows.append(dict(mdl=f"{r.arm}-core", season=season, week=w, market=market, team=r.team,
                                     source="backfill (daily price + 1c + fee, approximate)", snapshot=str(when), model=float(getattr(r, "p_" + market)),
                                     price=p, cost=None if p is None or p <= 0 else p + SPREAD_ALLOWANCE + fee(p + SPREAD_ALLOWANCE),
                                     won=float(getattr(r, "y_" + market))))
    return rows


def live_v5_rows(v4_live, fa):
    """v5 live rows: same team, market, checkpoint and price as each v4 live row; v5 probability from the first forecast-archive
    season file generated at or after the checkpoint time."""
    if not v4_live or not fa:
        return []
    files = []
    for f in sorted(glob.glob(os.path.join(fa, "2026", "*.json.gz"))):
        d = json.load(gzip.open(f))
        if d.get("challenger_v5"):
            files.append((pd.Timestamp(d["generated_utc"]), d))
    out = []
    for r in v4_live:
        start = pd.Timestamp(r["checkpoint_utc"])
        after = [d for t, d in files if t >= start]
        if not after:
            continue
        v = after[0]["challenger_v5"]["teams"].get(r["team"])
        if v is None:
            continue
        out.append({**r, "mdl": "v5", "model": float(v["p_" + r["market"]]), "v5_file_utc": after[0]["generated_utc"]})
    return out


def add_bets(df):
    df = df.copy()
    df["edge"] = df.model / df.cost - 1
    df["bet"] = df.cost.notna() & (df.edge >= EV_THRESHOLD)
    df["profit"] = np.where(~df.bet | df.won.isna(), np.nan, np.where(df.won == 1, STAKE / df.cost - STAKE, -STAKE))
    df["expected_profit"] = np.where(df.bet, STAKE * df.model / df.cost - STAKE, np.nan)
    return df


def accuracy(df):
    out = {}
    for (mdl, season, w, market), z in df[df.won.notna() & df.price.notna()].groupby(["mdl", "season", "week", "market"]):
        # retrospective and live rows of the same season/week are never mixed: live has no week 4 in 2026
        if market == "div":
            ll_m, ll_k = [], []
            for _, G in z.assign(division=z.team.map(DIV_OF)).groupby("division"):
                if len(G) != 4 or G.won.sum() != 1:
                    continue
                mo = G.model.clip(lower=.002).to_numpy(); mk = G.price.clip(lower=.002).to_numpy()
                mo, mk = mo / mo.sum(), mk / mk.sum(); win = G.won.to_numpy() == 1
                ll_m.append(-np.log(mo[win][0])); ll_k.append(-np.log(mk[win][0]))
            out[f"{mdl} {season} div w{w}"] = dict(metric="log loss of winner", model=float(np.mean(ll_m)) if ll_m else None,
                                             market=float(np.mean(ll_k)) if ll_k else None, divisions=len(ll_m))
        else:
            out[f"{mdl} {season} playoff w{w}"] = dict(metric="brier", model=float(((z.model - z.won) ** 2).mean()),
                                                 market=float(((z.price - z.won) ** 2).mean()), teams=len(z))
    return out


def record(df):
    b = df[df.bet]
    def summ(z):
        s = z[z.profit.notna()]
        return dict(bets=int(len(z)), settled=int(len(s)), pending=int(z.profit.isna().sum()), staked=float(STAKE * len(s)),
                    profit=float(s.profit.sum()), return_on_stake=float(s.profit.sum() / (STAKE * len(s))) if len(s) else None,
                    expected_profit_model=float(z.expected_profit.sum()), wins=int((s.won == 1).sum()))
    out = {}
    for mdl, bm in b.groupby("mdl"):
        o = {"all backfill and retrospective": summ(bm[bm.record != "2026 live"])}
        for rec, z in bm.groupby("record"):
            o[rec] = summ(z)
        for (season, market), z in bm.groupby(["season", "market"]):
            o[f"{season} {market}"] = summ(z)
        for (season, w), z in bm.groupby(["season", "week"]):
            o[f"{season} w{w}"] = summ(z)
        out[mdl] = o
    return out


def main():
    md, shiv = sys.argv[1], sys.argv[2]
    fa = sys.argv[3] if len(sys.argv) > 3 else None          # forecast-archive checkout (for live v5)
    g = games()
    live, missing = live_rows(shiv, g)
    rows = backfill_rows(md, g) + retro_rows(md, g) + live + core_backfill_rows(md, g) + retro_rows(md, g, mdl="v5") + live_v5_rows(live, fa)
    df = add_bets(pd.DataFrame(rows))
    df["record"] = np.where(df.source.str.startswith("live"), "2026 live", np.where(df.source.str.startswith("2026 retro"), "2026 retrospective", "backfill 2024-25"))
    df.to_csv(os.path.join(ROOT, "research", "nfl_futures_paper_bets.csv"), index=False)
    out = dict(rule="research/NFL_FUTURES_PAPER_BET_RULE.md", updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
               note="Proxy test against Polymarket executable prices; not bookmaker profit. Backfill seasons were used in earlier benchmark work.",
               missing_checkpoints_2026=missing, accuracy=accuracy(df), paper_bets=record(df))
    open(os.path.join(ROOT, "research", "nfl_futures_scorecard.json"), "w").write(json.dumps(out, indent=2))
    print(json.dumps(out["paper_bets"], indent=2)); print(json.dumps(out["accuracy"], indent=1)); print(missing)


if __name__ == "__main__":
    main()
