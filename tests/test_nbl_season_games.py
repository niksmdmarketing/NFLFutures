import itertools, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import nbl_site


def test_extra_phase_games_are_finals():
    teams = list("ABCD")
    games, i = [], 0
    for rnd in range(4):                       # each pair plays 4 times -> 12 games each
        for h, a in itertools.permutations(teams, 2):
            if (h < a) == (rnd % 2 == 0):
                i += 1
                games.append({"id": i, "start_time": f"2026-01-{i:02d}", "match_status": "complete", "home_score": 90,
                              "away_score": 80, "home_team": {"team_code": h}, "away_team": {"team_code": a}, "phase": "Regular"})
    n = {t: sum(t in (g["home_team"]["team_code"], g["away_team"]["team_code"]) for g in games) for t in teams}
    st = [{"team": {"team_code": t}, "won": n[t] // 2, "lost": n[t] - n[t] // 2, "phase": "Regular"} for t in teams]
    for k, (h, a) in enumerate([("A", "B"), ("A", "B")]):      # semi-final games mislabelled Regular
        games.append({"id": 100 + k, "start_time": f"2026-02-{k+1:02d}", "match_status": "complete", "home_score": 90,
                      "away_score": 80, "home_team": {"team_code": h}, "away_team": {"team_code": a}, "phase": "Regular"})
    x, _, reg_n = nbl_site.season_games({"standings": st, "games": games})
    assert int((~x.fin).sum()) * 2 == sum(reg_n.values())
    assert int(x.fin.sum()) == 2
