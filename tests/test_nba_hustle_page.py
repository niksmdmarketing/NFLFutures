import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import nba_site
import sportsite as S


def test_hustle_page_registered_and_script_exists():
    slugs = [p[0] for p in nba_site.PAGES]
    assert "hustle" in slugs
    assert os.path.exists(os.path.join(S.ENGINE, "hustle.js"))
    page = S.page_html("NBA", "Futures", [(s, l) for s, l, _, _ in nba_site.PAGES], "hustle", "t", "i", script="hustle.js")
    assert 'src="hustle.js"' in page and 'data-page="hustle"' in page and "Hustle &amp; Synergy" in page
