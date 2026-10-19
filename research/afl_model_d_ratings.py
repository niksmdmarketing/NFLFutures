"""Team ratings of AFL model D (research/AFL_THREE_WAY_RULE.md), for the live site. Reads the clean Wheelo tables (never committed) and writes
only derived team ratings to pipeline/afl_model_d_ratings.json.

D's predicted margin is linear in per-team quantities, so it can be written as  margin = home_term + rating[home] - rating[away]  with
  rating(t) = wA * rA(t) + wB * sum_j b_j * r_j(t) / sd_j + wC * beta_C * S(t)      (then centred to mean 0)
  home_term = h_D - wB * sum_j b_j * mu_j / sd_j
where rA is the live srs rating, r_j the opponent-adjusted stat ratings, S(t) the summed player ratings of the team's previous-match lineup.
Usage:
  python afl_model_d_ratings.py <clean_dir> --check            (rebuild ratings before past rounds and compare with the test's D predictions)
  python afl_model_d_ratings.py <clean_dir> --preseason 2027   (ratings before round 0 of that season: all games through the previous season)
  python afl_model_d_ratings.py <clean_dir> --before 2027 5    (in-season: ratings before round 5 of 2027)
  python afl_model_d_ratings.py <clean_dir> --auto 2027         (weekly job: pre-season, or before the round after the latest one in the data)
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

import afl_three_way_test as TW

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline", "afl_model_d_ratings.json")
CODES = {"Adelaide": "ADE", "Brisbane": "BRI", "Carlton": "CAR", "Collingwood": "COL", "Essendon": "ESS", "Fremantle": "FRE", "Geelong": "GEE",
         "Gold Coast": "GCS", "Greater Western Sydney": "GWS", "Hawthorn": "HAW", "Melbourne": "MEL", "North Melbourne": "NTH", "Port Adelaide": "PTA",
         "Richmond": "RIC", "St Kilda": "STK", "Sydney": "SYD", "West Coast": "WCE", "Western Bulldogs": "WBD"}


def fitted(clean):
    """frozen D parameters, re-derived exactly as in the test (fit on 2013-2018 only)."""
    M, res, ex = TW.predictions(clean)
    tu = ex["tu"]
    feats = ["b_" + s for s in TW.STATS]
    mu, sdv = M.loc[tu, feats].mean(), M.loc[tu, feats].std()
    return M, res, ex, mu, sdv


def ratings_before(clean_M, T, P, season, rnd, par):
    """ratings using only games strictly before (season, rnd)."""
    M = clean_M
    past_all = M[(M.season < season) | ((M.season == season) & (M["round"] < rnd))]
    # A and B: replay season by season (same as the test machinery)
    def rating_series(ycol, free_home):
        end, ha_prev = {}, 0.0
        cur = None
        for yr in sorted(past_all.season.unique()):
            s = past_all[past_all.season == yr]
            prior = {t: TW.PRIOR_REG * v for t, v in end.items()}
            if yr == season:
                cur = TW.srs(s.home, s.away, ycol(s), prior, TW.K_PRIOR, free_home)[0] if len(s) else prior
            else:
                end, _ = TW.srs(s.home, s.away, ycol(s), None, 8.0, free_home)
        if cur is None:                          # pre-season: no games yet this season
            cur = {t: TW.PRIOR_REG * v for t, v in end.items()}
        return cur
    rA = rating_series(lambda g: (g.home_score - g.away_score).to_numpy(float), False)
    ht = T[T.is_home == 1].set_index("MatchId")
    at = T[T.is_home == 0].set_index("MatchId")
    rB = {}
    for st in TW.STATS:
        dm = (ht[st] - at[st]).to_dict()
        rB[st] = rating_series(lambda g, dm=dm: g.match_id.map(dm).fillna(0).to_numpy(float), True)
    # C: player ratings after every game before (season, rnd); lineup = each team's last match
    Pp = P.merge(past_all[["match_id"]].rename(columns={"match_id": "MatchId"}), on="MatchId")
    Pp = Pp.sort_values(["season", "round"])
    Pp["v"] = Pp.RatingPoints * np.where(Pp.season == 2020, 1.25, 1.0)
    d = 0.5 ** (1.0 / par["H"])
    S, W = {}, {}
    for (_, _), g in Pp.groupby(["season", "round"], sort=True):
        for pid, v in zip(g.WebsiteId, g.v):
            S[pid] = S.get(pid, 0.0) * d + v
            W[pid] = W.get(pid, 0.0) * d + 1.0
    last = Pp.sort_values(["season", "round"]).groupby("Team").tail(23)
    lastmatch = Pp.sort_values(["season", "round"]).groupby("Team").MatchId.last()
    strength = {}
    for team, mid in lastmatch.items():
        ids = Pp[(Pp.MatchId == mid) & (Pp.Team == team)].WebsiteId
        strength[team] = sum((S.get(p, 0) + par["n0"] * par["R"]) / (W.get(p, 0) + par["n0"]) for p in ids)
    teams = sorted(CODES)
    b = par["bB"][1:]
    raw = {t: par["wA"] * rA.get(t, 0.0) + par["wB"] * sum(bj * rB[st].get(t, 0.0) / par["sd"][st] for bj, st in zip(b, TW.STATS))
           + par["wC"] * par["betaC"] * strength.get(t, 0.0) for t in teams}
    m = np.mean(list(raw.values()))
    return {t: raw[t] - m for t in teams}


def params(res, ex, mu, sdv):
    return {"wA": res["D"]["wA"], "wB": res["D"]["wB"], "wC": res["D"]["wC"], "hD": res["D"]["h"], "bB": ex["bB"], "betaC": res["C"]["beta"],
            "H": res["C"]["H"], "n0": res["C"]["n0"], "R": res["C"]["R"], "sd": {s: sdv["b_" + s] for s in TW.STATS}, "mu": {s: mu["b_" + s] for s in TW.STATS}}


def home_term(par):
    return par["hD"] - par["wB"] * sum(bj * par["mu"][s] / par["sd"][s] for bj, s in zip(par["bB"][1:], TW.STATS))


def main():
    clean = sys.argv[1]
    M, res, ex, mu, sdv = fitted(clean)
    T = pd.read_csv(f"{clean}/afl_team_stats.csv")
    pp = f"{clean}/afl_player_stats.csv.gz" if os.path.exists(f"{clean}/afl_player_stats.csv.gz") else f"{clean}/afl_player_stats.csv"
    P = pd.read_csv(pp, usecols=["season", "round", "MatchId", "Team", "WebsiteId", "RatingPoints"])
    P["MatchId"] = P.MatchId.astype(str)
    M["match_id"] = M.match_id.astype(str)
    T["MatchId"] = T.MatchId.astype(str)
    par = params(res, ex, mu, sdv)
    hd = home_term(par)
    if "--check" in sys.argv:
        out = []
        for season, rnd in [(2019, 1), (2022, 10), (2026, 5), (2026, 20)]:
            r = ratings_before(M, T, P, season, rnd, par)
            g = M[(M.season == season) & (M["round"] == rnd)]
            for x in g.itertuples():
                out.append((season, rnd, x.home, x.away, round(hd + r[x.home] - r[x.away], 3), round(x.D, 3)))
        df = pd.DataFrame(out, columns=["season", "round", "home", "away", "from_ratings", "test_D"])
        print(df.to_string())
        print("max abs diff", float((df.from_ratings - df.test_D).abs().max()))
        return
    if "--auto" in sys.argv:                 # weekly refresh: pre-season if no games of that season yet, else before the next round
        season = int(sys.argv[sys.argv.index("--auto") + 1])
        played = M[M.season == season]
        rnd = int(played["round"].max()) + 1 if len(played) else -1
    elif "--preseason" in sys.argv:
        season, rnd = int(sys.argv[sys.argv.index("--preseason") + 1]), -1
    else:
        i = sys.argv.index("--before")
        season, rnd = int(sys.argv[i + 1]), int(sys.argv[i + 2])
    r = ratings_before(M, T, P, season, rnd, par)
    last = M[(M.season < season) | ((M.season == season) & (M["round"] < rnd))].sort_values(["season", "round"]).iloc[-1]
    doc = {"model": "AFL model D (team stats + players), research/AFL_THREE_WAY_RULE.md", "season": season, "before_round": rnd if rnd >= 0 else "pre-season",
           "data_through": {"season": int(last.season), "round": int(last["round"]), "round_name": last.round_name, "date": str(last.date)[:10]},
           "rounds_played_this_season": int(M[(M.season == season) & (M["round"] < max(rnd, 0))]["round"].nunique()),
           "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "home_term": round(hd, 3),
           "ratings": {CODES[t]: round(v, 3) for t, v in sorted(r.items(), key=lambda kv: -kv[1])}}
    json.dump(doc, open(OUT, "w"), indent=1)
    print(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main()
