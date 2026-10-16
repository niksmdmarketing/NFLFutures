import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import navgroups as N  # noqa: E402

FLAT = ('<header><nav class="nav nav-simple" aria-label="NBA sections"><a href="./">Standings</a><a href="futures.html">Futures</a>'
        '<a href="why.html">Why</a><a href="teams.html">Team stats</a><a href="new.html">Brand new</a></nav></header>')


def test_groups_keep_every_link_and_are_idempotent():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "nba"))
        for fn in ("index.html", "futures.html", "why.html", "teams.html", "new.html"):
            open(os.path.join(d, "nba", fn), "w").write(FLAT)
        N.apply(d)
        once = open(os.path.join(d, "nba", "why.html")).read()
        N.apply(d)
        assert open(os.path.join(d, "nba", "why.html")).read() == once
        for f in ("./", "futures.html", "why.html", "teams.html", "new.html"):
            assert f'href="{f}"' in once
        assert 'aria-current="page">Forecast<' in once and 'aria-current="page">Why, team by team<' in once
        assert once.count("<nav") == 2
        idx = open(os.path.join(d, "nba", "index.html")).read()
        assert "nav-sub" not in idx   # a one-page tab has no second row
