"""NBA stage one per research/NBA_MINUTES_RULE.md.
  python research/nba_minutes_test.py build <official_reports_dir>   -> data/research/nba_minutes_rows.csv.gz
  python research/nba_minutes_test.py score                          -> research/nba_minutes_results.json
"""
import collections
import glob
import json
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
ROWS = os.path.join(ROOT, "data", "research", "nba_minutes_rows.csv.gz")
FIRST_BOX, LAST = 2016, 2026
TEST = [2022, 2023, 2024, 2025, 2026]
MAXM = 53
GROUP = {"PG": "G", "SG": "G", "G": "G", "SF": "W", "GF": "W", "F": "W", "PF": "B", "C": "B", "FC": "B", "F-C": "B", "C-F": "B", "G-F": "W", "F-G": "W"}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def name_key(display):
    return _norm(re.sub(r"\b(Jr\.?|Sr\.?|II|III|IV)\b", "", display if isinstance(display, str) else ""))


def player_key(printed):
    last, _, first = (printed if isinstance(printed, str) else "").partition(",")
    last = re.sub(r"(Jr\.?|Sr\.?|II|III|IV)$", "", last.strip())
    return _norm(first + last)


def load_box():
    frames = []
    for y in range(FIRST_BOX, LAST + 1):
        d = pd.read_csv(os.path.join(ROOT, "data", "nba", f"player_box_{y}.csv"), low_memory=False,
                        usecols=["game_id", "season", "season_type", "game_date_time", "athlete_id", "athlete_display_name", "team_abbreviation",
                                 "team_display_name", "minutes", "starter", "athlete_position_abbreviation"])
        d = d[pd.to_numeric(d.season_type, errors="coerce") == 2]
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0.0)
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    d = d.dropna(subset=["athlete_id"])
    d["athlete_id"] = d.athlete_id.astype(int)
    d["tip"] = pd.to_datetime(d.game_date_time, utc=True, errors="coerce", format="ISO8601")
    d["season"] = pd.to_numeric(d.season, errors="coerce").astype(int)
    d["starter"] = d.starter.astype(str).str.lower().eq("true")
    d["grp"] = d.athlete_position_abbreviation.map(GROUP).fillna("W")
    return d.sort_values(["tip", "game_id"])


def load_reports(src):
    fs = [f for f in glob.glob(os.path.join(src, "rep_*.csv.gz")) if os.path.getsize(f) > 100]
    R = pd.concat([pd.read_csv(f) for f in fs]).drop_duplicates(["game_date", "team", "player", "report"])
    R = R[R.status.isin(["Out", "Doubtful", "Questionable", "Probable", "Available"])].copy()
    hm = R.report.str[11:].str.replace("PM", "").str.split("_")
    hour = hm.str[0].astype(int) + 12
    minute = hm.str[1].fillna("0").astype(int)
    R["rtime"] = (pd.to_datetime(R.game_date) + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m")).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    R["pkey"] = R.player.map(player_key)
    return R


def build(src):
    d = load_box()
    R = load_reports(src)
    import nba_teams
    # canonical ESPN abbreviation from the league code or the team name (fix 20 Oct 2026: league codes NYK, SAS, GSW, NOP, UTA, WAS
    # were previously used as-is, so in the 2026 season those six teams never received report statuses)
    R["team_abbr"] = [nba_teams.resolve(c) or nba_teams.resolve(t) for c, t in zip(R.team_code if "team_code" in R else [None] * len(R), R.team)]
    keymap = {}
    for (s, k), ids in d.assign(k=d.athlete_display_name.map(name_key)).groupby(["season", "k"]).athlete_id.unique().items():
        if len(ids) == 1:
            keymap[(s, k)] = int(ids[0])
    R["aid"] = [keymap.get((int(s), k)) for s, k in zip(R.season, R.pkey)]
    # rows whose team cell was misparsed (older parsed files put the injury category there; fix 20 Oct 2026, previously ~29k rows were
    # silently dropped): the team is the one of the two matchup teams the player last appeared for on or before that game date
    R = R.reset_index(drop=True)
    bad = R.team_abbr.isna()
    if bad.any():
        app = d[d.minutes > 0][["season", "athlete_id", "tip", "team_abbreviation"]].sort_values("tip")
        last = {k: (np.array([t.value for t in g.tip]), g.team_abbreviation.to_numpy()) for k, g in app.groupby(["season", "athlete_id"])}
        rec = 0
        for i in R.index[bad & R.aid.notna()]:
            mu = str(R.at[i, "matchup"]) if "matchup" in R else ""
            if "@" not in mu:
                continue
            pair = {nba_teams.resolve(x) for x in mu.split("@")}
            g = last.get((int(R.at[i, "season"]), int(R.at[i, "aid"])))
            if g is None:
                continue
            day_end = pd.Timestamp(str(R.at[i, "game_date"])[:10], tz="America/New_York") + pd.Timedelta(days=1)
            j = int((g[0] < day_end.value).sum())
            if j > 0 and g[1][j - 1] in pair:
                R.at[i, "team_abbr"] = g[1][j - 1]
                rec += 1
        # players with no appearance yet this season (e.g. long-term injured): the matchup team given for them in an earlier report row
        # (or, failing that, last season's team)
        good = R[R.team_abbr.notna() & R.aid.notna()].sort_values("rtime")
        prior = {k: (np.array([t.value for t in g.rtime]), g.team_abbr.to_numpy()) for k, g in good.groupby(["season", "aid"])}
        lastseason = {(int(k[0]) + 1, int(k[1])): g[1][-1] for k, g in last.items()}
        rec2 = 0
        for i in R.index[R.team_abbr.isna() & R.aid.notna()]:
            mu = str(R.at[i, "matchup"]) if "matchup" in R else ""
            if "@" not in mu:
                continue
            pair = {nba_teams.resolve(x) for x in mu.split("@")}
            key = (int(R.at[i, "season"]), int(R.at[i, "aid"]))
            g = prior.get(key)
            t = None
            if g is not None:
                j = int((g[0] <= R.at[i, "rtime"].value).sum())
                if j > 0 and g[1][j - 1] in pair:
                    t = g[1][j - 1]
            if t is None and lastseason.get(key) in pair:
                t = lastseason[key]
            if t is not None:
                R.at[i, "team_abbr"] = t
                rec2 += 1
        rec += rec2
        left = R.team_abbr.isna()
        print("report rows with a misparsed team:", int(bad.sum()), "recovered from matchup and appearances:", rec,
              "still dropped:", int(left.sum()), flush=True)
    R = R.dropna(subset=["aid", "team_abbr"])
    R["aid"] = R.aid.astype(int)
    rep_by_team = {t: g.sort_values("rtime") for t, g in R.groupby("team_abbr")}
    rep_times = {t: g.rtime.drop_duplicates().to_numpy() for t, g in rep_by_team.items()}

    def report_at(team, cutoff):
        """statuses for a team from the latest report published at or before cutoff (and within 3 days)"""
        g = rep_by_team.get(team)
        if g is None:
            return {}, None
        sub = g[g.rtime <= cutoff]
        if sub.empty:
            return {}, None
        t = sub.rtime.max()
        if (cutoff - t) > pd.Timedelta(days=3):
            return {}, None
        last = sub[sub.rtime == t]
        return dict(zip(last.aid, last.status)), t

    # per-player state
    hist = collections.defaultdict(list)          # aid -> list of (team_game_idx_on_team, minutes, starter) for current team
    last_team = {}
    grp_of = {}
    season_of = {}
    team_idx = collections.Counter()               # (season, team) -> games played so far
    played_games = collections.defaultdict(list)   # aid -> list of minutes in games played (any team), this season
    roster = collections.defaultdict(set)         # (season, team) -> players whose latest team this season is team
    pl = d[d.minutes > 0].groupby(["season", "athlete_id"]).minutes.agg(["mean", "size"])
    prev = {(int(y) + 1, int(a)): (float(m), int(n)) for (y, a), (m, n) in pl.iterrows()}   # last season: minutes per game played, games played
    out = []
    ng = 0
    for gid, G in d.groupby("game_id", sort=False):
        ng += 1
        tip = G.tip.iloc[0]
        y = int(G.season.iloc[0])
        for t, X in G.groupby("team_abbreviation"):
            key = (y, t)
            gi = team_idx[key]
            present = dict(zip(X.athlete_id, X.minutes))
            starters = set(X[X.starter].athlete_id)
            for a, g_ in zip(X.athlete_id, X.grp):
                grp_of[a] = g_
            cands = list(roster[key])
            if y >= 2020:
                st1, rt1 = report_at(t, tip - pd.Timedelta(hours=1))
                st6, rt6 = report_at(t, tip - pd.Timedelta(hours=6))
            else:
                st1, st6, rt1, rt6 = {}, {}, None, None
            for a in st1:
                if a not in cands and (last_team.get(a) in (None, t) or season_of.get(a) != y):
                    cands.append(a)
            feats = {}
            for a in cands:
                h = [x for x in hist[a] if x[0] < gi][-10:] if last_team.get(a) == t and season_of.get(a) == y else []
                n_team = min(10, gi - (hist[a][0][0] if hist[a] and last_team.get(a) == t and season_of.get(a) == y else gi))
                played = [m for m in played_games[a] if m > 0] if season_of.get(a) == y else []
                last10p = played[-10:]
                w = 0.5 ** (np.arange(len(played))[::-1] / 10.0)
                ewm = float(np.sum(w * np.array(played)) / w.sum()) if played else np.nan
                app10 = (sum(1 for x in h if x[1] > 0) / max(1, n_team)) if n_team > 0 else np.nan
                streak = 0
                for x in reversed(h):
                    if x[1] > 0:
                        break
                    streak += 1
                feats[a] = dict(app10=app10, mpg10=float(np.mean(last10p)) if last10p else np.nan, ewm=ewm,
                                season_mpg=float(np.mean(played)) if played else np.nan,
                                season_app=(len(played) / max(1, gi)) if gi else np.nan,
                                start10=float(np.mean([x[2] for x in h if x[1] > 0])) if any(x[1] > 0 for x in h) else 0.0,
                                streak=streak, st1=st1.get(a, ""), st6=st6.get(a, ""), grp=grp_of.get(a, "W"))
            # vacated minutes from teammates ruled out at each forecast time
            for tag, stc in (("1", "st1"), ("6", "st6")):
                pm = {"Out": 1.0, "Doubtful": 0.97, "Questionable": 0.45}
                vac = collections.Counter()
                for a, f in feats.items():
                    exp = f["ewm"] if f["ewm"] == f["ewm"] else 0.0
                    if exp >= 12:
                        vac[f["grp"]] += exp * pm.get(f[stc], 0.0)
                for a, f in feats.items():
                    f["vac_same" + tag] = vac[f["grp"]] - (f["ewm"] if f["ewm"] == f["ewm"] else 0.0) * pm.get(f[stc], 0.0)
                    f["vac_other" + tag] = sum(v for g_, v in vac.items() if g_ != f["grp"])
            for a, f in feats.items():
                out.append(dict(season=y, game_id=gid, tip=str(tip), team=t, aid=a, gi=gi, minutes=float(present.get(a, 0.0)),
                                started=int(a in starters), rep1=str(rt1) if rt1 is not None else "", **f))
            # fallback rows (scored separately): players listed in this game's box (a proxy for the public roster) who were not candidates;
            # only last season's minutes and games are used as inputs, never this game's minutes
            for a, m in present.items():
                if a not in feats:
                    pm_, pn_ = prev.get((y, a), (np.nan, 0))
                    out.append(dict(season=y, game_id=gid, tip=str(tip), team=t, aid=a, gi=gi, minutes=float(m), fallback=1,
                                    prev_mpg=pm_, prev_gp=pn_, grp=grp_of.get(a, "W")))
            # update state
            for a, m in present.items():
                if last_team.get(a) != t or season_of.get(a) != y:
                    if a in last_team:
                        roster[(season_of[a], last_team[a])].discard(a)
                    roster[key].add(a)
                    hist[a] = []
                    if season_of.get(a) != y:
                        played_games[a] = []
                last_team[a] = t
                season_of[a] = y
                hist[a].append((gi, m, a in starters))
                played_games[a].append(m)
            for a in cands:
                if a not in present and last_team.get(a) == t and season_of.get(a) == y:
                    hist[a].append((gi, 0.0, False))
            team_idx[key] += 1
        if ng % 2000 == 0:
            print(ng, len(out), str(tip)[:10], flush=True)
    D = pd.DataFrame(out)
    D.to_csv(ROWS, index=False, compression="gzip")
    print("rows", len(D))


# ---------------------------------------------------------------- scoring
PM = ["Out", "Doubtful", "Questionable", "Probable", "Available"]


def disc_normal(mu, sd):
    """P(minutes = k | appear), k = 1..MAXM, discretised normal truncated to [1, MAXM]."""
    k = np.arange(1, MAXM + 1)
    c = norm.cdf((k[None, :] + 0.5 - mu[:, None]) / sd[:, None]) - norm.cdf((k[None, :] - 0.5 - mu[:, None]) / sd[:, None])
    c = np.clip(c, 1e-12, None)
    return c / c.sum(1, keepdims=True)


def rps(pa, q, y):
    """unconditional RPS over 0..MAXM: P(0) = 1 - pa, P(k) = pa q_k."""
    P = np.column_stack([1 - pa, pa[:, None] * q])
    F = np.cumsum(P, 1)
    Y = (np.arange(MAXM + 1)[None, :] >= np.clip(np.round(y), 0, MAXM)[:, None]).astype(float)
    return ((F - Y) ** 2).sum(1) / MAXM


def sd_fit(mu, y):
    """sd = a + b mu fitted on absolute residuals (normal scaling)."""
    X = np.column_stack([np.ones(len(mu)), mu])
    b = np.linalg.lstsq(X, np.abs(y - mu) * np.sqrt(np.pi / 2), rcond=None)[0]
    return lambda m: np.clip(b[0] + b[1] * m, 2.0, 15.0)


def score():
    from sklearn.linear_model import LogisticRegression
    D = pd.read_csv(ROWS)
    if "fallback" not in D:
        D["fallback"] = 0
    D["fallback"] = D.fallback.fillna(0)
    FB = D[(D.fallback == 1) & (D.season >= 2020)].copy()
    unexpected = FB[FB.minutes > 0].groupby("season").size().to_dict()
    D = D[(D.fallback == 0) & (D.aid != -1) & (D.season >= 2020)].copy()
    D["y_app"] = (D.minutes > 0).astype(float)
    for c in ("st1", "st6"):
        D[c] = D[c].fillna("")
    D["newcomer"] = D["ewm"].isna()
    fill = {"app10": 0.5, "mpg10": 12.0, "ewm": 12.0, "season_mpg": 12.0, "season_app": 0.5}
    for c, v in fill.items():
        D[c] = D[c].fillna(v)
    D["early"] = (D.gi < 10).astype(float)
    res = {"unexpected_appearances_not_scored": {int(k): int(v) for k, v in unexpected.items()}, "by_time": {}}
    for tag in ("1", "6"):
        st = D["st" + tag]
        preds = {}
        for s in TEST:
            tr, te = (D.season < s).to_numpy(), (D.season == s).to_numpy()
            T = D[tr]
            # availability from report status (calibrated on training seasons)
            pmiss = {k: float(1 - T[T["st" + tag] == k].y_app.mean()) for k in PM if (T["st" + tag] == k).sum() > 50}
            pm_te = st[te].map(pmiss).fillna(0.0).to_numpy()
            # appears given available: logistic on rows not listed Out/Doubtful/Questionable
            Xc = ["app10", "mpg10", "start10", "streak", "vac_same" + tag, "vac_other" + tag, "early", "ewm", "newcomer"]
            ok = ~T["st" + tag].isin(["Out", "Doubtful", "Questionable"])
            Xf = lambda Z: np.column_stack([Z.app10, Z.mpg10 / 48, Z.start10, np.log1p(Z.streak), Z["vac_same" + tag] / 48, Z["vac_other" + tag] / 48, Z.early, Z["ewm"] / 48, Z.newcomer.astype(float)])
            lr = LogisticRegression(C=1.0, max_iter=500).fit(Xf(T[ok]), T[ok].y_app)
            Z = D[te]
            pa_M = (1 - pm_te) * lr.predict_proba(Xf(Z))[:, 1]
            # minutes given appearing
            P = T[T.minutes > 0]
            Xm = lambda Z: np.column_stack([np.ones(len(Z)), Z["ewm"], Z.season_mpg, Z["vac_same" + tag] * Z["ewm"] / 36, Z["vac_other" + tag] * Z["ewm"] / 36,
                                            ((Z.streak >= 2) & (Z["st" + tag] != "Out")).astype(float), Z.start10, Z.early, Z.newcomer.astype(float)])
            bm = np.linalg.lstsq(Xm(P), P.minutes.to_numpy(), rcond=None)[0]
            muP = np.clip(Xm(P) @ bm, 1, 48)
            sdM = sd_fit(muP, P.minutes.to_numpy())
            mu_M = np.clip(Xm(Z) @ bm, 1, 48)
            q_M = disc_normal(mu_M, sdM(mu_M))
            # baselines
            sd1 = sd_fit(P.season_mpg.to_numpy(), P.minutes.to_numpy())
            sd2 = sd_fit(P.mpg10.to_numpy(), P.minutes.to_numpy())
            pa_B1 = np.clip(Z.season_app.to_numpy(), 0.02, 0.98)
            pa_B2 = np.where(Z["st" + tag].isin(["Out", "Doubtful"]), 0.03, np.clip(Z.app10.to_numpy(), 0.02, 0.98))
            q_B1 = disc_normal(Z.season_mpg.clip(1, 48).to_numpy(), sd1(Z.season_mpg.clip(1, 48).to_numpy()))
            q_B2 = disc_normal(Z.mpg10.clip(1, 48).to_numpy(), sd2(Z.mpg10.clip(1, 48).to_numpy()))
            yv = Z.minutes.to_numpy()
            rng0 = np.random.default_rng(s)
            for name, pa, q in (("M", pa_M, q_M), ("B1", pa_B1, q_B1), ("B2r", pa_B2, q_B2)):
                pa = np.clip(pa, 1e-3, 1 - 1e-3)
                ya = Z.y_app.to_numpy()
                Fq = np.cumsum(q, 1)
                yk = np.clip(np.round(yv), 1, MAXM).astype(int)
                hi = Fq[np.arange(len(yk)), yk - 1]
                lo = np.where(yk > 1, Fq[np.arange(len(yk)), np.maximum(yk - 2, 0)], 0.0)
                pit = np.where(yv > 0, lo + rng0.random(len(yk)) * (hi - lo), np.nan)   # randomised PIT of minutes given appearing
                preds.setdefault(name, []).append(pd.DataFrame({"idx": Z.index, "rps": rps(pa, q, yv),
                                                                "ll": -(ya * np.log(pa) + (1 - ya) * np.log(1 - pa)), "pa": pa, "pit": pit}))
        out = {}
        S = {k: pd.concat(v).set_index("idx").loc[D[D.season.isin(TEST)].index] for k, v in preds.items()}
        X = D.loc[S["M"].index]
        wk = (X.season.astype(str) + "_" + pd.to_datetime(X.tip).dt.isocalendar().week.astype(str)).to_numpy()
        for k in S:
            pit = S[k].pit.dropna().to_numpy()
            out[k] = {"rps": round(float(S[k].rps.mean()), 5), "app_logloss": round(float(S[k].ll.mean()), 5),
                      "pit_deciles_given_appearing (0.10 each = calibrated)": [round(float(v), 3) for v in np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)]}
        gain = (S["B2r"].rps - S["M"].rps).to_numpy()
        rng = np.random.default_rng(12)
        keys = np.unique(wk)
        idx = {k: np.where(wk == k)[0] for k in keys}
        bs = [gain[np.concatenate([idx[k] for k in rng.choice(keys, len(keys))])].mean() for _ in range(2000)]
        bys = {int(s): round(float(gain[(X.season == s).to_numpy()].mean()), 5) for s in TEST}
        ret = ((X.streak >= 2) & (X["st" + tag] != "Out")).to_numpy()
        tm_out = (X["vac_same" + tag] + X["vac_other" + tag] >= 25).to_numpy()
        sub = {"returning": float(gain[ret].mean()), "teammate_out_25mpg": float(gain[tm_out].mean()),
               "starters": float(gain[(X.start10 >= 0.5).to_numpy()].mean()), "bench": float(gain[(X.start10 < 0.5).to_numpy()].mean()),
               "team_games_1_10": float(gain[(X.gi < 10).to_numpy()].mean()), "later": float(gain[(X.gi >= 10).to_numpy()].mean())}
        out["M_vs_B2r"] = {"gain_rps": round(float(gain.mean()), 5), "gain_pct": round(float(gain.mean() / S["B2r"].rps.mean() * 100), 2),
                           "lower90": round(float(np.percentile(bs, 10)), 5), "by_season": bys, "subgroups": {k: round(v, 5) for k, v in sub.items()},
                           "n": int(len(gain)), "n_returning": int(ret.sum()), "n_teammate_out": int(tm_out.sum())}
        g = {"1_rps_lower_bound_above_0": out["M_vs_B2r"]["lower90"] > 0, "2_4_of_5_seasons": sum(v > 0 for v in bys.values()) >= 4,
             "3_app_logloss": out["M"]["app_logloss"] < out["B2r"]["app_logloss"], "4_returning_and_teammate_out_not_worse": sub["returning"] >= 0 and sub["teammate_out_25mpg"] >= 0}
        out["gates"] = {k: bool(v) for k, v in g.items()}
        out["all_pass"] = bool(all(g.values())) if tag == "1" else None
        res["by_time"][f"{tag}h_before"] = out
    res["fallback_unseen_players"] = score_fallback(FB)
    json.dump(res, open(os.path.join(HERE, "nba_minutes_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


def score_fallback(FB):
    """Players listed in the box who were not candidates (debuts, opening night, new arrivals). Model F: last-season minutes prior;
    baseline FB0: training-season averages for such players. Reported only (not a stage-one gate)."""
    from sklearn.linear_model import LogisticRegression
    FB = FB.copy()
    FB["has_prev"] = FB.prev_mpg.notna().astype(float)
    FB["pm"] = FB.prev_mpg.fillna(0.0)
    FB["early"] = (FB.gi < 3).astype(float)
    FB["y_app"] = (FB.minutes > 0).astype(float)
    rows = []
    for s in TEST:
        T, Z = FB[FB.season < s], FB[FB.season == s]
        if len(T) < 200 or len(Z) == 0:
            continue
        X = lambda Q: np.column_stack([Q.has_prev, Q.pm / 48, np.log1p(Q.prev_gp), Q.early])
        lr = LogisticRegression(max_iter=500).fit(X(T), T.y_app)
        P = T[T.minutes > 0]
        Xm = lambda Q: np.column_stack([np.ones(len(Q)), Q.has_prev, Q.pm, Q.early])
        b = np.linalg.lstsq(Xm(P), P.minutes, rcond=None)[0]
        sdf = sd_fit(np.clip(Xm(P) @ b, 1, 48), P.minutes.to_numpy())
        mu = np.clip(Xm(Z) @ b, 1, 48)
        pa_F = np.clip(lr.predict_proba(X(Z))[:, 1], 1e-3, 1 - 1e-3)
        pa_0 = np.full(len(Z), np.clip(T.y_app.mean(), 1e-3, 1 - 1e-3))
        mu0 = np.full(len(Z), float(np.clip(P.minutes.mean(), 1, 48)))
        sd0 = float(np.std(P.minutes))
        yv, ya = Z.minutes.to_numpy(), Z.y_app.to_numpy()
        rows.append(dict(season=s, n=len(Z), rps_F=float(rps(pa_F, disc_normal(mu, sdf(mu)), yv).mean()),
                         rps_0=float(rps(pa_0, disc_normal(mu0, np.full(len(Z), sd0)), yv).mean()),
                         ll_F=float(np.mean(-(ya * np.log(pa_F) + (1 - ya) * np.log(1 - pa_F)))),
                         ll_0=float(np.mean(-(ya * np.log(pa_0) + (1 - ya) * np.log(1 - pa_0))))))
    R = pd.DataFrame(rows)
    if R.empty:
        return {}
    w = R.n / R.n.sum()
    return {"rows": int(R.n.sum()), "rps_fallback_model": round(float((R.rps_F * w).sum()), 5), "rps_average_baseline": round(float((R.rps_0 * w).sum()), 5),
            "app_logloss_model": round(float((R.ll_F * w).sum()), 4), "app_logloss_baseline": round(float((R.ll_0 * w).sum()), 4),
            "seasons_better": int((R.rps_F < R.rps_0).sum()), "by_season": R.round(5).to_dict("records")}


if __name__ == "__main__":
    build(sys.argv[2]) if sys.argv[1] == "build" else score()
