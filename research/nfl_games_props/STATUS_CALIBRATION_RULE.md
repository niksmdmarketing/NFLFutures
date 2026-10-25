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

## Outcome (26 Oct 2026). Fails; the current constants stay (labelled as assumptions)
Run: research/nfl_games_props/status_calibration_test.py (code committed before results; results status_calibration_results.json).

**Disclosed implementation details, fixed before scoring:**
- the research player rows start in 2018, so fitting used 2018..s-1 rather than 2015..s-1;
- probabilities clipped to [0.001, 0.999] in both versions;
- the base appearance model refitted walk-forward.

**Data:** 65,795 player-weeks. 3,457 with a reported status were scored in 2021-2025: Out 1,383, Doubtful 234, Questionable 1,840. 276 player-weeks with unknown appearance were excluded.

**Overall:**
- log loss: current 0.38424, calibrated 0.38971 (gain -0.00547; one-sided 95% bound -0.01073);
- Brier: 0.13196 against 0.13360;
- better in 1 of 5 seasons.

All three gates fail.

| Status and group | n | Played | Current mean p | Calibrated mean p | Log loss current / calibrated |
|---|---|---|---|---|---|
| Out (all groups) | 1,383 | 0.1% | 0% | about 0% | equal |
| Doubtful QB / RB-FB / WR-TE | 31 / 61 / 142 | 0% / 0% / 0.7% | 10% | 1-3% | 0.105 / 0.011; 0.105 / 0.030; 0.121 / 0.050 |
| Questionable QB | 150 | 43% | 50% | 54% | 0.776 / 0.817 |
| Questionable RB-FB | 500 | 65% | 57% | 62% | 0.680 / 0.675 |
| Questionable WR-TE | 1,190 | 70% | 58% | 71% | 0.703 / 0.731 |

**Reading:**
- Doubtful players almost never played (0.4% overall), so the 10% assumption is clearly too high.
- For Questionable players, the calibrated multipliers (0.81-0.97) move the average closer to the observed rate. But they score worse, because the base appearance model separates which Questionable players play only weakly, so a larger multiplier mostly spreads probability onto the wrong players.
- The single-form candidate fails as written. The constants stay, still labelled as assumptions.
- **Out of scope here:** a Doubtful-only correction, and a different Questionable form (for example, using practice participation). Each would need its own rule. The Doubtful pattern was seen in this test, so a Doubtful rule would be data-suggested and would need forward confirmation.
