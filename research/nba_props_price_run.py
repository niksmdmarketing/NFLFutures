"""Run research/NBA_PROPS_PRICE_TEST_RULE.md: assemble prices, forecasts and outcomes, then the mechanics check or the scoring.

  export-w2 <dest>     copy the 2026-27 forward forecasts (forecast-archive branch, nba/props_forward/<date>/<game>_60_*.json.gz,
                       params "b") to <dest>; needs `git fetch origin forecast-archive` first (FETCH_HEAD)
  mechanics            coverage, matching and timing checks only - no outcome, edge or profit is computed
  score                the rule's tests (writes research/nba_props_price_results.json)
Common options: --prices <dir of OddsPapi props csv.gz> --w1 <window-1 archive> --w2 <exported window-2 dir> [--out <json>]
Forecast used per game: the latest 60-minute record generated at or before its cutoff. Points pts_d_v2, rebounds reb_v2, assists
ast_v2 (primary); v3 versions reported. Outcomes from ESPN player boxes; a player with no minutes is void.
"""
import argparse
import glob
import gzip
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nba_props_names as NM  # noqa: E402
import nba_props_price_test as PT  # noqa: E402

DIST = {"v2": {"pts": "pts_d_v2", "reb": "reb_v2", "ast": "ast_v2"}, "v3": {"pts": "pts_d_v3", "reb": "reb_v3", "ast": "ast_v3"}}
WINDOW1_END = pd.Timestamp("2026-05-01", tz="UTC")


def export_w2(dest):
    files = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "--name-only", "FETCH_HEAD", "--", "nba/props_forward"],
                           capture_output=True, text=True, check=True).stdout.split()
    files = [f for f in files if f.count("/") == 3 and "_60_" in f and f.endswith(".json.gz")]
    os.makedirs(dest, exist_ok=True)
    n = 0
    for f in files:
        out = os.path.join(dest, f.replace("/", "__"))
        if os.path.exists(out):
            continue
        b = subprocess.run(["git", "-C", ROOT, "show", f"FETCH_HEAD:{f}"], capture_output=True, check=True).stdout
        open(out, "wb").write(b)
        n += 1
    print("exported", n, "of", len(files))


def forecasts(dirs):
    """One row per game, player: the latest 60-minute record generated at or before the cutoff."""
    import nba_props_challenger_c as CC
    recs = []
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*.json.gz"), recursive=True):
            if "_60_" not in os.path.basename(p):
                continue
            try:
                r = json.load(gzip.open(p))
            except Exception:  # noqa: BLE001
                continue
            if r.get("params_id", "b") != "b" or r.get("horizon_min") != 60 or "players" not in r:
                continue
            cut = pd.Timestamp(r["cutoff_utc"])
            replay = isinstance(r.get("report"), dict) and r["report"].get("replay") is True
            # replay records (window 1) are dated by their replay time (run_utc); live records by when the forecast finished
            stamp = r.get("run_utc") if replay else r.get("forecast_finished_utc")
            if not stamp:
                raise ValueError(f"Forecast has no provable generation/completion timestamp: {p}")
            gen = pd.Timestamp(stamp)
            if gen.tzinfo is None or cut.tzinfo is None:
                raise ValueError(f"Forecast timestamps need explicit timezone: {p}")
            if gen > cut:
                continue
            recs.append((int(r["game_id"]), cut, gen, p, r))
    best = {}
    for gid, cut, gen, p, r in recs:
        if gid not in best or gen > best[gid][1]:
            best[gid] = (cut, gen, r)
    rows = []
    for gid, (cut, gen, r) in best.items():
        for pl in r["players"]:
            row = dict(game_id=gid, cutoff=cut, generated=gen, aid=int(pl["aid"]), name=pl.get("name"), team=pl.get("team"),
                       p_appear=pl.get("p_appear"),
                       em=CC.expected_minutes(pl["minutes_v2"]))
            for v, m in DIST.items():
                for s, k in m.items():
                    row[f"{s}_{v}"] = pl.get(k)
            rows.append(row)
    F = pd.DataFrame(rows)
    F["window"] = np.where(F.cutoff < WINDOW1_END, 1, 2)
    return F


def outcomes(seasons=(2026, 2027)):
    frames = []
    for y in seasons:
        p = os.path.join(ROOT, "data", "nba", f"player_box_{y}.csv")
        if not os.path.exists(p):
            continue
        b = pd.read_csv(p, low_memory=False, usecols=["game_id", "athlete_id", "minutes", "points", "rebounds", "assists", "season_type"])
        b = b[pd.to_numeric(b.season_type, errors="coerce") == 2]
        frames.append(b)
    B = pd.concat(frames, ignore_index=True)
    for c in ("game_id", "athlete_id", "minutes", "points", "rebounds", "assists"):
        B[c] = pd.to_numeric(B[c], errors="coerce")
    B = B.dropna(subset=["game_id", "athlete_id"])
    return B.rename(columns={"athlete_id": "aid", "points": "pts", "rebounds": "reb", "assists": "ast"}).astype({"game_id": int, "aid": int})


def fixture_map(P, F):
    """OddsPapi fixture -> ESPN game id by date and team names. Returns dict."""
    sch = []
    for y in (2026, 2027):
        p = os.path.join(ROOT, "data", "nba", f"nba_schedule_{y}.csv")
        if os.path.exists(p):
            s = pd.read_csv(p, low_memory=False)
            sch.append(s[["id", "game_date_time", "home_display_name", "away_display_name"]] if "home_display_name" in s else
                       s[["id", "game_date_time", "home_name", "away_name"]].rename(columns={"home_name": "home_display_name", "away_name": "away_display_name"}))
    S = pd.concat(sch, ignore_index=True)
    S["tip"] = pd.to_datetime(S.game_date_time, utc=True, errors="coerce")
    S["key"] = [frozenset((NM.norm(h), NM.norm(a))) for h, a in zip(S.home_display_name, S.away_display_name)]
    m = {}
    fx = P.drop_duplicates("fixture_id")[["fixture_id", "start_time", "home", "away"]]
    for r in fx.itertuples():
        t = pd.Timestamp(r.start_time)
        k = frozenset((NM.norm(r.home), NM.norm(r.away)))
        c = S[(S.key == k) & ((S.tip - t).abs() <= pd.Timedelta(hours=6))]
        if len(c) == 1:
            m[r.fixture_id] = int(c.id.iloc[0])
    return m


def assemble(prices_dir, dirs, with_outcomes):
    raw = pd.concat([pd.read_csv(p) for p in glob.glob(os.path.join(prices_dir, "*.csv.gz"))], ignore_index=True)
    # historical updates carry OddsPapi player ids only; names come from the live-odds name map (collector "names" mode)
    nmap_path = os.path.join(os.path.dirname(os.path.abspath(prices_dir)), "player_names.json")
    nmap = {str(k): v["name"] if isinstance(v, dict) else v
            for k, v in json.load(open(nmap_path)).items()} if os.path.exists(nmap_path) else {}
    # Amendment 8 fallback: SportsGameOdds identity matches, only for ids the live-odds map did not name
    sgo_path = os.path.join(os.path.dirname(nmap_path), "player_names_sgo.json")
    sgo = {str(k): v["name"] for k, v in json.load(open(sgo_path)).items()} if os.path.exists(sgo_path) else {}
    nmap = {k: v for k, v in nmap.items() if isinstance(v, str) and v.strip()}
    sgo = {k: v for k, v in sgo.items() if isinstance(v, str) and v.strip()}
    n_sgo = len(set(sgo) - set(nmap))
    nmap = {**sgo, **nmap}
    supplied = raw.get("player_name", pd.Series(index=raw.index, dtype="object"))
    resolved = raw.player_key.astype(str).map(nmap)
    raw["player_name"] = resolved.where(resolved.notna(), supplied)
    raw["player_name"] = raw.player_name.fillna("id:" + raw.player_key.astype(str))
    P = PT.prices_long(raw)
    F = forecasts(dirs)
    fmap = fixture_map(P, F)
    P["game_id"] = P.fixture_id.map(fmap)
    L = PT.devig(PT.main_lines(P[P.stat.isin(PT.PRIMARY_STATS)]))
    L["game_id"] = L.fixture_id.map(fmap)
    # name matching within each game
    aid = {}
    unmatched = 0
    for gid, g in L.dropna(subset=["game_id"]).groupby("game_id"):
        cand = F[F.game_id == int(gid)][["aid", "name"]].drop_duplicates()
        got, miss = NM.match(sorted(g.player_name.unique()), list(cand.itertuples(index=False, name=None)))
        unmatched += len(miss)
        for k, v in got.items():
            aid[(gid, k)] = v
    L["aid"] = [aid.get((g, n)) for g, n in zip(L.game_id, L.player_name)]
    matched_lines = L.dropna(subset=["game_id", "aid"]).astype({"game_id": int, "aid": int})
    if matched_lines.duplicated(["game_id", "aid", "stat"]).any():
        raise ValueError("Duplicate player/game/stat after identity resolution; reconcile aliases before scoring")
    D = matched_lines.merge(F, on=["game_id", "aid"], how="inner", validate="many_to_one")
    # Amendment 7: stored pmfs are unconditional (mass 1 - p_appear at zero); books void non-appearances, so the model's over
    # probability is taken from the appearing-conditional pmf. Challenger c (Amendment 6) recalibrates that conditional pmf.
    import nba_props_challenger_c as CC
    cmaps = json.load(open(CC.OUT))["maps"] if os.path.exists(CC.OUT) else None
    recs = D.to_dict("records")
    # Amendment 11: p_appear below 0.01 is excluded for every model (same rows) and counted
    low_pa = np.array([row["p_appear"] is not None and float(row["p_appear"]) < CC.PA_MIN for row in recs], dtype=bool)

    def _over(pmf, pa, ln, stat=None, em=None):
        if not isinstance(pmf, list) or (pa is not None and float(pa) < CC.PA_MIN):
            return np.nan
        c = CC.conditional(pmf, pa)
        return PT.p_over(c if cmaps is None or stat is None else CC.calibrated_conditional(c, em, stat, cmaps), ln)
    for v in DIST:
        D[f"model_over_{v}"] = [_over(row[f"{s}_{v}"], row["p_appear"], ln) for row, s, ln in zip(recs, D.stat, D.line)]
    if cmaps is not None:
        D["model_over_c"] = [_over(row[f"{s}_v2"], row["p_appear"], ln, s, row["em"]) for row, s, ln in zip(recs, D.stat, D.line)]
    excluded_low_pa = int(low_pa.sum())
    tip = D.fixture_id.map(P.drop_duplicates("fixture_id").set_index("fixture_id").start_time)
    D["date"] = pd.to_datetime(tip, utc=True).dt.tz_convert("America/New_York").dt.date.astype(str)
    unknown_participation_lines = None
    unknown_participation_player_games = None
    if with_outcomes:
        O = outcomes()
        D = D.merge(O[["game_id", "aid", "minutes", "pts", "reb", "ast"]], on=["game_id", "aid"], how="left", validate="many_to_one")
        unknown = ~(D.minutes > 0)
        unknown_participation_lines = int(unknown.sum())
        unknown_participation_player_games = int(D.loc[unknown, ["game_id", "aid"]].drop_duplicates().shape[0])
        D = D[~unknown].copy()
        D["actual"] = [r[s] for r, s in zip(D[["pts", "reb", "ast"]].to_dict("records"), D.stat)]
        if D.actual.isna().any():
            raise ValueError("Missing played-player outcome: cannot settle as under")
        D["over"] = (D.actual > D.line).astype(int)
    meta = dict(price_rows=len(raw), fixtures=int(P.fixture_id.nunique()), fixtures_mapped=len(fmap), main_lines=len(L),
                lines_with_game=int(L.game_id.notna().sum()), names_unmatched=int(unmatched), joined=len(D),
                lines_without_player_name=int(L.player_name.astype(str).str.startswith("id:").sum()) if len(L) else 0)
    priced_player_games = L[["fixture_id", "player_name"]].drop_duplicates()
    matched_player_games = L.dropna(subset=["game_id", "aid"])[["fixture_id", "player_name"]].drop_duplicates()
    meta["priced_player_games"] = len(priced_player_games)
    meta["matched_player_games"] = len(matched_player_games)
    meta["name_match_rate"] = len(matched_player_games) / max(len(priced_player_games), 1)
    # Amendment 14 items 5 and 6: match rate by stat (and book when present), and coverage by month of the regular season
    meta["name_match_by_stat"] = {s_: float(g.dropna(subset=["game_id", "aid"])[["fixture_id", "player_name"]].drop_duplicates().shape[0]
                                            / max(g[["fixture_id", "player_name"]].drop_duplicates().shape[0], 1))
                                  for s_, g in L.groupby("stat")} if "stat" in L else {}
    meta["name_match_by_book"] = {b_: float(g.dropna(subset=["game_id", "aid"])[["fixture_id", "player_name"]].drop_duplicates().shape[0]
                                            / max(g[["fixture_id", "player_name"]].drop_duplicates().shape[0], 1))
                                  for b_, g in L.groupby("bookmaker")} if "bookmaker" in L else {}
    try:
        sch = pd.read_csv(os.path.join(ROOT, "data", "nba", "nba_schedule_2026.csv"), low_memory=False)
        sch = sch[pd.to_numeric(sch.season_type, errors="coerce") == 2]
        sch["t"] = pd.to_datetime(sch["game_date_time"] if "game_date_time" in sch else sch["date"], utc=True, errors="coerce")
        lo = pd.to_datetime(P.start_time, utc=True).min()
        sch = sch[sch.t >= lo]
        got = set(pd.to_numeric(L.game_id.dropna(), errors="coerce").dropna().astype(int))
        sch["has_price"] = pd.to_numeric(sch.id, errors="coerce").isin(got)
        meta["coverage_by_month"] = {str(k): [int(v.has_price.sum()), int(len(v))] for k, v in sch.groupby(sch.t.dt.strftime("%Y-%m"))}
    except Exception as ex:
        meta["coverage_by_month"] = f"not computed: {ex}"
    meta["ids_named_by_sgo_fallback"] = n_sgo
    meta["excluded_low_appearance_lines"] = excluded_low_pa
    meta["unknown_participation_lines"] = unknown_participation_lines
    meta["unknown_participation_player_games"] = unknown_participation_player_games
    return P, L, D, meta


def mechanics(args):
    P, L, D, meta = assemble(args.prices, [d for d in (args.w1, args.w2) if d], with_outcomes=False)
    cov = {}
    for (b, s), g in P[P.stat.isin(PT.PRIMARY_STATS)].groupby(["bookmaker", "stat"]):
        cov[f"{b}/{s}"] = dict(rows=len(g), with_entry_price=float(g.t60_price.notna().mean()), with_close=float(g.close_price.notna().mean()))
    late = P[pd.to_datetime(P.t60_time, utc=True, errors="coerce") > pd.to_datetime(P.start_time, utc=True) - pd.Timedelta(minutes=60)]
    match_rate = meta["name_match_rate"]
    lq = dict(lines=len(L), primary_two_books=float(L.primary.mean()) if len(L) else None,
              close_complete=float(L.close_complete.mean()) if len(L) else None,
              books_per_line=L.books.value_counts().sort_index().to_dict() if len(L) else {})
    out = dict(meta, coverage=cov, line_quality=lq, entry_prices_after_entry_time=len(late), name_match_rate_approx=round(match_rate, 4),
               forecasts_after_cutoff=int((D.generated > D.cutoff).sum()) if "generated" in D else None,
               by_window=D.groupby("window").size().to_dict() if len(D) else {}, by_stat=D.groupby("stat").size().to_dict() if len(D) else {})
    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open(args.out or os.path.join(HERE, "nba_props_price_mechanics.json"), "w"), indent=1, default=str)


def _blend_w1_on_w2(X):
    """Blend fitted on window 1 only, applied unchanged to window 2: log losses of market, model and blend on window 2."""
    A, B = X[X.window == 1], X[X.window == 2]
    if len(A) < 50 or len(B) < 50:
        return None
    XA = np.column_stack([PT._logit(A.market_over), PT._logit(A.model_over)])
    b, st = PT.logistic(XA, A.over.to_numpy(float))
    if b is None:
        return {"fit_status": st}
    mu, sd = XA.mean(axis=0), XA.std(axis=0)
    XB = (np.column_stack([PT._logit(B.market_over), PT._logit(B.model_over)]) - mu) / sd
    pb = 1 / (1 + np.exp(-(b[0] + XB @ b[1:])))
    ll = lambda p: float(-np.mean(B.over * np.log(np.clip(p, 1e-6, 1)) + (1 - B.over) * np.log(np.clip(1 - p, 1e-6, 1))))
    return {"fit_status": st, "n_w2": int(len(B)), "logloss_market": ll(B.market_over), "logloss_model": ll(B.model_over), "logloss_blend": ll(pb)}


def _gate(ok, assessable):
    return "pass" if assessable and ok else "insufficient" if not assessable else "fail"


def _evaluate(X, col):
    """Gates G1-G3 for one model column on the primary rows X (same rows for every model)."""
    r = {}
    probabilities = pd.to_numeric(X[col], errors="coerce")
    values = probabilities.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("Missing/invalid model probabilities: paired scoring cannot change rows by model")
    Xm = X.assign(model_over=probabilities).reset_index(drop=True)
    r["n"] = int(len(Xm))
    r["info_pooled"] = PT.info_test(Xm)
    r["info_by_window"] = {int(w): PT.info_test(Xm[Xm.window == w].reset_index(drop=True)) if (Xm.window == w).sum() > 0
                           else {"n": int((Xm.window == w).sum()), "assessable": False} for w in (1, 2)}
    r["blend_w1_on_w2"] = _blend_w1_on_w2(Xm)
    for thr in (0.03, 0.05, 0.10):
        B = PT.bets(Xm, thr)
        r[f"bets_{int(thr * 100)}"] = {"pooled": PT.clv_summary(B), "by_window": {int(w): PT.clv_summary(B[B.window == w]) for w in (1, 2)}}
    ip, iw = r["info_pooled"], r["info_by_window"]
    g1_ass = ip["assessable"] and all(v.get("assessable") for v in iw.values())
    g1 = _gate(g1_ass and ip["lb90"] > 0 and all(v["model_coef"] > 0 for v in iw.values()), g1_ass)
    b5 = r["bets_5"]["pooled"]
    g2_ass = b5.get("n", 0) >= 200 and b5.get("dates", 0) >= 20 and b5.get("close_coverage_ok", False)   # Amendment 14 item 2
    g2 = _gate(g2_ass and b5.get("clv_lb90", -1) > 0, g2_ass)
    bw = r["bets_5"]["by_window"]
    g3_ass = all(v.get("n", 0) >= 50 for v in bw.values())
    g3 = _gate(g3_ass and all(v.get("clv_mean", -1) > 0 for v in bw.values()), g3_ass)
    gates = {"G1": g1, "G2": g2, "G3": g3}
    gates["result"] = "pass" if all(v == "pass" for v in gates.values()) else "fail" if "fail" in gates.values() else "insufficient"
    r["gates"] = gates
    return r


def manifest(args):
    """Amendment 14 item 7: hashes that pin the rule, models, code, price files and window archives used for this run."""
    import hashlib
    def sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    fixed = {"rule": "research/NBA_PROPS_PRICE_TEST_RULE.md", "params_b": "model/nba_props_live_params_2026b.json",
             "challenger_c2": "model/nba_props_challenger_c.json", "points_dispersion": "model/nba_points_d_params_2026.json",
             "price_test_code": "research/nba_props_price_test.py", "runner_code": "research/nba_props_price_run.py",
             "challenger_code": "research/nba_props_challenger_c.py", "live_core_code": "research/nba_props_live_core.py"}
    out = {k: (sha(os.path.join(ROOT, v)) if os.path.exists(os.path.join(ROOT, v)) else None) for k, v in fixed.items()}
    def tree(d):
        files = sorted(os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs) if d and os.path.isdir(d) else []
        listing = "\n".join(f"{os.path.relpath(p, d)}\t{os.path.getsize(p)}" for p in files)
        return {"files": len(files), "listing_sha256": hashlib.sha256(listing.encode()).hexdigest()}
    out["prices_dir"] = {**tree(args.prices), "content_sha256": hashlib.sha256("".join(sha(p) for p in sorted(
        os.path.join(r, f) for r, _, fs in os.walk(args.prices) for f in fs if f.endswith(".gz"))).encode()).hexdigest()} if args.prices and os.path.isdir(args.prices) else None
    out["window1_dir"], out["window2_dir"] = tree(args.w1), tree(args.w2)
    out["window_bounds"] = "window 1: 1 Jan 2026 to end of 2025-26 regular season; window 2: 2026-27 regular season from activation (rule v1)"
    return out


def score(args):
    """Amendment 2 gates for the frozen model (primary, v2) and challenger c (secondary, Amendment 6), on the same rows."""
    import nba_props_challenger_c as CC
    if not os.path.isfile(CC.OUT):
        raise ValueError("Registered challenger file missing; stop before prices or outcomes are opened")
    P, L, D, meta = assemble(args.prices, [d for d in (args.w1, args.w2) if d], with_outcomes=True)
    if meta["name_match_rate"] < 0.95:
        raise ValueError("Mechanics failed: fewer than 95% of priced player-games matched")
    low = {k: v for k, v in {**meta.get("name_match_by_stat", {}), **meta.get("name_match_by_book", {})}.items() if v < 0.90}
    if low:
        raise ValueError(f"Amendment 14 item 5: match rate below 90% in a stratum {low}; explain in an amendment before scoring")
    if "model_over_c" not in D:
        raise ValueError("Challenger c is registered (Amendment 6) but model/nba_props_challenger_c.json is missing")
    res = {"meta": meta, "stats": {}}
    empty = {"G1": "insufficient", "G2": "insufficient", "G3": "insufficient", "result": "insufficient"}
    for s in PT.PRIMARY_STATS:
        A = D[D.stat == s].dropna(subset=["model_over_v2", "market_over"]).reset_index(drop=True)
        X = A[A.primary].reset_index(drop=True)
        r = {"n_priced_lines_all": int(len(A)), "n_primary": int(len(X)), "n_one_book_only": int((~A.primary).sum())}
        if X.empty:
            r["gates"], r["challenger_c"] = empty, {"gates": empty}
            res["stats"][s] = r
            continue
        challenger = pd.to_numeric(X.model_over_c, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        if not np.isfinite(challenger).all() or (challenger < 0).any() or (challenger > 1).any():
            raise ValueError("Challenger unavailable on frozen-model primary rows; cannot score different cohorts")
        r.update(_evaluate(X, "model_over_v2"))
        r["mean_model_minus_market_over"] = float((pd.to_numeric(X.model_over_v2) - pd.to_numeric(X.market_over)).mean())   # Amendment 14 item 8
        r["expected_minutes_tiers"] = {k: int(v) for k, v in pd.cut(pd.to_numeric(X.em, errors="coerce"), [-1, 15, 25, 100], labels=["<=15", "15-25", ">25"]).value_counts().items()} if "em" in X else None
        r["challenger_c"] = _evaluate(X, "model_over_c")
        r["reported_v3_info"] = PT.info_test(X.assign(model_over=X.model_over_v3).dropna(subset=["model_over"]).reset_index(drop=True))
        pin = A.dropna(subset=["pinnacle_over"]).assign(market_over=lambda x: x.pinnacle_over, model_over=lambda x: x.model_over_v2)
        r["pinnacle_only_info"] = PT.info_test(pin.reset_index(drop=True)) if len(pin) >= 50 else None
        res["stats"][s] = r
    res["manifest"] = manifest(args)   # Amendment 14 item 7
    json.dump(res, open(args.out or os.path.join(HERE, "nba_props_price_results.json"), "w"), indent=1, default=str)
    print(json.dumps({s: {"b": v.get("gates"), "c": v.get("challenger_c", {}).get("gates")} for s, v in res["stats"].items()}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--prices")
    ap.add_argument("--w1")
    ap.add_argument("--w2")
    ap.add_argument("--out")
    a = ap.parse_args()
    {"export-w2": lambda: export_w2(a.dest), "mechanics": lambda: mechanics(a), "score": lambda: score(a)}[a.mode]()
