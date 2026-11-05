# NBA live forecast: schedule rows fix (6 Nov 2026), dated bug fix
Owner approved 6 Nov 2026 ("Yes for schedule fix") after the replay finding in research/NBA_REPLAY_STANDING_RULE.md, Amendment 5.
- **Bug:** ESPN schedule files keep the original row of a postponed game beside its make-up game and list the NBA Cup final, which does not count in the standings. pipeline/nba.py simulated both as extra regular-season games (up to 85 games a team in the 2021-22 file).
- **Fix:** `_season_rows` drops rows with status POSTPONED and type CC after `_schedule`, in `build_data` only. A postponed game with no make-up row yet is covered by the simulator's existing filler games. `_schedule` itself is unchanged, so legacy replays keep reproducing.
- **Effect today:** none. The 2026-27 schedule (checked 6 Nov 2026) has no such rows; a 2,000-simulation run on it is identical before and after. On the 2021-22 file the schedule drops from 1,241 to 1,230 rows and the maximum games per team from 85 to 82.
- **Tests:** tests/test_nba_season_rows.py.
