"""Tests for the collection-only NFL injury monitor.  Run: python -m unittest discover -s tests -v"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import nfl_injuries as M  # noqa: E402

NOW = dt.datetime(2026, 10, 10, 3, 0, tzinfo=dt.timezone.utc)


def row(name, pid, pos, inj="", prac="Full Participation in Practice", game=""):
    return (f'<tr><td><a href="/players/{pid}/">{name}</a></td><td>{pos}</td><td>{inj}</td>'
            f"<td>{prac}</td><td>{game}</td></tr>")


def team(label, rows):
    return (f'<div class="d3-o-section-sub-title">{label}</div>'
            '<table class="d3-o-reports--detailed"><thead><tr><th>Player</th><th>Position</th><th>Injuries</th>'
            f'<th>Practice Status</th><th>Game Status</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def page(teams, season=2026, week=5, dates=("THURSDAY, OCTOBER 8TH", "SUNDAY, OCTOBER 11TH")):
    return ("<html><body><h1>Official Latest NFL Injury Report</h1>"
            f"<h1>{season} NFL Injury Report</h1><h2>Injuries - WEEK {week}</h2>" +
            "".join(f"<h2>{d}</h2>" for d in dates) + "".join(teams) + "<h2>NEWS</h2></body></html>")


BASE = [team("Buccaneers", [row("SirVocea Dennis", "sirvocea-dennis", "LB", "Ankle, Foot", "Did Not Participate In Practice", "Out"),
                            row("Tristan Wirfs", "tristan-wirfs", "T", "Knee", "Limited Participation in Practice", "Questionable")]),
        team("Cowboys", [row("Cobie Durant", "cobie-durant", "CB", "Hamstring", "Did Not Participate In Practice", "Out"),
                         row("Tyler Smith", "tyler-smith-2", "G")])]


class Parse(unittest.TestCase):
    def test_parses_teams_players_and_context(self):
        r = M.parse_report(page(BASE))
        self.assertEqual((r["season"], r["week"]), (2026, 5))
        self.assertEqual(r["covered_teams"], ["DAL", "TB"])
        self.assertEqual(r["source_game_dates"], ["2026-10-08", "2026-10-11"])
        by = {x["player_id"]: x for x in r["rows"]}
        self.assertEqual(by["tristan-wirfs"]["team"], "TB")             # offensive lineman kept and assigned to his team
        self.assertEqual(by["tristan-wirfs"]["position"], "T")
        self.assertEqual(by["cobie-durant"]["team"], "DAL")
        self.assertEqual(by["cobie-durant"]["game_status"], "Out")
        self.assertIsNone(by["tyler-smith-2"]["game_status"])          # blank stays blank, never "Active"
        self.assertIsNone(by["tyler-smith-2"]["injury"])

    def test_full_team_names_and_january_dates(self):
        r = M.parse_report(page([team("Arizona Cardinals", [row("A B", "a-b", "QB")])], week=18, dates=("SUNDAY, JANUARY 3RD",)))
        self.assertEqual(r["covered_teams"], ["ARI"])
        self.assertEqual(r["source_game_dates"], ["2027-01-03"])

    def test_malformed_pages_raise(self):
        bad = {
            "no week": page(BASE).replace("Injuries - WEEK 5", "Injuries"),
            "two seasons": page(BASE).replace("<h2>NEWS</h2>", "<h1>2025 NFL Injury Report</h1>"),
            "header change": page(BASE).replace("<th>Game Status</th>", "<th>Status</th>"),
            "unknown team": page([team("Hornets", [row("A", "a", "QB")])]),
            "row shape": page([team("Bears", ["<tr><td>x</td><td>y</td></tr>"])]),
            "no player link": page([team("Bears", ['<tr><td>A</td><td>QB</td><td></td><td></td><td></td></tr>'])]),
            "duplicate team": page(BASE + [BASE[0]]),
            "no tables": page([]),
            "empty html": "",
        }
        for name, html in bad.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    M.parse_report(html)

    def test_unknown_status_is_kept_with_warning(self):
        r = M.parse_report(page([team("Bears", [row("A", "a", "QB", game="Note")])]))
        self.assertEqual(r["rows"][0]["game_status"], "Note")
        self.assertTrue(r["parse_warnings"])


class Collect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.build = Path(self.tmp.name) / "store", Path(self.tmp.name) / "build"

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, html, now=NOW, exc=None):
        def fetch():
            if exc:
                raise exc
            return html, "h"
        return M.collect(self.store, now=now, fetcher=fetch, build_dir=self.build, games_csv=Path(self.tmp.name) / "none.csv")

    def reports(self):
        return sorted(self.store.glob("reports/*/*/*.json"))

    def test_first_collection_and_unchanged_report_is_not_duplicated(self):
        s, ok = self.run_with(page(BASE))
        self.assertTrue(ok)
        self.assertEqual(s["collection_status"], "ok")
        s, ok = self.run_with(page(BASE), now=NOW + dt.timedelta(hours=3))
        self.assertEqual(len(self.reports()), 1)                         # same content -> no new report file
        self.assertEqual(s["checks"], 2)                                 # but the attempt is logged
        self.assertEqual(s["distinct_reports"], 1)
        self.assertTrue((self.build / "injury_monitor.json").exists())

    def test_within_week_changes_are_recorded(self):
        self.run_with(page(BASE))
        changed = [team("Buccaneers", [row("SirVocea Dennis", "sirvocea-dennis", "LB", "Ankle, Foot", "Did Not Participate In Practice", "Out"),
                                       row("Tristan Wirfs", "tristan-wirfs", "T", "Knee", "Full Participation in Practice", "")]),
                   team("Cowboys", [row("Cobie Durant", "cobie-durant", "CB", "Hamstring", "Did Not Participate In Practice", "Out"),
                                    row("New Guy", "new-guy", "DE", "Shoulder", "Limited Participation in Practice", "Questionable")])]
        s, _ = self.run_with(page(changed), now=NOW + dt.timedelta(hours=3))
        kinds = {(c["player_id"], c["kind"]) for c in s["recent_changes"]}
        self.assertIn(("tristan-wirfs", "updated"), kinds)
        self.assertIn(("new-guy", "appeared"), kinds)
        self.assertIn(("tyler-smith-2", "no_longer_listed"), kinds)       # recorded as no longer listed, not "recovered"
        self.assertEqual(len(self.reports()), 2)

    def test_missing_team_table_is_not_a_player_change(self):
        self.run_with(page(BASE))
        s, _ = self.run_with(page(BASE[:1]), now=NOW + dt.timedelta(hours=3))
        kinds = {c["kind"] for c in s["recent_changes"] if c["team"] == "DAL"}
        self.assertEqual(kinds, {"team_table_missing"})

    def test_week_transition_records_no_changes(self):
        self.run_with(page(BASE))
        s, _ = self.run_with(page(BASE[:1], week=6, dates=("THURSDAY, OCTOBER 15TH",)), now=NOW + dt.timedelta(days=3))
        self.assertEqual(s["recent_changes"], [])
        self.assertEqual(s["report_week"], 6)
        self.assertEqual(len(self.reports()), 2)
        self.assertTrue(any("week-06" in str(p) for p in self.reports()))

    def test_partial_early_week_report_is_accepted_and_warned(self):
        csv = Path(self.tmp.name) / "games.csv"
        csv.write_text("season,week,game_type,home_team,away_team\n2026,5,REG,TB,DAL\n2026,5,REG,ARI,SF\n")
        s, ok = M.collect(self.store, now=NOW, fetcher=lambda: (page(BASE), "h"), build_dir=self.build, games_csv=csv)
        self.assertTrue(ok)
        self.assertEqual(s["missing_teams"], ["ARI", "SF"])
        self.assertTrue(any("not on the report yet" in w for w in s["warnings"]))

    def test_network_failure_keeps_last_good_report(self):
        self.run_with(page(BASE))
        s, ok = self.run_with(None, now=NOW + dt.timedelta(hours=3), exc=OSError("timed out"))
        self.assertFalse(ok)
        self.assertEqual(s["collection_status"], "degraded")
        self.assertIn("timed out", s["last_error"])
        self.assertEqual(len(s["rows"]), 4)                              # last good rows still there
        self.assertEqual(s["failed_checks"], 1)

    def test_malformed_page_does_not_replace_report(self):
        self.run_with(page(BASE))
        s, ok = self.run_with("<html>maintenance</html>", now=NOW + dt.timedelta(hours=3))
        self.assertFalse(ok)
        self.assertEqual(len(self.reports()), 1)
        self.assertEqual(s["report_week"], 5)

    def test_stale_report_is_flagged(self):
        self.run_with(page(BASE))
        s, _ = self.run_with(None, now=NOW + dt.timedelta(hours=7), exc=OSError("down"))
        self.assertEqual(s["collection_status"], "stale")
        self.assertTrue(any("do not assume" in w for w in s["warnings"]))
        s, _ = self.run_with(page(BASE), now=NOW + dt.timedelta(days=10))
        self.assertTrue(any("ended more than a week ago" in w for w in s["warnings"]))

    def test_wrong_season_is_rejected(self):
        s, ok = self.run_with(page(BASE, season=2025))
        self.assertFalse(ok)
        self.assertEqual(s["collection_status"], "unavailable")

    def test_first_ever_failure(self):
        s, ok = self.run_with(None, exc=OSError("dns"))
        self.assertFalse(ok)
        self.assertEqual(s["collection_status"], "unavailable")
        self.assertEqual(s["rows"], [])

    def test_sqlite_rebuild(self):
        self.run_with(page(BASE))
        self.run_with(page(BASE[:1]), now=NOW + dt.timedelta(hours=3))
        import sqlite3
        db = sqlite3.connect(M.build_sqlite(self.store, Path(self.tmp.name) / "x.sqlite"))
        self.assertEqual(db.execute("select count(*) from reports").fetchone()[0], 2)
        self.assertEqual(db.execute("select count(*) from checks").fetchone()[0], 2)
        self.assertGreater(db.execute("select count(*) from changes").fetchone()[0], 0)

    def test_monitor_is_not_used_by_projections(self):
        root = Path(M.__file__).resolve().parent
        for f in ("ratings.py", "simulate.py", "simulate_v3.py", "awards.py", "award_race.py"):
            self.assertNotIn("nfl_injuries", (root / f).read_text(encoding="utf-8"), f)


if __name__ == "__main__":
    unittest.main()
