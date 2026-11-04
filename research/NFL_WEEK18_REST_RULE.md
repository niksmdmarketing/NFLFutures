# NFL simulator: teams with a locked seed rest starters in the final week. Rule, version 1

Written 5 Nov 2026 (Sydney), before any data for this question was looked at. Amendments are added below with dates; nothing above them is edited.

## Why
- In the last regular-season week (week 17 to 2020, week 18 from 2021), clubs whose playoff seed can no longer change often rest starters.
- The simulator (pipeline/simulate.py) plays every final-week game at full strength. That understates the chances of the clubs they play, for playoffs, division and seeds.
- Independent NFL review, 4-5 Nov 2026: TypeSafe "sound with fixable issues" (59%), with this as the next pick (39%, low confidence 0.27).

## Locked club (both stages use the same definition)
After all games before the final week, a club is **locked** when both:
1. its division lead over every division rival is more than 1 win (ties count ½), so it has won the division whatever happens; and
2. its win total differs by more than 1 from every other club in its conference that is within 1 win of its own division's lead (any club that could still win a division).

So its place among division winners, seeds 1-4, cannot change. This is conservative: clubs locked only through a tiebreaker, and wild-card clubs, are not counted as locked.

## Stage 1: is there an effect? (2002-2025, the 8-division era)
- **Expectation for every final-week game:** home − away season-to-date SRS (ridge, as ratings.srs, on that season's earlier games) plus 1.8 at a non-neutral site.
- **Residual:** actual home margin − expectation, signed from the locked club's side.
- **Effect:** mean residual over locked clubs' final-week games (both clubs locked: the game is left out), with a 90% bootstrap over seasons (4,000 draws, seed 1). Control: the same mean over all other final-week games.
- **Stage 1 pass:** the upper bound is below 0. Penalty P = the measured mean, in points, used as is (not re-tuned).
- **Stage 1 fail:** stop; the simulator is not changed.

## Stage 2: simulator fix and no-harm check (only after a Stage 1 pass)
- `simulate(..., rest_pen=P)`: in each simulation, final-week games involving a club locked by the definition above (using that simulation's earlier results) have that club's margin lowered by P. A game with both clubs locked is left unchanged. No other draws change.
- **Replay:** research/replay_nfl.py, checkpoints after weeks 12-17, seasons 2020-2025 (correct 7-seed format, frozen v4), 4,000 simulations, baseline vs `BT_REST=1`.
- **Pass:** combined log-loss mean gain (division, playoff, No. 1 seed, conference, Super Bowl) at least −0.0002, and no market below −0.0005. It is a correctness fix (like the neutral-site fix), so it then goes live in v4 as a dated bug-fix exception to the 2026 freeze.
- **Fail:** recorded; live unchanged.

## Stage 1 result (5 Nov 2026): PASS
research/nfl_week18_rest.py -> research/nfl_week18_rest_results.json and nfl_week18_rest_rows.csv.
- **Locked clubs' final-week games:** 19 (2004-2024). Mean residual −17.9 points, 90% season bootstrap −22.7 to −12.3. Control games (365): +0.9.
- **Penalty P = 17.891.**
- **Caveat:** locked clubs are the season's best, and their season-to-date SRS also regresses, so part of the 17.9 is regression to the mean. The rule fixes P as measured; Stage 2 checks it does no harm.

## Stage 2 result (5 Nov 2026): PASS
Replay of checkpoints after week 12 onwards, 2020-2025 (4,000 sims, frozen v4), baseline vs BT_REST=1. Gain, 90% bootstrap over seasons:
- **Combined:** +0.0005 (+0.0002 to +0.0009), better in 6/6 seasons.
- **Make playoffs:** +0.0027 (+0.0011 to +0.0045), 6/6.
- **Other markets:** division 0.0000, No. 1 seed 0.0000, conference 0.0000, Super Bowl −0.0001 (the worst market, within −0.0005).
- **Largest single change:** 14 percentage points in a team's playoff chance.

**Live from 5 Nov 2026:** run.py passes simulate.REST_PEN (17.891) to the displayed v4 simulation and to the QB shadow, so the shadow still differs from v4 only by QB timing. This is a dated bug-fix exception to the 2026 v4 freeze. The v5 challenger is unchanged.

## Amendments
(none)

### Amendment, 5 Nov 2026: leave-season-out check (GPT review; TypeSafe 62% keep live and check now), written before the run
GPT noted the 17.891 penalty was fitted on 2002-2025, overlapping the 2020-2025 replay that validated it. The check:
- **Penalty per test season y** = the mean residual of locked clubs in every season except y: 2020 17.169, 2021 17.891, 2022 17.891, 2023 17.607, 2024 16.404, 2025 17.891. Seasons with no locked clubs are unaffected, so their rows are reused.
- **Replay and scoring** exactly as in Stage 2: weeks 12+, 4,000 sims, the same baseline.
- **Gates** exactly as in Stage 2: combined mean gain ≥ −0.0002, and no market below −0.0005.
- **Fail:** the penalty is switched off live and runs as a shadow instead.
- **Version label:** displayed NFL futures are labelled `v4+rest-20261105` (meta model field) from now on, so frozen v4 and rest-adjusted v4 are never mixed.
- This is a behavioural assumption, not a correctness fix; that wording in the decision above is withdrawn.
