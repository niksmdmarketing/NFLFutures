"""NFL non-QB injury layer, Stage 1 (research/NFL_NONQB_INJURY_RULE.md). Read-only research.
Builds per-game missing-starter features (2014-2025), fits on 2014-2021, tests on 2022-2025 against the frozen v4 base.
Writes research/nfl_nonqb_injury_results.json and data/research/nfl_nonqb_injury_features.csv.gz.
Usage: python research/nfl_nonqb_injury_test.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import ratings  # noqa: E402
from common import FIX, download, games  # noqa: E402

YEARS = range(2014, 2026)
GROUPS = {"OL": {"T", "G", "C", "OT", "OG", "OL", "LT", "RT", "LG", "RG"}, "DL": {"DE", "DT", "NT", "OLB", "EDGE", "DL"}, "LB": {"ILB", "MLB", "LB"},
          "CB": {"CB"}, "S": {"S", "FS", "SS", "DB", "SAF"}, "WR": {"WR"}, "TE": {"TE"}, "RB": {"RB", "FB"}}
EXCLUDE = {"QB", "K", "P", "LS"}
G = list(GROUPS)
SUFFIX = "_reportonly" if os.environ.get("INJ_REPORT_ONLY") == "1" else ""
OUT_CSV = os.path.join(ROOT, "data", "research", f"nfl_nonqb_injury_features{SUFFIX}.csv.gz")
RES = os.path.join(ROOT, "research", f"nfl_nonqb_injury_results{SUFFIX}.json")


_PL = pd.read_csv(download("players/players.csv", max_age_h=24 * 30), low_memory=False)
PFR2GSIS = _PL.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id.to_dict()
PLAYER_POS = _PL.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id").set_index("gsis_id").position.to_dict()


def group(pos):
    for g, s in GROUPS.items():
        if pos in s:
            return g
    return None


def load(rel, y):
    p = download(f"{rel}_{y}.csv", max_age_h=24 * 365, required=False)
    return pd.read_csv(p, low_memory=False) if p else pd.DataFrame()


def fix(s):
    return s.replace(FIX)


def season_features(y):
    sn = load("snap_counts/snap_counts", y)
    inj = load("injuries/injuries", y)
    ro = load("weekly_rosters/roster_weekly", y)
    sn = sn[sn.game_type == "REG"].copy(); inj = inj[inj.game_type == "REG"].copy(); ro = ro[ro.game_type == "REG"].copy()
    for d in (sn, inj, ro):
        d["team"] = fix(d["team"].astype(str))
    pfr2gsis = {**ro.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id.to_dict(), **PFR2GSIS}
    sn["gsis_id"] = sn.pfr_player_id.map(pfr2gsis)
    sn["share"] = np.fmax(pd.to_numeric(sn.offense_pct, errors="coerce").fillna(0), pd.to_numeric(sn.defense_pct, errors="coerce").fillna(0))
    if sn.share.max() > 1.5:
        sn["share"] = sn.share / 100.0
    sn = sn.dropna(subset=["gsis_id"])
    played = sn[(sn.offense_snaps.fillna(0) + sn.defense_snaps.fillna(0)) > 0]
    ro["pos2"] = ro["depth_chart_position"].where(ro["depth_chart_position"].notna() & (ro["depth_chart_position"].astype(str) != ""), ro.gsis_id.map(PLAYER_POS)) if "depth_chart_position" in ro else ro.gsis_id.map(PLAYER_POS)
    ro["pos2"] = ro["pos2"].fillna(ro["position"])
    pos = ro.dropna(subset=["gsis_id"]).set_index(["week", "team", "gsis_id"]).pos2
    pos = pos[~pos.index.duplicated()]
    out = {}
    inj_out = inj[inj.report_status.isin(["Out", "Doubtful"])]
    for (t, w), _ in ro.groupby(["team", "week"]):
        if w < 2:
            continue
        prior = played[(played.team == t) & (played.week < w)]
        imp = prior.groupby("gsis_id").share.agg(["mean", "size"])
        imp = imp[imp["size"] >= 2]["mean"]
        if imp.empty:
            continue
        miss = set(inj_out[(inj_out.team == t) & (inj_out.week == w)].gsis_id.dropna())
        rw = ro[(ro.team == t) & (ro.week == w)]
        if os.environ.get("INJ_REPORT_ONLY") != "1":      # sensitivity: final injury report only (no roster status)
            miss |= set(rw[rw.status.astype(str) != "ACT"].gsis_id.dropna())
        feats = dict.fromkeys(G, 0.0)
        names = []
        for p in miss:
            if p not in imp.index:
                continue
            ps = pos.get((w, t, p))
            if ps is None:
                rows = ro[(ro.gsis_id == p)]
                ps = rows.pos2.iloc[-1] if len(rows) else PLAYER_POS.get(p)
            if ps is None or ps in EXCLUDE:
                continue
            g = group(str(ps))
            if g:
                feats[g] += float(imp[p])
                names.append(p)
        out[(t, int(w))] = feats
    return out


def build():
    if os.path.exists(OUT_CSV):
        return pd.read_csv(OUT_CSV)
    rows = []
    for y in YEARS:
        f = season_features(y)
        for (t, w), v in f.items():
            rows.append({"season": y, "week": w, "team": t, **v})
        print(y, len(f), flush=True)
    D = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    D.to_csv(OUT_CSV, index=False)
    return D


def game_rows():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows = []
    for y in range(2010, 2026):          # same order as nfl_walkforward_weights.build
        reg = g[(g.season == y) & (g.game_type == "REG")]
        for w in sorted(reg.week.unique()):
            for r in reg[reg.week == w].itertuples():
                if pd.isna(r.result):
                    continue
                rows.append((y, int(w), r.home_team, r.away_team, float(r.result), float(r.spread_line) if pd.notna(r.spread_line) else np.nan))
    return pd.DataFrame(rows, columns=["season", "week", "home", "away", "result", "spread"])


if __name__ == "__main__":
    F = build().set_index(["season", "week", "team"])
    d = np.load(os.path.join(ROOT, "data", "research", "nfl_wf_features.npz"))
    meta = game_rows()
    assert len(meta) == len(d["y"]) and np.allclose(meta.result.values, d["y"])
    coef = np.array([ratings.P["coef"][c] for c in ratings.P["cols"]])
    meta["pred"] = d["X"] @ coef + ratings.P["intercept"]
    for g in G:
        hv = [F[g].get((s, w, h), np.nan) for s, w, h in zip(meta.season, meta.week, meta.home)]
        av = [F[g].get((s, w, a), np.nan) for s, w, a in zip(meta.season, meta.week, meta.away)]
        meta["d_" + g] = np.array(hv, float) - np.array(av, float)
    cols = ["d_" + g for g in G]
    M = meta[(meta.season >= 2014) & (meta.week >= 2)].dropna(subset=cols).copy()
    M["resid"] = M.result - M.pred
    tr, te = M[M.season <= 2021], M[M.season >= 2022]
    X, y = tr[cols].values, tr.resid.values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * (res @ res) / (len(y) - len(beta)))
    tot_tr, tot_te = tr[cols].sum(1).values, te[cols].sum(1).values
    b_pool = float(tot_tr @ tr.resid.values / (tot_tr @ tot_tr))
    out = {"fit_games": len(tr), "test_games": len(te), "coverage_2014_2025": round(len(M) / len(meta[(meta.season >= 2014) & (meta.week >= 2)]), 3),
           "beta": dict(zip(G, beta.round(3).tolist())), "t": dict(zip(G, (beta / se).round(2).tolist())), "beta_pooled": round(b_pool, 3),
           "feature_mean_abs_test": dict(zip(G, te[cols].abs().mean().round(3).tolist()))}
    def score(pred, df):
        r = df.result.values - pred
        win = (df.result.values > 0).astype(float); keep = df.result.values != 0
        p = norm.cdf(pred / 13.4).clip(1e-6, 1 - 1e-6)
        return float(np.sqrt(np.mean(r ** 2))), float(-np.mean((win * np.log(p) + (1 - win) * np.log(1 - p))[keep]))
    base = te.pred.values; inj = base + te[cols].values @ beta; pool = base + tot_te * b_pool
    for name, pr in (("baseline", base), ("injury", inj), ("pooled", pool)):
        rm, ll = score(pr, te)
        out[name] = {"rmse": round(rm, 4), "logloss": round(ll, 5),
                     "rmse_by_season": {int(s): round(float(np.sqrt(np.mean((te.result.values[te.season.values == s] - pr[te.season.values == s]) ** 2))), 4) for s in range(2022, 2026)}}
    ok = np.isfinite(te.spread.values)
    from sklearn.linear_model import LinearRegression
    for name, pr in (("baseline", base), ("injury", inj)):
        b = LinearRegression().fit(np.column_stack([pr[ok], te.spread.values[ok]]), te.result.values[ok])
        out[name]["blend_with_close"] = {"model": round(float(b.coef_[0]), 3), "spread": round(float(b.coef_[1]), 3)}
    out["close_rmse"] = round(float(np.sqrt(np.mean((te.result.values[ok] - te.spread.values[ok]) ** 2))), 4)
    better = sum(out["injury"]["rmse_by_season"][s] < out["baseline"]["rmse_by_season"][s] for s in range(2022, 2026))
    signs = all(b < 0 for b, t in zip(beta, beta / se) if abs(t) > 2)    # home missing more -> lower home margin
    out["gates"] = {"rmse_lower": out["injury"]["rmse"] < out["baseline"]["rmse"], "seasons_better": better,
                    "logloss_lower": out["injury"]["logloss"] < out["baseline"]["logloss"], "signs_ok": signs}
    out["stage1_pass"] = bool(out["gates"]["rmse_lower"] and better >= 3 and out["gates"]["logloss_lower"] and signs)
    json.dump(out, open(RES, "w"), indent=1)
    print(json.dumps(out, indent=1))


def futures_missing(y):
    """Stage 2 (amendment): (week w, team) -> {group: missing share} for players known out after week w's games, from the week-w
    roster: status neither ACT nor INA, with at least 2 games of snaps through week w. QB/K/P/LS excluded."""
    sn = load("snap_counts/snap_counts", y)
    ro = load("weekly_rosters/roster_weekly", y)
    sn = sn[sn.game_type == "REG"].copy(); ro = ro[ro.game_type == "REG"].copy()
    for d in (sn, ro):
        d["team"] = fix(d["team"].astype(str))
    pfr2gsis = {**ro.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id.to_dict(), **PFR2GSIS}
    sn["gsis_id"] = sn.pfr_player_id.map(pfr2gsis)
    sn["share"] = np.fmax(pd.to_numeric(sn.offense_pct, errors="coerce").fillna(0), pd.to_numeric(sn.defense_pct, errors="coerce").fillna(0))
    if sn.share.max() > 1.5:
        sn["share"] = sn.share / 100.0
    played = sn.dropna(subset=["gsis_id"])
    played = played[(played.offense_snaps.fillna(0) + played.defense_snaps.fillna(0)) > 0]
    ro["pos2"] = ro["depth_chart_position"].where(ro["depth_chart_position"].notna() & (ro["depth_chart_position"].astype(str) != ""), ro.gsis_id.map(PLAYER_POS)) if "depth_chart_position" in ro else ro.gsis_id.map(PLAYER_POS)
    ro["pos2"] = ro["pos2"].fillna(ro["position"])
    out = {}
    for (t, w), rw in ro.groupby(["team", "week"]):
        prior = played[(played.team == t) & (played.week <= w)]
        imp = prior.groupby("gsis_id").share.agg(["mean", "size"])
        imp = imp[imp["size"] >= 2]["mean"]
        feats = dict.fromkeys(G, 0.0)
        for r in rw[~rw.status.astype(str).isin(["ACT", "INA"])].itertuples():
            if r.gsis_id in imp.index and str(r.pos2) not in EXCLUDE:
                g = group(str(r.pos2))
                if g:
                    feats[g] += float(imp[r.gsis_id])
        out[(int(w), t)] = feats
    return out
