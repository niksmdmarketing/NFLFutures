# NFL props: calibrating the injury-status availability probabilities. Rule written BEFORE any result (26 Oct 2026)

## Why
The live NFL player-props page converts official injury-report statuses into chances of playing with fixed constants (model/nfl_player_props_v1.json, status_rules):
- Out 0;
- Doubtful 0.10;
- Questionable: the player's normal chance x 0.8;
- a "reported will play" floor of 0.95.

These were set by hand. For NBA the equivalent probabilities were measured from historical official reports (pipeline/nba_avail_params.json; Questionable players sat 45%). Until this test runs, the page labels the constants as assumptions.

## Data
- nflverse weekly injury reports (report_status, gsis_id, team, season, week) for regular seasons 2015-2025, using the final report status for each player-week.
- nflverse snap counts, used for the outcome:
  - **played** means positive offensive snaps;
  - the "official production with zero snaps" correction from RULE.md applies;
  - a missing player counts as not playing only in a complete, reconciled team snap file, otherwise unknown and excluded.
- Players are matched by checked IDs only, never by name.
- Scope: positions QB, WR, TE, RB, FB, the props population.
- Coverage is reported: matched rows, unknowns, and seasons with missing files.

## Candidate (one form)
P(play | status) per status (Out, Doubtful, Questionable) and position group (QB; WR/TE; RB/FB). Each is the empirical share from seasons before the test season, shrunk towards the all-position rate for that status with 20 pseudo-observations. Questionable keeps its multiplicative form: the calibrated multiplier is P(play | Questionable) divided by the average model base probability for those player-weeks, from earlier seasons. Players with no status keep the base probability.

## Test
- Walk-forward over 2021-2025, fitting on 2015..s-1.
- Compare the current constants with the calibrated values, on players with a reported status (Out, Doubtful, Questionable):
  - appearance log loss and Brier;
  - calibration by status and position group;
  - per season.

## Gates (all must hold)
1. Calibrated appearance log loss is lower overall, with a season-block bootstrap one-sided 95% lower bound of the gain above zero.
2. It is better in at least 4 of 5 seasons.
3. No status x position group with at least 200 player-weeks is worse by more than 0.01 in log loss.

## Decision
- **Pass:** the calibrated table replaces the constants under a new parameter identifier (nfl-player-props-v1.1-experimental), recorded with its hash, effective from the next refresh. The page keeps "experimental". The forward archive records which version each forecast used.
- **Fail:** the constants stay, labelled as assumptions, and the result is recorded.
- Either way, the reception and pass-attempt models are untouched, and no claim of a betting edge follows.
