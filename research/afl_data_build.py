"""Build clean AFL tables from Wheelo match_stats round files (2012-2026). Code only: the raw files and the outputs are Wheelo data and stay
on the user's computer (never committed).
Usage: python afl_data_build.py <match_stats_dir> <out_dir>
Outputs (CSV):
  afl_matches.csv        one row per match: season, round, round_name, phase (opening/regular/finals), match_id, date, home, away, scores, xScores
  afl_team_stats.csv     one row per team per match: every TeamData column + is_home, opponent, margin
  afl_player_stats.csv   one row per player per match: every Data column + season, round, is_home, opponent
  afl_build_report.json  checks (counts, duplicates, missing values, players per team, score cross-checks)
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def frame(block):
    """Wheelo blocks are [ {col: [values]} ] for multi-row tables and [ {col: value} ] for one-row tables (e.g. a grand final)."""
    if not block:
        return pd.DataFrame()
    b = block[0]
    if all(isinstance(v, list) for v in b.values()):
        return pd.DataFrame(b)
    return pd.DataFrame([b])


def phase(name):
    n = name.lower()
    if n.startswith("opening"):
        return "opening"
    if n.startswith("round"):
        return "regular"
    return "finals"


def build(src, out):
    os.makedirs(out, exist_ok=True)
    M, T, P, skipped = [], [], [], []
    for p in sorted(glob.glob(os.path.join(src, "*.json"))):
        base = os.path.basename(p)
        if len(base) != 11:                       # only YYYYRR.json round files (e.g. a stray 2025.json metrics file is ignored)
            skipped.append(base)
            continue
        d = json.load(open(p, encoding="utf-8"))
        if not {"Data", "TeamData", "Matches", "Summary"} <= set(d):
            skipped.append(base)
            continue
        s = d["Summary"][0]
        season, rnd, rname = int(s["Season"]), int(s["RoundNumber"]), s["RoundName"]
        m, td, pl = frame(d["Matches"]), frame(d["TeamData"]), frame(d["Data"])
        for x in (m, td, pl):
            x.insert(0, "season", season)
            x.insert(1, "round", rnd)
            x.insert(2, "round_name", rname)
            x.insert(3, "phase", phase(rname))
            x.insert(4, "file", base)
        M.append(m)
        T.append(td)
        P.append(pl)
    m = pd.concat(M, ignore_index=True)
    t = pd.concat(T, ignore_index=True)
    pl = pd.concat(P, ignore_index=True)
    for x in (m, t, pl):
        x["MatchId"] = x["MatchId"].astype(str)
        for c in x.columns:
            if c not in ("MatchId",) and x[c].dtype == object:
                num = pd.to_numeric(x[c].replace({"NA": np.nan, "": np.nan}), errors="coerce")
                if num.notna().sum() >= 0.9 * x[c].replace({"NA": np.nan, "": np.nan}).notna().sum() and num.notna().any():
                    x[c] = num
    m = m.drop(columns=[c for c in m.columns if c.endswith("Image")])
    t = t.drop(columns=[c for c in t.columns if c.endswith("Image")])
    pl = pl.drop(columns=[c for c in pl.columns if c.endswith("Image")])

    # dates: "13 Mar" + season
    m["date"] = pd.to_datetime([f"{y}-{MONTHS[s.split()[1]]:02d}-{int(s.split()[0]):02d}" for y, s in zip(m.season, m.MatchDate)])
    # home/away and scores onto the team table
    side = pd.concat([m[["MatchId", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "Team", "AwayTeam": "opponent"}).assign(is_home=1),
                      m[["MatchId", "AwayTeam", "HomeTeam"]].rename(columns={"AwayTeam": "Team", "HomeTeam": "opponent"}).assign(is_home=0)])
    t = t.merge(side, on=["MatchId", "Team"], how="left")
    opp = t[["MatchId", "Team", "Score"]].rename(columns={"Team": "opponent", "Score": "opp_score"})
    t = t.merge(opp, on=["MatchId", "opponent"], how="left")
    t["margin"] = t.Score - t.opp_score
    t = t.merge(m[["MatchId", "date"]], on="MatchId", how="left")
    pl = pl.merge(side, on=["MatchId", "Team"], how="left").merge(m[["MatchId", "date"]], on="MatchId", how="left")

    h = t[t.is_home == 1].set_index("MatchId")
    a = t[t.is_home == 0].set_index("MatchId")
    mm = m[["season", "round", "round_name", "phase", "MatchId", "date", "HomeTeam", "AwayTeam"]].set_index("MatchId")
    mm["home_score"], mm["away_score"] = h.Score, a.Score
    mm["home_xscore"], mm["away_xscore"] = (h.xScore, a.xScore) if "xScore" in t else (np.nan, np.nan)
    mm = mm.reset_index().rename(columns={"MatchId": "match_id", "HomeTeam": "home", "AwayTeam": "away"})

    # checks
    rep = {"files_skipped": skipped, "matches": int(len(mm)), "matches_by_season": mm.groupby("season").size().to_dict(),
           "finals_by_season": mm[mm.phase == "finals"].groupby("season").size().to_dict(),
           "duplicate_match_ids": int(mm.match_id.duplicated().sum()), "team_rows_not_two": int((t.groupby("MatchId").size() != 2).sum()),
           "unmatched_team_side": int(t.is_home.isna().sum()), "unmatched_player_side": int(pl.is_home.isna().sum()),
           "missing_score": int(mm.home_score.isna().sum() + mm.away_score.isna().sum()),
           "xscore_present_by_season": mm.groupby("season").home_xscore.apply(lambda s: int(s.notna().sum())).to_dict(),
           "teams": sorted(set(mm.home) | set(mm.away))}
    per = pl.groupby(["MatchId", "Team"]).size()
    rep["players_per_team_match"] = {"min": int(per.min()), "max": int(per.max()), "share_22_or_23": round(float(per.isin([22, 23]).mean()), 4),
                                     "by_season_mean": pl.groupby(["season", "MatchId", "Team"]).size().groupby("season").mean().round(2).to_dict()}
    rep["player_id_column"] = "WebsiteId"
    rep["players_unique"] = int(pl.WebsiteId.nunique())
    rep["player_rows_missing_id"] = int(pl.WebsiteId.isna().sum())
    rep["dup_player_match"] = int(pl.duplicated(["MatchId", "WebsiteId"]).sum())
    names_per_id = pl.groupby("WebsiteId").Player.nunique()
    rep["ids_with_several_names"] = int((names_per_id > 1).sum())
    if "Goals" in pl and "Behinds" in pl:
        g = pl.groupby(["MatchId", "Team"])[["Goals", "Behinds"]].sum()
        pts = (6 * g.Goals + g.Behinds).rename("pts").reset_index()
        chk = t.merge(pts, on=["MatchId", "Team"], how="left")
        bad = chk[(chk.pts - chk.Score).abs() > 0]
        rep["player_goals_vs_team_score_mismatch"] = int(len(bad))   # rushed behinds are not credited to players, so small gaps are expected
        rep["mismatch_median_gap"] = float((chk.Score - chk.pts).median())
        rep["mismatch_max_gap"] = float((chk.Score - chk.pts).abs().max())
    tog = pl.groupby(["season"]).TimeOnGround.apply(lambda s: round(float(s.isna().mean()), 4)).to_dict() if "TimeOnGround" in pl else {}
    rep["player_tog_missing_share_by_season"] = tog
    cov = {c: pl.groupby("season")[c].apply(lambda s: round(float(s.notna().mean()), 3)).to_dict() for c in pl.columns if c not in ("season",)}
    rep["player_columns_full_coverage_from"] = {c: int(min([y for y, v in cv.items() if v > 0.95], default=0)) for c, cv in cov.items()}
    rep["team_columns"] = len(t.columns)
    rep["player_columns"] = len(pl.columns)

    mm.to_csv(os.path.join(out, "afl_matches.csv"), index=False)
    t.to_csv(os.path.join(out, "afl_team_stats.csv"), index=False)
    pl.to_csv(os.path.join(out, "afl_player_stats.csv"), index=False)
    json.dump(rep, open(os.path.join(out, "afl_build_report.json"), "w"), indent=1, default=str)
    return rep


if __name__ == "__main__":
    r = build(sys.argv[1], sys.argv[2])
    print(json.dumps({k: v for k, v in r.items() if k != "player_columns_full_coverage_from"}, indent=1, default=str))
