"""News-based QB absence futures replay (research/NFL_QB_NEWS_RULE.md). Research only; nothing deployed.
Usage: python research/nfl_qb_news_test.py               (full run)
       QB_NEWS_IDENTITY=1 python research/nfl_qb_news_test.py  (none arm only + case audit; no gains)
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nfl_backtest as B  # noqa: E402
import nfl_engine as E  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import DATA, FIX, TEAMS, games, load_pbp, scrimmage  # noqa: E402
from nfl_futures_diagnosis import WF, V4, V5, eng_weights  # noqa: E402
from nfl_v5_promotion_test import bll  # noqa: E402
from nfl_qb_oracle_test import main_qb  # noqa: E402

SEASONS = range(2018, 2026)
CHECKS = (4, 9, 13)
N = 5000
SEEDS = {"A": lambda y, w: 1000 * y + w, "B": lambda y, w: 7000 * y + w}
MK = ("div", "playoff", "seed1", "conf", "sb")
PRIMARY = [(m, w) for m in ("div", "playoff") for w in CHECKS]
LAMBDAS = (0.5, 1.0)
OUT = os.path.join(ROOT, "research")
QN = os.path.join(OUT, "qb_news")
IDENTITY = os.environ.get("QB_NEWS_IDENTITY") == "1"
EXPLICIT = {"S", "W", "M", "G", "UNTILWEEK", "IR", "PUP", "C"}
# Season-specific list minimums (games); filled from GPT's table before the run (see the rule). None = no return path -> season.
IR_MIN = json.load(open(os.path.join(QN, "list_minimums.json"))) if os.path.exists(os.path.join(QN, "list_minimums.json")) else {}
LAB = pd.read_csv(os.path.join(OUT, "nfl_qb_starter_labels.csv"))


def load_cases():
    d = pd.read_csv(os.path.join(QN, "gpt_qb_reports_2018_2025.csv"), encoding="utf-8-sig")
    R = pd.read_csv(os.path.join(QN, "qb_reports_coded.csv"))
    pl = pd.read_csv(os.path.join(DATA, "players.csv"), usecols=["gsis_id", "display_name", "position"], low_memory=False)
    qbname = pl[pl.position == "QB"].dropna(subset=["gsis_id"]).copy()
    norm = lambda x: re.sub(r"[^a-z]", "", str(x).lower())
    qbname["key"] = qbname.display_name.map(norm)
    cases = []
    for i, r in d.iterrows():
        who = [x.strip() for x in str(r.iloc[0]).split(";")]
        season, team = int(who[0]), FIX.get(who[1], who[1])
        starter = re.sub(r"^starter:\s*", "", who[2])
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(r.iloc[1]))
        start = pd.Timestamp(m.group(1)) if m else None
        lab = LAB[(LAB.season.isin([season, season - 1])) & (LAB.team == team)]
        ids = set(lab.chosen.dropna()) | set(lab.drop1.dropna())
        cand = qbname[(qbname.key == norm(starter)) & qbname.gsis_id.isin(ids)].gsis_id.unique()
        if len(cand) != 1:
            cand = qbname[qbname.key == norm(starter)].gsis_id.unique()
        cases.append(dict(case=i, season=season, team=team, starter_name=starter, starter=cand[0] if len(cand) == 1 else None, start=start,
                          reports=[dict(date=pd.Timestamp(x.date), code=x.code, lo=x.lo, hi=x.hi) for x in R[R.case == i].itertuples()]))
    return cases


def list_min(code, season):
    v = IR_MIN.get(code, {}).get(str(season), "missing")
    if v == "missing":
        raise SystemExit(f"list minimum for {code} {season} not set (research/qb_news/list_minimums.json)")
    return v


def remaining_range(rep, fut, played_since, season):
    """(a, b) further games out, or ('S',) for all remaining. fut: future team games (week, gameday) sorted; played_since: team games
    played between the report date (exclusive) and the cutoff."""
    c, lo, hi = rep["code"], rep["lo"], rep["hi"]
    nf = len(fut)
    if c == "S":
        return nf, nf
    if c in ("IR", "PUP"):
        m = list_min(c, season)
        if m is None:
            return nf, nf
        lo, hi, c = m, m + 2, "G"
    if c in ("W", "M"):
        f = 4.35 if c == "M" else 1.0
        dl, dh = rep["date"] + timedelta(days=7 * f * lo), rep["date"] + timedelta(days=7 * f * hi)
        return int((fut.gameday <= dl).sum()), int((fut.gameday <= dh).sum())
    if c == "UNTILWEEK":
        return int((fut.week < lo).sum()), int((fut.week < hi).sum())
    a, b = max(int(lo) - played_since, 0), max(int(hi) - played_since, 0)   # G, C, D, U
    return min(a, nf), min(b, nf)


def p_out(a, b, nf):
    if a == b == 0:
        a, b = 0, 1     # still out but overdue
    ks = np.arange(a, b + 1)
    return np.array([(ks >= j).mean() for j in range(1, nf + 1)])


def team_shifts(y, w, cases, greg, cur, gd, vals, low, ref, arm):
    """Per team: array of value shifts (before scale and lambda) for its remaining games, and an audit list."""
    cutoff = pd.Timestamp(greg[greg.week == w].gameday.max()) + timedelta(days=1)
    lab = LAB[LAB.season == y]
    st_of = {(r.game_id, r.team): r.chosen for r in lab.itertuples()}
    s = scrimmage(cur)
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    s["gameday"] = s.game_id.map(gd)
    out, audit = {}, []
    for t in TEAMS:
        fut = greg[(greg.week > w) & ((greg.home_team == t) | (greg.away_team == t))].sort_values(["week", "gameday"])
        fut = fut.assign(gameday=pd.to_datetime(fut.gameday))
        past = greg[(greg.week <= w) & ((greg.home_team == t) | (greg.away_team == t))].assign(gameday=lambda x: pd.to_datetime(x.gameday))
        act = []
        for c in cases:
            if c["season"] != y or c["team"] != t or c["start"] is None or c["start"] > cutoff or not c["starter"]:
                continue
            returned = any(st_of.get((g.game_id, t)) == c["starter"] for g in past.itertuples() if g.gameday > c["start"])
            reps = [r for r in c["reports"] if r["date"] <= cutoff and (arm == "news_all" and not (r["code"] == "U" and r is not c["reports"][0])
                                                                        or arm == "news_explicit" and r["code"] in EXPLICIT)]
            reps = [r for r in reps if r["code"] != "NONE"]
            if returned or not reps:
                audit.append(dict(season=y, week=w, team=t, case=c["case"], arm=arm, used=False, why="returned" if returned else "no usable report"))
                continue
            act.append((c, reps[-1]))
        if not act:
            continue
        c, rep = max(act, key=lambda x: x[0]["start"])
        out_ids = {x[0]["starter"] for x in act}
        played_since = int(((past.gameday > rep["date"]) & (past.gameday <= cutoff)).sum())
        a, b = remaining_range(rep, fut, played_since, y)
        p = p_out(a, b, len(fut))
        ts = s[s.posteam == t]
        bk = ts[(ts.gameday > c["start"]) & ~ts.qb.isin(out_ids)].qb.value_counts()
        if not len(bk):
            bk = ts[(ts.gameday == c["start"]) & ~ts.qb.isin(out_ids)].qb.value_counts()
        if not len(bk):
            bk = ts[~ts.qb.isin(out_ids)].qb.value_counts()
        backup = bk.index[0] if len(bk) else None
        r_id = ref.get(t)
        v = lambda q: float(vals.get(q, low)) if q else float(low)
        exp_v = p * v(backup) + (1 - p) * v(c["starter"])
        out[t] = exp_v - v(r_id) if r_id else np.zeros(len(fut))
        audit.append(dict(season=y, week=w, team=t, case=c["case"], arm=arm, used=True, code=rep["code"], report_date=str(rep["date"].date()),
                          a=a, b=b, remaining_games=len(fut), starter=c["starter_name"], backup=backup, ref=r_id, p_out_next=float(p[0]) if len(p) else None,
                          active_cases=len(act)))
    return out, audit


def rows_for(g, cases):
    rows, audit = [], []
    gd = dict(zip(g.game_id, pd.to_datetime(g.gameday)))
    for y in SEASONS:
        cur_all, pri, pri2 = load_pbp(y), load_pbp(y - 1), load_pbp(y - 2)
        out = B.outcomes(g, y)
        ew = eng_weights(y)
        for w in CHECKS:
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            cur = cur_all[(cur_all.week <= w) & (cur_all.season_type == "REG")]
            ratings.P["coef"] = WF[str(y)]["coef"]
            b4, _ = ratings.base_ratings(cur, pri, gg, y)
            _, XT = E.team_features(cur, pri, gg, y, w + 1, 4.0, 0, False)
            b5 = XT @ ew
            greg = gg[(gg.season == y) & (gg.game_type == "REG")].sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
            vals, low, _ = ratings.qb_values(cur, pri, pri2)
            ref = main_qb(cur)
            arms_sh = {}
            for arm in ("news_explicit", "news_all"):
                sh, au = team_shifts(y, w, cases, greg, cur, gd, vals, low, ref, arm)
                arms_sh[arm] = sh
                audit += au
            fut = greg[greg.week > w]
            for core, base, P in (("v4", b4, V4), ("v5", b5, V5)):
                R0 = P["scale"] * (base - base.mean())
                arms = [("none", 0.0)] if IDENTITY else [("none", 0.0)] + [(a, l) for a in ("news_explicit", "news_all") for l in LAMBDAS]
                for arm, lam in arms:
                    G = greg
                    if arm != "none":
                        G = greg.copy()
                        G["margin_adj"] = 0.0
                        sh = arms_sh[arm]
                        pos = {t: 0 for t in TEAMS}
                        adj = []
                        for r in fut.itertuples():
                            v = []
                            for t in (r.home_team, r.away_team):
                                v.append(sh[t][pos[t]] if t in sh else 0.0)
                                pos[t] += 1
                            adj.append(P["scale"] * lam * (v[0] - v[1]))
                        G.loc[G.week > w, "margin_adj"] = adj
                    for sset, fn in SEEDS.items():
                        res = simulate.simulate(G, R0, N, P["tau"], P["sigma"], P["hfa"], seed=fn(y, w), hfa_post=P["hfa_post"],
                                                n_seeds=7 if y >= 2020 else 6)
                        for i, t in enumerate(TEAMS):
                            rows.append(dict(season=y, week=w, core=core, arm=arm, lam=lam, seedset=sset, team=t,
                                             **{"p_" + k: float(res[k][i]) for k in MK}, **{"y_" + k: float(out[k][i]) for k in MK}))
            print(y, w, sum(a["used"] for a in audit if a["season"] == y and a["week"] == w and a["arm"] == "news_explicit"), flush=True)
    return pd.DataFrame(rows), pd.DataFrame(audit)


def identity(df):
    old = pd.read_csv(os.path.join(OUT, "nfl_qb_oracle_rows.csv.gz"))
    old = old[(old.arm == "none") & old.season.isin(SEASONS)]
    new = df[df.arm == "none"]
    m = old.merge(new, on=["season", "week", "core", "seedset", "team"], suffixes=("_o", "_n"))
    diff = max(float((m["p_" + k + "_o"] - m["p_" + k + "_n"]).abs().max()) for k in MK)
    return dict(rows_old=int(len(old)), rows_new=int(len(new)), matched=int(len(m)), max_abs_diff=diff, ok=bool(len(m) == len(old) == len(new) and diff < 1e-9))


def loss_table(df):
    return {(s, w, m): float(bll(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()).mean()) for (s, w), z in df.groupby(["season", "week"]) for m in MK}


def evaluate(D, core, lam, oracle):
    seasons = list(SEASONS)
    sub = lambda arm, l: D[(D.core == core) & (D.arm == arm) & (D.lam == l)]
    L = {"none": loss_table(sub("none", 0.0)), "news_explicit": loss_table(sub("news_explicit", lam)), "news_all": loss_table(sub("news_all", lam))}
    gain = lambda b, cells=PRIMARY: np.array([np.mean([L["none"][(s, w, m)] - L[b][(s, w, m)] for m, w in cells]) for s in seasons])
    rng = np.random.default_rng(20261028)
    idx = rng.integers(0, len(seasons), (10000, len(seasons)))
    out = {}
    for arm in ("news_explicit", "news_all"):
        g = gain(arm)
        bt = g[idx].mean(1)
        out[arm] = dict(mean=float(g.mean()), lower90=float(np.quantile(bt, .10)), upper90=float(np.quantile(bt, .90)), seasons_better=int((g > 0).sum()),
                        by_season={str(s): float(v) for s, v in zip(seasons, g)},
                        by_cell={f"{m}_w{w}": float(gain(arm, [(m, w)]).mean()) for m, w in PRIMARY},
                        division=float(gain(arm, [c for c in PRIMARY if c[0] == "div"]).mean()),
                        playoff=float(gain(arm, [c for c in PRIMARY if c[0] == "playoff"]).mean()),
                        capture_share_of_oracle=float(g.mean() / oracle) if oracle else None)
    P = out["news_explicit"]
    out["gates"] = {"lower90_pos": bool(P["lower90"] > 0), "ge_0.001": bool(P["mean"] >= 0.001),
                    "markets_nonneg": bool(P["division"] >= 0 and P["playoff"] >= 0), "upper90_below_0.001": bool(P["upper90"] < 0.001)}
    return out


def decide(g):
    if g["upper90_below_0.001"]:
        return "stop: news-based input not built"
    if g["lower90_pos"] and g["ge_0.001"] and g["markets_nonneg"]:
        return "build a live news input into v5 (separate dated change)"
    return "inconclusive"


def oracle_gain(core, lam):
    o = pd.read_csv(os.path.join(OUT, "nfl_qb_oracle_rows.csv.gz"))
    o = o[o.season.isin(SEASONS) & (o.core == core)]
    o = o.groupby(["season", "week", "arm", "lam", "team"], as_index=False).mean(numeric_only=True)
    Ln, Lp = loss_table(o[o.arm == "none"]), loss_table(o[(o.arm == "pergame") & (o.lam == lam)])
    return float(np.mean([np.mean([Ln[(s, w, m)] - Lp[(s, w, m)] for m, w in PRIMARY]) for s in SEASONS]))


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    if not IDENTITY and str(IR_MIN.get("status", "")).startswith("draft"):
        raise SystemExit("list minimums are a draft; the full run needs GPT's table")
    cases = load_cases()
    unmatched = [dict(case=c["case"], season=c["season"], team=c["team"], name=c["starter_name"]) for c in cases if not c["starter"]]
    print("cases", len(cases), "unmatched", unmatched, flush=True)
    df, audit = rows_for(g, cases)
    audit.to_csv(os.path.join(QN, "news_audit.csv"), index=False)
    idc = identity(df)
    print("identity", idc, flush=True)
    if IDENTITY or not idc["ok"]:
        json.dump(dict(identity=idc, unmatched=unmatched, stopped=not idc["ok"]), open(os.path.join(QN, "news_identity.json"), "w"), indent=2)
        return
    df.to_csv(os.path.join(OUT, "nfl_qb_news_rows.csv.gz"), index=False)
    avg = df.groupby(["season", "week", "core", "arm", "lam", "team"], as_index=False).mean(numeric_only=True)
    res = {}
    for core in ("v5", "v4"):
        for lam in LAMBDAS:
            k = f"{core}_lam{lam}"
            og = oracle_gain(core, lam)
            res[k] = {s: evaluate(df[df.seedset == s], core, lam, og) for s in SEEDS}
            res[k]["average"] = evaluate(avg, core, lam, og)
            res[k]["oracle_gain_2018_25"] = og
            agree = all(res[k]["A"]["gates"][x] == res[k]["B"]["gates"][x] for x in res[k]["A"]["gates"])
            res[k]["seed_sets_agree"] = agree
            res[k]["decision"] = decide(res[k]["average"]["gates"]) if agree else "inconclusive (seed sets disagree)"
            res[k]["mc_noise_A_minus_B"] = res[k]["A"]["news_explicit"]["mean"] - res[k]["B"]["news_explicit"]["mean"]
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    outj = dict(rule="research/NFL_QB_NEWS_RULE.md", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(), identity=idc,
                unmatched=unmatched, primary="v5_lam0.5", decision=res["v5_lam0.5"]["decision"], results=res,
                code_sha256=sha(__file__), rule_sha256=sha(os.path.join(OUT, "NFL_QB_NEWS_RULE.md")))
    open(os.path.join(OUT, "nfl_qb_news_results.json"), "w").write(json.dumps(outj, indent=2))
    print(json.dumps({k: dict(decision=v["decision"], oracle=v["oracle_gain_2018_25"], **{a: {x: v["average"][a][x] for x in ("mean", "lower90", "upper90",
                      "seasons_better", "division", "playoff", "capture_share_of_oracle")} for a in ("news_explicit", "news_all")}) for k, v in res.items()}, indent=2))


if __name__ == "__main__":
    main()
