import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nhl_absence as A  # noqa: E402
import nhl_injuries as I  # noqa: E402

HTML = """<h4 class="TableBase-title"><a href="/nhl/teams/LV/vegas-golden-knights/" class="">Vegas</a></h4>
<table><thead><tr><th>Player</th><th>Position</th><th>Updated</th><th>Injury</th><th>Injury Status</th></tr></thead><tbody>
<tr><td><span class="CellPlayerName--short"><span class=""><a href="/x">J. Doe</a></span></span><span class="CellPlayerName--long"><span class=""><a href="/x">John Doe</a></span></span></td>
<td>G</td><td>Mon, Oct 12</td><td>Knee</td><td>IR. Expected to be out until at least Jan 5</td></tr>
<tr><td><span class="CellPlayerName--short"><span class=""><a href="/y">A. Roe</a></span></span><span class="CellPlayerName--long"><span class=""><a href="/y">Al Roe</a></span></span></td>
<td>C</td><td>Mon, Oct 12</td><td>Illness</td><td>Day-to-Day</td></tr></tbody></table>"""


def test_parse_maps_team_and_dates():
    d = I.parse(HTML, 2026)
    assert list(d.team) == ["VGK", "VGK"]
    assert d.name.tolist() == ["John Doe", "Al Roe"]
    assert d.ret.iloc[0] == dt.date(2027, 1, 5) and bool(d.ir.iloc[0])
    assert d.ret.iloc[1] is None and bool(d.dtd.iloc[1])


def test_goalie_cost_and_games(monkeypatch):
    inj = I.parse(HTML, 2026)
    val = pd.Series({"john doe|G": 0.4, "back up|G": 0.0, "al roe|F": 0.5})
    hours = {"al roe|F": 0.3}
    starts = {"VGK": {"john doe|G": 3.0, "back up|G": 1.0}}
    C = A.player_costs(2026, inj, val, hours, starts)
    g = C[C.name == "John Doe"].iloc[0]
    assert g.cost > 0 and g.cost < A.SCALE_G * 0.4
    s = C[C.name == "Al Roe"].iloc[0]
    assert abs(s.cost - A.SCALE_SK * 0.3 * (0.5 - A.REPL_SK)) < 1e-9
    monkeypatch.setattr(I, "current", lambda y: inj)
    monkeypatch.setattr(A, "values", lambda y: val)
    monkeypatch.setattr(A, "_usage", lambda y: (hours, starts))
    games = [("VGK", "SJS"), ("LAK", "VGK"), ("VGK", "ANA")]
    dates = ["2026-10-20", "2027-01-03", "2027-01-10"]
    adj, po, T = A.adjustments(2026, ["VGK", "SJS", "LAK", "ANA"], games, dates)
    # goalie misses the first two games, day-to-day centre the first one; home-minus-away sign
    assert adj[0] < 0 and adj[1] > 0 and adj[2] == 0
    assert np.isclose(adj[0], -(g.cost + s.cost)) and np.isclose(adj[1], g.cost)
    assert po == {}


def test_roster_term_recent_lineup_shift():
    import nhl_lineup as L
    d = pd.date_range("2026-10-01", periods=10)
    lv = pd.DataFrame({"date": list(d) * 2, "team": ["AAA"] * 10 + ["BBB"] * 10, "game_id": range(20),
                       "lv": [0.0] * 5 + [0.2] * 5 + [0.0] * 10})
    t = L.roster_term(lv, None, ["AAA", "BBB"], pd.Timestamp("2026-10-11"), k=30.0, n=5, pre=False)
    # AAA: recent 0.2 vs season 0.1, weight 10/40 -> +0.025 before centring
    assert abs((t["AAA"] - t["BBB"]) - 0.025) < 1e-9 and abs(t.sum()) < 1e-12
