import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import updates


def test_updates_sorted_and_linked():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "nba"))
        shell = '<html><head><title>x</title></head><body><div class="wrap"><header><nav class="sportbar"><a href="./">NFL</a></nav></header></div></body></html>'
        for p in ("index.html", "nba/index.html"):
            open(os.path.join(t, p), "w").write(shell)
        src = os.path.join(t, "u.json")
        json.dump([{"date": "2026-01-01", "sport": "NFL", "text": "a"}, {"date": "2026-02-01", "sport": "NBA", "text": "b"}], open(src, "w"))
        updates.build_site(t, src)
        rows = json.load(open(os.path.join(t, "data", "updates.json")))
        assert [r["date"] for r in rows] == ["2026-02-01", "2026-01-01"]
        assert 'href="../updates.html"' in open(os.path.join(t, "nba", "index.html")).read()
        updates.build_site(t, src)                                   # idempotent
        assert open(os.path.join(t, "index.html")).read().count("Updates</a>") == 1


if __name__ == "__main__":
    test_updates_sorted_and_linked()
    print("ok")
