"""Bookmaker player names -> ESPN athlete ids for the props price test (research/NBA_PROPS_PRICE_TEST_RULE.md).
Matching happens within one game: candidates are the players the forecast lists for the two teams. Steps, first hit wins:
exact normalised name; normalised name after the nickname table; unique (first initial, surname) within the game; unique surname
within the game. Normalising strips accents, punctuation, case and suffixes (Jr, Sr, II, III, IV). Unmatched names are returned,
never guessed. `python research/nba_props_names.py selftest` checks it against ESPN names from the 2025-26 box scores."""
import os
import re
import sys
import unicodedata

SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
NICK = {"nic": "nicolas", "nicolas": "nicolas", "herb": "herbert", "cam": "cameron", "mo": "moritz", "bub": "carrington", "kj": "kenyon",
        "gg": "gregory", "og": "ogugua", "rj": "rj", "pj": "pj", "tj": "tj", "cj": "cj", "aj": "aj", "jj": "jj", "bj": "bj", "dj": "dj",
        "trey": "trey", "jabari": "jabari", "dennis": "dennis", "nah'shon": "nahshon", "bones": "nahshon", "ish": "ishmail",
        "sviatoslav": "svi", "svi": "svi", "xavier": "xavier", "kenny": "kenyon", "mike": "michael", "nick": "nicholas", "matt": "matthew",
        "alex": "alexandre", "jakob": "jakob", "jeff": "jeffrey", "dan": "daniel", "danny": "daniel", "tim": "timothy", "ron": "ronald"}


def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`’]", "", s)
    s = re.sub(r"[^a-z0-9 -]", " ", s).replace("-", " ")
    s = SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _nick(n):
    parts = n.split(" ")
    if parts and parts[0] in NICK:
        parts[0] = NICK[parts[0]]
    return " ".join(parts)


def match(book_names, candidates):
    """candidates: list of (aid, espn_name). Returns ({book_name: aid}, [unmatched book names])."""
    full = {}
    nick = {}
    init = {}
    sur = {}
    for aid, nm in candidates:
        n = norm(nm)
        full.setdefault(n, set()).add(aid)
        nick.setdefault(_nick(n), set()).add(aid)
        p = n.split(" ")
        if len(p) >= 2:
            init.setdefault((p[0][0], " ".join(p[1:])), set()).add(aid)
            sur.setdefault(" ".join(p[1:]), set()).add(aid)
    out, miss = {}, []
    for b in book_names:
        n = norm(b)
        p = n.split(" ")
        for table, key in ((full, n), (nick, _nick(n)), (init, (p[0][:1], " ".join(p[1:])) if len(p) >= 2 else None),
                           (sur, " ".join(p[1:]) if len(p) >= 2 else None)):
            hit = table.get(key) if key is not None else None
            if hit and len(hit) == 1:
                out[b] = next(iter(hit))
                break
        else:
            miss.append(b)
    return out, miss


def selftest():
    import pandas as pd
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    b = pd.read_csv(os.path.join(root, "data", "nba", "player_box_2026.csv"), usecols=["game_id", "athlete_id", "athlete_display_name"], low_memory=False).dropna()
    games = b.groupby("game_id")
    rng = __import__("random").Random(1)
    tested = ok = 0
    for gid, g in list(games)[:400]:
        cand = list(zip(g.athlete_id, g.athlete_display_name))
        variants = []
        for aid, nm in cand:
            v = nm
            r = rng.random()
            if r < 0.2:
                v = nm.upper()
            elif r < 0.35:
                v = re.sub(r"\s+(Jr\.?|Sr\.?|III|II|IV)$", "", nm)
            elif r < 0.5:
                v = unicodedata.normalize("NFKD", nm).encode("ascii", "ignore").decode()
            elif r < 0.6:
                v = nm.replace(".", "")
            elif r < 0.7 and " " in nm:
                v = nm.split(" ")[0][0] + ". " + " ".join(nm.split(" ")[1:])
            variants.append((v, aid))
        res, miss = match([v for v, _ in variants], cand)
        for v, aid in variants:
            tested += 1
            ok += res.get(v) == aid
    rate = ok / tested
    assert rate > 0.97, rate
    assert match(["Nic Claxton"], [(1, "Nicolas Claxton"), (2, "Ben Simmons")])[0] == {"Nic Claxton": 1}
    assert match(["Alperen Sengun"], [(1, "Alperen Şengün")])[0] == {"Alperen Sengun": 1}
    assert match(["Jimmy Butler"], [(1, "Jimmy Butler III")])[0] == {"Jimmy Butler": 1}
    print(f"selftest passed: {ok}/{tested} synthetic variants matched ({rate:.4f})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
