# NBA player-first model: summary for review (20 Oct 2026)

Written for outside critique. Full rule, amendment and outcomes: research/NBA_PLAYER_FIRST_RULE.md. No live model or setting changed.

## Why this was done
The user asked whether a separately designed NBA model, giving player ratings more weight, could beat the current one. I first told TypeSafe (and the user) that an in-season player model had never been tested. That was wrong: on 14 Oct 2026 weekly-refitted player ratings were blended into the team rating at 15-30% and made futures slightly worse. After correcting the record, TypeSafe still chose to build a standalone game-level test (83%), because a prediction built from the players expected to play each game had not been tested.

## What the current NBA model is
- In season: a team rating (ridge on points per 100 possessions; last four seasons decaying, current season weight 8).
- Pre-season: 60% team rating + 40% player strength from RAPM (lineup-stint ratings), plus a roster step for transactions and a young-player development bonus; the player share fades to zero by game 20.
- Playoffs: a playoff-rotation term from RAPM and minutes.
- Single games: an availability (injury) adjustment.

## Test 0: three-way, single games (rule committed before results)
- Seasons 2015-2026 (12 test seasons, 14,440 games; 2014 used only for fitting). Weekly checkpoints; every input from before the week.
- A: team rating alone (refitted weekly), with a walk-forward linear recalibration.
- B: player-first. RAPM refitted weekly from all lineup stints before the week (last season weight 1, season before 0.5, this season 1; ridge toward a box-score prior). Team strength = sum of player rating x expected minutes / 48 over the players who played in the team's previous game; minutes = each player's last-10-games average, scaled to 240.
- C: A and B combined (weights fitted on earlier seasons only).

| Model | Margin MSE | vs A | Seasons better | Log loss |
|---|---|---|---|---|
| A team rating | 179.3 | - | - | 0.6201 |
| B player-first | 192.9 | -7.6% | 0 of 12 | 0.6489 |
| C combined | 177.7 | +0.93% (one-sided 97.5% bound above zero) | 12 of 12 | 0.6172 |

C passed all five gates (MSE bound, 12/12 seasons, log loss, early and later games, calibration slope 1.006). The player weight rose from 0.06 (2015) to 0.26 (2026) as stint history grew. Using the lineups that actually played did worse than previous-game lineups (actual minutes include garbage time), so the pre-game version is not using hidden information.

## Test 1: on top of the live availability layer (single games)
| Version | Games | Gain from the player term | Seasons better | Log loss without / with |
|---|---|---|---|---|
| Availability v2_base, 2015-2026 | 14,440 | +0.31% | 10 of 12 | 0.6077 / 0.6068 |
| Official pre-game injury reports, 2022-2026 | 6,153 | +0.42% | 5 of 5 | 0.6102 / 0.6095 |
Passed. The availability layer absorbs most of the gain (0.93% -> 0.3-0.4%), but it stays positive in almost every season.

## Test 2: futures replay
Live futures replay settings, plus the player term added to every checkpoint's team rating: rating + k x (S - mean S), k = player weight / team weight from Test 0 for that season. 11 seasons (2015-2026 without 2020).
- Mean log loss over five markets 0.1827 -> 0.1850 (gain -0.0023, 90% -0.0095 to +0.0037); better in 6 of 11 seasons; every market slightly worse.
- 2026 alone -0.041 at every stage (e.g. Lakers division 11% -> 1%, Spurs 8% -> 4%; both won). Without 2026 about +0.0016, but 2026 counts.
- Failed all three gates. Decision (TypeSafe 99%): recorded, not used.

## My reading
- Player ratings alone are much noisier than team results.
- As a second opinion for single games they help a little, consistently.
- In futures they hurt, most likely because the live futures model already carries player information (roster step, pre-season RAPM mix, playoff rotation), so a second player term double counts it and amplifies the player ratings' disagreements with results.

## Weaknesses I know about (please check these)
1. In Test 0, A was the team rating alone, not the full live model (no roster step or pre-season player mix). Early-season gains for C may therefore be overstated against the real live model.
2. A was given a walk-forward linear recalibration so it is not handicapped by scale; that also means "A" is not exactly the live probabilities.
3. The availability variant used in Test 1a (v2_base) uses who actually played before 2021, i.e. game-day information; it is generous to the baseline. Test 1b uses only official pre-game reports but covers only 2022-2026.
4. The rule said official reports start in 2022; the data actually cover 2020 onward. I gated on 2022+ as written and reported 2021+ separately.
5. The futures test used one specification only: k taken from the game-level weights and applied on top of the full live rating, whose scale and contents differ (roster step, pre-season mix). It was not tuned. A failure here does not rule out a better futures design, for example replacing the roster step rather than adding to it.
6. The pre-season lineup in the futures term is each team's last game of the previous season: rested stars and summer trades are not seen. This is a likely cause of the pre-season damage, including 2026.
7. Previous-game lineups miss players returning from injury and include players hurt during that game.
8. RAPM settings (ridge 3000, box prior 2.5, development bonus) were chosen earlier on the same seasons, so the player ratings are not fully out of sample.
9. Several tests were run in sequence on the same day; each had pre-registered gates, but the sequence itself is a garden of forking paths.
10. The bubble season (2020) is in the single-game test but skipped in the futures replay.

## Open questions for review
- Is "single-game only" a legitimate separate use, given that the futures model and the game predictions would then disagree on team strength?
- Is the double-counting explanation for the futures failure right, or is it the crude pre-season lineup (weakness 6)?
- Should a future futures test replace parts of the existing player information rather than add a term on top?
