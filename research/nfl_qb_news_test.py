"""News-based QB absence futures replay, version 3 (research/NFL_QB_NEWS_RULE.md, after GPT's review). Research only; nothing deployed.
Episodes come from official weekly status (outcome-independent); duration from bounded contemporaneous reports where available,
otherwise from earlier seasons' absence runs; one return draw per QB per simulated season.
Usage: python research/nfl_qb_news_test.py                (full run)
       QB_NEWS_IDENTITY=1 python research/nfl_qb_news_test.py   (none arm + episode audit; no gains)
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
sys.path.insert(0, os.path.join(ROOT, "research", "qb_news"))
import nfl_backtest as B  # noqa: E402
import nfl_engine as E  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import DATA, FIX, TEAMS, games, load_pbp, scrimmage  # noqa: E402
from nfl_futures_diagnosis import WF, V4, V5, eng_weights  # noqa: E402
from nfl_v5_promotion_test import bll  # noqa: E402
from nfl_qb_oracle_test import main_qb  # noqa: E402
from absence_runs import statuses, dropbacks_by_week, prior_leaders  # noqa: E402

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
LM = json.load(open(os.path.join(QN, "list_minimums.json")))
LAB = pd.read_csv(os.path.join(OUT, "nfl_qb_starter_labels.csv"))
RUNS = pd.read_csv(os.path.join(QN, "absence_runs.csv"))
TIX = {t: i for i, t in enumerate(TEAMS)}


def load_cases():
    d = pd.read_csv(os.path.join(QN, "gpt_qb_reports_2018_2025.csv"), encoding="utf-8-sig")
    R = pd.read_csv(os.path.join(QN, "qb_reports_coded.csv"))
    pl = pd.read_csv(os.path.join(DATA, "players.csv"), usecols=["gsis_id", "display_name", "position"], low_memory=False)
    q = pl[pl.position == "QB"].dropna(subset=["gsis_id"]).copy()
    norm = lambda x: re.sub(r"[^a-z]", "", str(x).lower())
    q["key"] = q.display_name.map(norm)
    cases = []
    for i, r in d.iterrows():
        who = [x.strip() for x in str(r.iloc[0]).split(";")]
        season, team = int(who[0]), FIX.get(who[1], who[1])
        name = re.sub(r"^starter:\s*", "", who[2])
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(r.iloc[1]))
        lab = LAB[(LAB.season.isin([season, season - 1])) & (LAB.team == team)]
        ids = set(lab.chosen.dropna()) | set(lab.drop1.dropna())
        cand = q[(q.key == norm(name)) & q.gsis_id.isin(ids)].gsis_id.unique()
        if len(cand) != 1:
            cand = q[q.key == norm(name)].gsis_id.unique()
        cases.append(dict(case=i, season=season, team=team, name=name, qb=cand[0] if len(cand) == 1 else None,
                          start=pd.Timestamp(m.group(1)) if m else None,
                          reports=[dict(date=pd.Timestamp(x.date), code=x.code, lo=x.lo, hi=x.hi, bounded=bool(x.bounded)) for x in R[R.case == i].itertuples()]))
    return cases


def report_range(rep, ep, season):
    """Remaining-absence support (a, b) in future team games implied by one report, anchored at its publication date, or None if the
    stated range is already exhausted (contradicted by continued absence) or unusable."""
    c, lo, hi, nf = rep["code"], rep["lo"], rep["hi"], ep["nf"]
    el = ep["elapsed_since"].get(str(rep["date"].date()), 0)
    if c == "S":
        return nf, nf
    if c == "C":
        return 0, 0
    if c in ("IR", "PUP"):
        m = LM[c].get(str(season))
        if m is None:
            return nf, nf
        lo, hi, c = m, m + 2, "G"
    if c in ("W", "M"):
        f = 4.35 if c == "M" else 1.0
        days = ep["fut_days"] + (ep["last_day"] - rep["date"]).days      # days from the report date to each future game
        a, b = int((days <= 7 * f * lo).sum()), int((days <= 7 * f * hi).sum())
        return (a, b) if b > 0 else None
    if c == "UNTILWEEK":
        a, b = int((ep["fut_weeks"] < lo).sum()), int((ep["fut_weeks"] < hi).sum())
        return (a, b) if b > 0 else None
    a, b = int(lo) - el, int(hi) - el
    return (max(a, 0), min(b, nf)) if b > 0 else None


def episodes(y, w, cases, greg, st, vals, low, ref, prior_leader, db):
    """Active absences at the week-w cutoff, from official status only (version 3): a run in progress at week w of the frozen
    pre-absence incumbent (absence_runs logic). News never adds an episode; it only supplies a timeline for one."""
    last_day = pd.Timestamp(greg[greg.week == w].gameday.max())
    lab = LAB[LAB.season == y]
    st_of = {(r.game_id, r.team): r.chosen for r in lab.itertuples()}
    out, audit = {}, []
    for t in TEAMS:
        tg = greg[((greg.home_team == t) | (greg.away_team == t))].assign(gameday=lambda x: pd.to_datetime(x.gameday)).sort_values("week")
        past, fut = tg[tg.week <= w], tg[tg.week > w]
        cur = None
        for g_ in past.itertuples():
            starter = st_of.get((g_.game_id, t))
            k = int(g_.week)
            if cur:
                if starter != cur["qb"] and (cur["qb"], k) in st:
                    cur["m"] += 1
                    cur["backup"] = starter
                    cur["weeks"].append(k)
                    continue
                cur = None
            prev = db[(db.posteam == t) & (db.week < k)]
            inc = prev.groupby("qb").n.sum().idxmax() if len(prev) else prior_leader.get(t)
            if inc is not None and starter != inc and (inc, k) in st:
                cur = dict(qb=inc, m=1, backup=starter, weeks=[k], first_week=k)
        if cur is None or cur["weeks"][-1] != int(past.week.max()):
            continue
        ep = cur
        # Version 3b (GPT's final check): no hard floors - reserve subtypes and transaction dates are not verified in our data.
        # Episodes with a reserve-list (RES) week are flagged; so are episodes running from the team's first game (possible job loss).
        ep["floor"], ep["placed_week"] = 0, None
        ep["res"] = any(st.get((ep["qb"], k)) == "RES" for k in ep["weeks"])
        ep["role_flag"] = ep["first_week"] == int(past.week.min())
        # timeline reports about this QB (publication date on or before the last week-w game date; US dates)
        reps = []
        for c in cases:
            if c["season"] == y and c["team"] == t and c["qb"] == ep["qb"] and c["start"] is not None and c["start"] <= last_day:
                reps += [r for r in c["reports"] if r["date"] <= last_day and r["code"] != "NONE"]
        ep["reports"] = sorted(reps, key=lambda r: r["date"])
        ep["last_day"] = last_day
        ep["fut_days"] = (fut.gameday - last_day).dt.days.to_numpy()
        ep["fut_weeks"] = fut.week.to_numpy()
        ep["nf"] = len(fut)
        ep["elapsed_since"] = {str(r["date"].date()): int(((past.gameday > r["date"]) & (past.gameday <= last_day)).sum()) for r in ep["reports"]}
        v = lambda q_: float(vals.get(q_, low)) if q_ else float(low)
        r_id = ref.get(t)
        ep.update(team=t, v_qb=v(ep["qb"]), v_backup=v(ep["backup"]), v_ref=v(r_id), ref=r_id)
        out[t] = ep
        audit.append(dict(season=y, week=w, team=t, qb=ep["qb"], backup=ep["backup"], ref=r_id, m=ep["m"], floor=ep["floor"], res=ep["res"], role_flag=ep["role_flag"],
                          placed_week=ep["placed_week"], n_reports=len(ep["reports"]), n_bounded=sum(r["bounded"] for r in ep["reports"]), nf=ep["nf"]))
    return out, audit


def km_hazard(y):
    """Discrete survival (Kaplan-Meier) hazards of returning after exactly l missed games, from earlier seasons' runs; runs that reach
    season end are right-censored. Sparse tail (fewer than 10 at risk): one pooled constant hazard for all l from there on."""
    r = RUNS[RUNS.season < y]
    L, cens = r.L.to_numpy(), r.censored.to_numpy().astype(bool)
    lmax = int(L.max()) if len(L) else 0
    haz, l0 = {}, None
    for l in range(1, lmax + 1):
        n = int((L >= l).sum())
        if n < 10:
            l0 = l
            break
        haz[l] = float(((L == l) & ~cens).sum()) / n
    if l0 is not None:
        exp_ = sum(int((L >= l).sum()) for l in range(l0, lmax + 1))
        ev = int(((L >= l0) & ~cens).sum())
        haz["tail"] = ev / exp_ if exp_ else 0.0
        haz["l0"] = l0
    return haz


def sample_km(haz, m, nf, rng):
    """Further games missed R (N draws), given m already missed: at each step the QB returns with hazard h(l) (l = total missed)."""
    R = np.zeros(N, int)
    alive = np.ones(N, bool)
    l = m
    for j in range(nf + 1):
        h = haz["tail"] if ("l0" in haz and l >= haz["l0"]) else haz.get(l, haz.get("tail", 0.0))
        ret = alive & (rng.random(N) < h)
        alive &= ~ret
        if j == nf or not alive.any():
            break
        R[alive] += 1
        l += 1
    return R      # unresolved draws stay out through the horizon


def draw_remaining(ep, mode, rng, y, haz):
    """Remaining absence R per simulation and its source. mode: 'empirical' (no news), 'bounded' (primary), 'mapping' (sensitivity)."""
    nf, allr = ep["nf"], ep.get("reports", [])
    R, src = None, None
    if mode in ("core", "bounded"):
        mode = "bounded"
    if mode != "empirical" and allr:
        last_b = [r for r in allr if (r["bounded"] if mode == "bounded" else not (r["code"] == "U" and r is not allr[0]))]
        cleared = [r for r in allr if r["code"] == "C" and (not last_b or r["date"] >= last_b[-1]["date"])]
        if cleared:
            R, src = np.zeros(N, int), "report:C"
        elif last_b:
            rr = report_range(last_b[-1], ep, y)
            if rr is not None:
                R, src = rng.integers(rr[0], rr[1] + 1, N), f"report:{last_b[-1]['code']}"
    if R is None:
        R, src = sample_km(haz, ep["m"], nf, rng), "survival"
    R = np.clip(np.maximum(R, ep["floor"]), 0, nf)
    return R, src + (f"+floor{ep['floor']}" if ep["floor"] else "")


def build_adj(eps, fut, mode, lam, scale, y, w, deterministic=False, haz=None):
    nG = len(fut)
    adj = np.zeros((N, nG), dtype=np.float32)
    pos = {t: [] for t in TEAMS}
    for k, r in enumerate(fut.itertuples()):
        pos[r.home_team].append((k, 1.0))
        pos[r.away_team].append((k, -1.0))
    src = {}
    for t, ep in eps.items():
        rng = np.random.default_rng(20261028 + 1000 * y + 10 * w + TIX[t])
        if mode == "core" and (ep["res"] or ep["role_flag"]):
            continue
        cols = pos[t]
        if deterministic:      # whole-season shortcut: the current backup for every remaining game
            d = scale * lam * (ep["v_backup"] - ep["v_ref"])
            for k, sg in cols:
                adj[:, k] += sg * d
            continue
        R, src[t] = draw_remaining(ep, mode, rng, y, haz)
        for j, (k, sg) in enumerate(cols, start=1):
            qv = np.where(j <= R, ep["v_backup"], ep["v_qb"])
            adj[:, k] += sg * scale * lam * (qv - ep["v_ref"])
    return adj, src


def rows_for(g, cases):
    rows, audit, srcs = [], [], []
    gd = dict(zip(g.game_id, pd.to_datetime(g.gameday)))
    for y in SEASONS:
        cur_all, pri, pri2 = load_pbp(y), load_pbp(y - 1), load_pbp(y - 2)
        out = B.outcomes(g, y)
        ew = eng_weights(y)
        st = statuses(y)
        dbw = dropbacks_by_week(y)
        prior_leader = prior_leaders(y)
        haz = km_hazard(y)
        for w in CHECKS:
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            cur = cur_all[(cur_all.week <= w) & (cur_all.season_type == "REG")]
            st_w = {k: v for k, v in st.items() if k[1] <= w}
            ratings.P["coef"] = WF[str(y)]["coef"]
            b4, _ = ratings.base_ratings(cur, pri, gg, y)
            _, XT = E.team_features(cur, pri, gg, y, w + 1, 4.0, 0, False)
            b5 = XT @ ew
            greg = gg[(gg.season == y) & (gg.game_type == "REG")].sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
            vals, low, _ = ratings.qb_values(cur, pri, pri2)
            ref = main_qb(cur)
            eps, au = episodes(y, w, cases, greg, st_w, vals, low, ref, prior_leader, dbw[dbw.week <= w])
            audit += au
            fut = greg[greg.week > w]
            if IDENTITY:      # duration sources only (no simulation with adjustments)
                for mode, arm in (("empirical", "empirical"), ("bounded", "news"), ("mapping", "news_mapping")):
                    _, src = build_adj(eps, fut, mode, 0.5, V5["scale"], y, w, haz=haz)
                    srcs += [dict(season=y, week=w, arm=arm, team=t, source=s_) for t, s_ in src.items()]
            for core, base, P in (("v4", b4, V4), ("v5", b5, V5)):
                R0 = P["scale"] * (base - base.mean())
                arms = [("none", 0.0)] if IDENTITY else [("none", 0.0)] + [(a, l) for a in ("shortcut", "empirical", "news", "news_mapping", "news_core") for l in LAMBDAS]
                for arm, lam in arms:
                    full = None
                    if arm != "none":
                        mode = {"news_mapping": "mapping", "news": "bounded", "empirical": "empirical", "news_core": "core"}.get(arm, "bounded")
                        adj, src = build_adj(eps, fut, mode, lam, P["scale"], y, w, deterministic=arm == "shortcut", haz=haz)
                        if core == "v5" and lam == 0.5:
                            srcs += [dict(season=y, week=w, arm=arm, team=t, source=s_) for t, s_ in src.items()]
                        full = np.zeros((N, len(greg)), dtype=np.float32)
                        full[:, (greg.week > w).to_numpy()] = adj
                    for sset, fn in SEEDS.items():
                        res = simulate.simulate(greg, R0, N, P["tau"], P["sigma"], P["hfa"], seed=fn(y, w), hfa_post=P["hfa_post"],
                                                n_seeds=7 if y >= 2020 else 6, adj_sims=full)
                        for i, t in enumerate(TEAMS):
                            rows.append(dict(season=y, week=w, core=core, arm=arm, lam=lam, seedset=sset, team=t,
                                             **{"p_" + k: float(res[k][i]) for k in MK}, **{"y_" + k: float(out[k][i]) for k in MK}))
            print(y, w, "episodes", len(eps), flush=True)
    return pd.DataFrame(rows), pd.DataFrame(audit), pd.DataFrame(srcs)


def identity(df):
    old = pd.read_csv(os.path.join(OUT, "nfl_qb_oracle_rows.csv.gz"))
    old = old[(old.arm == "none") & old.season.isin(SEASONS)]
    new = df[df.arm == "none"]
    m = old.merge(new, on=["season", "week", "core", "seedset", "team"], suffixes=("_o", "_n"))
    diff = max(float((m["p_" + k + "_o"] - m["p_" + k + "_n"]).abs().max()) for k in MK)
    return dict(rows_old=int(len(old)), rows_new=int(len(new)), matched=int(len(m)), max_abs_diff=diff, ok=bool(len(m) == len(old) == len(new) and diff < 1e-9))


def loss_table(df):
    return {(s, w, m): float(bll(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()).mean()) for (s, w), z in df.groupby(["season", "week"]) for m in MK}


def evaluate(D, core, lam, oracle_L):
    seasons = list(SEASONS)
    sub = lambda arm, l: D[(D.core == core) & (D.arm == arm) & (D.lam == l)]
    L = {"none": loss_table(sub("none", 0.0)), **{a: loss_table(sub(a, lam)) for a in ("shortcut", "empirical", "news", "news_mapping", "news_core")}, "oracle": oracle_L}
    gain = lambda a, b, cells=PRIMARY: np.array([np.mean([L[a][(s, w, m)] - L[b][(s, w, m)] for m, w in cells]) for s in seasons])
    rng = np.random.default_rng(20261028)
    idx = rng.integers(0, len(seasons), (10000, len(seasons)))
    out = {}
    for name, (a, b) in {"news_vs_none": ("none", "news"), "news_vs_shortcut": ("shortcut", "news"), "shortcut_vs_none": ("none", "shortcut"),
                         "empirical_vs_none": ("none", "empirical"), "news_vs_empirical": ("empirical", "news"),
                         "core_vs_none": ("none", "news_core"), "flagged_contribution": ("news_core", "news"),
                         "mapping_vs_none": ("none", "news_mapping"), "oracle_vs_none": ("none", "oracle")}.items():
        g = gain(a, b)
        bt = g[idx].mean(1)
        out[name] = dict(mean=float(g.mean()), lower90=float(np.quantile(bt, .10)), upper90=float(np.quantile(bt, .90)), seasons_better=int((g > 0).sum()),
                         by_season={str(s): float(v) for s, v in zip(seasons, g)}, by_cell={f"{m}_w{w}": float(gain(a, b, [(m, w)]).mean()) for m, w in PRIMARY},
                         division=float(gain(a, b, [c for c in PRIMARY if c[0] == "div"]).mean()),
                         playoff=float(gain(a, b, [c for c in PRIMARY if c[0] == "playoff"]).mean()))
    o = out["oracle_vs_none"]["mean"]
    out["capture_share_descriptive"] = out["news_vs_none"]["mean"] / o if o else None
    P = out["news_vs_none"]
    out["gates"] = {"lower90_pos": bool(P["lower90"] > 0), "ge_0.001": bool(P["mean"] >= 0.001),
                    "markets_nonneg": bool(P["division"] >= 0 and P["playoff"] >= 0), "upper90_below_0.001": bool(P["upper90"] < 0.001)}
    return out


def decide(g):
    if g["upper90_below_0.001"]:
        return "fail: this specified mapping fails (not generalised to all news-based QB inputs)"
    if g["lower90_pos"] and g["ge_0.001"] and g["markets_nonneg"]:
        return "pass: implement and archive a live shadow input; displayed v5 unchanged pending forward evaluation"
    return "inconclusive"


def oracle_losses(core, lam, seedset=None):
    o = pd.read_csv(os.path.join(OUT, "nfl_qb_oracle_rows.csv.gz"))
    o = o[o.season.isin(SEASONS) & (o.core == core) & (o.arm == "pergame") & (o.lam == lam)]
    o = o[o.seedset == seedset] if seedset else o.groupby(["season", "week", "team"], as_index=False).mean(numeric_only=True)
    return loss_table(o)


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    cases = load_cases()
    unmatched = [dict(case=c["case"], name=c["name"]) for c in cases if not c["qb"]]
    print("cases", len(cases), "unmatched", unmatched, flush=True)
    # coverage: week-1 incumbents excluded because the previous-season leader is not on the team's roster
    import absence_runs as AR
    cov = []
    for y in SEASONS:
        pdb = AR.dropbacks_by_week(y - 1)
        lead = pdb.groupby(["posteam", "qb"]).n.sum().reset_index().sort_values("n").groupby("posteam").qb.last().to_dict()
        kept = prior_leaders(y)
        cov += [dict(season=y, team=t, prior_leader=q, kept=t in kept) for t, q in lead.items()]
    pd.DataFrame(cov).to_csv(os.path.join(QN, "news_v3b_week1_coverage.csv"), index=False)
    df, audit, srcs = rows_for(g, cases)
    audit.to_csv(os.path.join(QN, "news_v2_episodes.csv"), index=False)
    if len(srcs):
        srcs.to_csv(os.path.join(QN, "news_v2_duration_sources.csv"), index=False)
    idc = identity(df)
    print("identity", idc, flush=True)
    if IDENTITY or not idc["ok"]:
        json.dump(dict(identity=idc, unmatched=unmatched, stopped=not idc["ok"]), open(os.path.join(QN, "news_v2_identity.json"), "w"), indent=2)
        return
    df.to_csv(os.path.join(OUT, "nfl_qb_news_rows.csv.gz"), index=False)
    avg = df.groupby(["season", "week", "core", "arm", "lam", "team"], as_index=False).mean(numeric_only=True)
    res = {}
    for core in ("v5", "v4"):
        for lam in LAMBDAS:
            k = f"{core}_lam{lam}"
            res[k] = {s: evaluate(df[df.seedset == s], core, lam, oracle_losses(core, lam, s)) for s in SEEDS}
            res[k]["average"] = evaluate(avg, core, lam, oracle_losses(core, lam))
            agree = all(res[k]["A"]["gates"][x] == res[k]["B"]["gates"][x] for x in res[k]["A"]["gates"])
            res[k]["seed_sets_agree"] = agree
            res[k]["decision"] = decide(res[k]["average"]["gates"]) if agree else "inconclusive (seed sets disagree)"
            res[k]["mc_noise_A_minus_B"] = res[k]["A"]["news_vs_none"]["mean"] - res[k]["B"]["news_vs_none"]["mean"]
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    outj = dict(rule="research/NFL_QB_NEWS_RULE.md", version="3b", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
                identity=idc, unmatched=unmatched, primary="v5_lam0.5", decision=res["v5_lam0.5"]["decision"], results=res,
                code_sha256=sha(__file__), rule_sha256=sha(os.path.join(OUT, "NFL_QB_NEWS_RULE.md")))
    open(os.path.join(OUT, "nfl_qb_news_results.json"), "w").write(json.dumps(outj, indent=2))
    print(json.dumps({k: dict(decision=v["decision"], capture=v["average"]["capture_share_descriptive"], **{n: {x: v["average"][n][x] for x in ("mean", "lower90", "upper90",
                      "seasons_better", "division", "playoff")} for n in ("news_vs_none", "news_vs_empirical", "empirical_vs_none", "core_vs_none", "flagged_contribution", "news_vs_shortcut", "shortcut_vs_none", "mapping_vs_none", "oracle_vs_none")})
                      for k, v in res.items()}, indent=2))


if __name__ == "__main__":
    main()
