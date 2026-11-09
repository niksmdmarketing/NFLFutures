"""NBL news shadow tests (DeepSeek relay 033, adapted by Claude). Synthetic data only."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import nbl_news as NN


def _p(first, last, team, games, minutes, points):
    return {"team": {"team_code": team}, "player": {"first_name": first, "last_name": last}, "games": games, "minutes": minutes,
            "points": points, "rebounds": 60, "assists": 30, "steals": 10, "blocks": 5, "turnovers": 20,
            "field_goals_made": points // 2.5, "field_goals_attempted": points // 1.2, "free_throws_made": 20, "free_throws_attempted": 25}


SEASONS = {2025: [_p("Jacob", "Holt", "BRI", 20, 600, 400), _p("Bench", "Guy", "BRI", 20, 100, 30), _p("Other", "Star", "SYD", 15, 500, 300),
                  _p("Fill", "In", "SYD", 20, 300, 80)]}
RATING = {"BRI": 2.0, "SYD": -2.0}


def test_values_baseline():
    v = NN.values(SEASONS, 2025)
    assert v[("BRI", "jacobholt")]["value"] > v[("BRI", "benchguy")]["value"]
    assert abs(v[("SYD", "otherstar")]["baseline"] - 0.25) < 1e-9       # missed 5 of 20


def test_null_and_signs():
    v = NN.values(SEASONS, 2025)
    todo = [{"home": "BRI", "away": "SYD", "round": "5"}, {"home": "SYD", "away": "BRI", "round": "9"}]
    assert NN.adjustments(todo, [], v, RATING) is None
    assert NN.adjustments(todo, [{"player_key": "nobody"}], v, RATING) is None
    a = NN.adjustments(todo, [{"player_key": "jacob holt", "return_low": "R7", "return_high": "R7", "return_text_class": "round"}], v, RATING)
    assert a[0] < 0 and a[1] == 0          # out in round 5 (home), back by round 9
