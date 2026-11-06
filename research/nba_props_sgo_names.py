"""Name fallback for research/NBA_PROPS_PRICE_TEST_RULE.md Amendment 8: OddsPapi player ids the live-odds map did not name are
matched to SportsGameOdds players through identical bookmaker lines in the same game. Lines identify players only; no price
value or result is read (OddsPapi rows are used only for which lines had a closing quote).

  python research/nba_props_sgo_names.py <oddspapi_nba_dir> <sgo_identity_dir>   -> <oddspapi_nba_dir>/player_names_sgo.json
  python research/nba_props_sgo_names.py selftest
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_props_price_test as PT   # noqa: E402

BOOKS = ("draftkings", "fanduel")
STAT_SGO = {"points": "pts", "rebounds": "reb", "assists": "ast"}
TIP_TOL = pd.Timedelta(minutes=15)
MIN_PAIRS, MIN_GAMES, AGREE = 2, 2, 0.8


def _team_key(name):
    import nba_teams
    return nba_teams.resolve(str(name)) or str(name).strip().lower()


def oddspapi_lines(O):
    """id, fixture, book, stat -> set of lines quoted with a closing quote (no price values kept)."""
    O = O[O.bookmaker.isin(BOOKS)].copy()
    O["stat"] = O.market_name.map(PT.stat_of)
    O = O[O.stat.isin(PT.PRIMARY_STATS) & O.close_price.notna()]
    O["line"] = pd.to_numeric(O.handicap, errors="coerce")
    O = O.dropna(subset=["line"])
    return O.groupby(["player_key", "fixture_id", "bookmaker", "stat"]).line.apply(lambda s: set(s.round(1))).to_dict()


def pair_games(O, S):
    """OddsPapi fixture -> SGO event: tip within 15 minutes and the same two teams."""
    fo = O.drop_duplicates("fixture_id")[["fixture_id", "start_time", "home", "away"]]
    fs = S.drop_duplicates("event_id")[["event_id", "start_time", "home", "away"]]
    fs = fs.assign(t=pd.to_datetime(fs.start_time, utc=True), k=[frozenset((_team_key(h), _team_key(a))) for h, a in zip(fs.home, fs.away)])
    out = {}
    for f, st, h, a in fo.itertuples(index=False):
        t, k = pd.Timestamp(st).tz_convert("UTC") if pd.Timestamp(st).tzinfo else pd.Timestamp(st, tz="UTC"), frozenset((_team_key(h), _team_key(a)))
        c = fs[(fs.k == k) & ((fs.t - t).abs() <= TIP_TOL)]
        if len(c) == 1:
            out[f] = c.event_id.iloc[0]
    return out


def match(O, S, named):
    lines = oddspapi_lines(O)
    games = pair_games(O, S)
    S = S[S.bookmaker.isin(BOOKS) & S.stat.isin(STAT_SGO)].assign(stat=lambda x: x.stat.map(STAT_SGO), line=lambda x: pd.to_numeric(x.line).round(1))
    sg = defaultdict(list)
    for e, pid, nm, b, s, ln in S[["event_id", "player_id", "player_name", "bookmaker", "stat", "line"]].itertuples(index=False):
        sg[(e, b, s, ln)].append((pid, nm))
    per_id = defaultdict(list)
    keys = defaultdict(dict)
    for (pk, f, b, s), ls in lines.items():
        if str(pk) in named or f not in games:
            continue
        keys[(pk, f)][(b, s)] = ls
    for (pk, f), bs in keys.items():
        e = games[f]
        votes = Counter()
        names = {}
        for (b, s), ls in bs.items():
            cands = {p for ln in ls for p in sg.get((e, b, s, ln), [])}
            for pid, nm in cands:
                votes[pid] += 1
                names[pid] = nm
        if not votes:
            continue
        top = votes.most_common(2)
        if top[0][1] >= MIN_PAIRS and (len(top) == 1 or top[1][1] < top[0][1]):
            per_id[str(pk)].append((top[0][0], names[top[0][0]]))
    out = {}
    for pk, ms in per_id.items():
        c = Counter(p for p, _ in ms)
        best, n = c.most_common(1)[0]
        if len(ms) >= MIN_GAMES and n / len(ms) >= AGREE:
            out[pk] = {"name": dict(ms)[best], "sgo_player_id": best, "games_matched": len(ms), "agree": round(n / len(ms), 3), "source": "sgo"}
    return out


def run(odir, sdir):
    O = pd.concat([pd.read_csv(p) for p in glob.glob(os.path.join(odir, "props", "*.csv.gz")) if os.path.getsize(p) > 60], ignore_index=True)
    S = pd.concat([pd.read_csv(p) for p in glob.glob(os.path.join(sdir, "*.csv.gz")) if os.path.getsize(p) > 60], ignore_index=True)
    npath = os.path.join(odir, "player_names.json")
    named = set(json.load(open(npath))) if os.path.exists(npath) else set()
    out = match(O, S, named)
    json.dump(out, open(os.path.join(odir, "player_names_sgo.json"), "w"), indent=1, sort_keys=True)
    ids = set(O.player_key.astype(str)) - named
    print(json.dumps({"ids_total": int(O.player_key.nunique()), "named_live": len(named), "unnamed_before": len(ids), "named_by_sgo": len(out),
                      "still_unnamed": len(ids - set(out))}))


def selftest():
    O = pd.DataFrame([dict(fixture_id="f1", start_time="2026-02-01T00:00:00Z", home="Boston Celtics", away="Miami Heat", bookmaker=b, market_name=m,
                           handicap=h, player_key=k, close_price=1.9)
                      for b in BOOKS for k, (hp, hr) in {"11": (20.5, 6.5), "12": (12.5, 3.5)}.items()
                      for m, h in (("Over Under Player Points (incl. overtime)", hp), ("Over Under Player Rebounds (incl. overtime)", hr))]
                     + [dict(fixture_id="f2", start_time="2026-02-03T00:30:00Z", home="Miami Heat", away="Boston Celtics", bookmaker=b, market_name=m,
                             handicap=h, player_key="11", close_price=1.9)
                        for b in BOOKS for m, h in (("Over Under Player Points (incl. overtime)", 21.5), ("Over Under Player Rebounds (incl. overtime)", 5.5))])
    S = pd.DataFrame([dict(event_id="e1", start_time="2026-02-01T00:05:00Z", home="Boston Celtics", away="Miami Heat", player_id=p, player_name=n,
                           stat=s, bookmaker=b, line=l) for b in BOOKS
                      for p, n, s, l in (("JT", "Jayson Tatum", "points", 20.5), ("JT", "Jayson Tatum", "rebounds", 6.5),
                                         ("X", "Other Guy", "points", 12.5), ("X", "Other Guy", "rebounds", 3.5))]
                     + [dict(event_id="e2", start_time="2026-02-03T00:30:00Z", home="Miami Heat", away="Boston Celtics", player_id=p, player_name=n,
                             stat=s, bookmaker=b, line=l) for b in BOOKS
                        for p, n, s, l in (("JT", "Jayson Tatum", "points", 21.5), ("JT", "Jayson Tatum", "rebounds", 5.5))])
    out = match(O, S, named=set())
    assert out.get("11", {}).get("name") == "Jayson Tatum" and out["11"]["games_matched"] == 2, out
    assert "12" not in out, out          # only one matched game: below the two-game minimum
    assert match(O, S, named={"11"}).get("11") is None
    print("selftest passed")


if __name__ == "__main__":
    selftest() if sys.argv[1] == "selftest" else run(sys.argv[1], sys.argv[2])
