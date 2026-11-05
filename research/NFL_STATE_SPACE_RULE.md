# NFL state-space ratings shadow. Rule, version 1

Written 5 Nov 2026 (Sydney), before any state-space parameter was fitted or any result was seen. Amendments are added below with dated headings; nothing above them is edited.

## Why
- v4 treats rating uncertainty as one constant (tau 5.0) for every team at every point in the season. A state-space model lets each team's rating carry its own uncertainty, large before the season and shrinking as games arrive, and lets the rating drift week to week.
- Earlier tests that tried to shrink or recalibrate rating uncertainty were inconclusive, but none used a proper filter.
- TypeSafe, asked which single NFL experiment to run next: price-first selection 34%, state-space shadow 31%, wait 20%, ensemble 9%, Elo-style benchmark 6%. The owner asked for the state-space test to run now, because price-first has no history to replay (Australian prices only exist from recent captures) and is already running forward as the selection paper test.

## Model (structure fixed before fitting)
- Latent rating per team (points vs average, game-margin scale), Gaussian, full 32x32 covariance, Kalman filter on regular-season game margins only (no efficiency data, no QB or injury layer, no market prices).
- Observation: margin = rating_home - rating_away + hfa + noise (variance s_g^2). hfa is 0 at neutral sites.
- Between weeks every team's variance grows by q_wk (drift). Between seasons mean = rho x end-of-regular-season mean and variance = rho^2 x end variance + q_off.
- Five parameters: rho, q_off, q_wk, s_g, hfa. Fitted once, on 2010-2021 only, by one-step-ahead predictive log likelihood of regular-season games (weeks 1-18). 2006-2009 is burn-in. A coarse grid, refined once around the best cell. The 2022-2025 seasons are not touched when fitting.
- At each checkpoint (before the season, then after each week) the filter gives ratings m (mean zero) and per-team sd = sqrt(P_ii).

## Arms (all compared with research/replay_nfl.py, same checkpoints, 4,000 sims, same seed, BT_REST=1, quarterback and injury layers off)
- **v4:** frozen v4 as live (tau 5.0, sigma 11.37, hfa 1.8, rating_scale 0.89).
- **SS (primary):** state-space mean as the rating (scale 1.0), per-team tau = filter sd, sigma = fitted s_g, hfa = fitted hfa. No tuning on 2022-2025.
- **SS-tau (diagnostic only):** v4 ratings with the filter's per-team sd as tau (v4 sigma and hfa unchanged). It isolates the uncertainty structure. It cannot pass or rescue a fail of SS. If it passes alone, that is recorded and may justify a separate, pre-registered follow-up, nothing more.

## Test seasons
2022-2025 only (the filter never saw them). Caveat carried from v4: v4's tau/sigma were tuned on 2022-2025 win totals, so the baseline has seen the test seasons and SS has not. That favours v4.

## Stage 1: games (2022-2025 regular season, weeks 2-18)
- **Reported:** SS margin RMSE (pre-game filtered ratings + fitted hfa) per season, win-probability log loss at sigma 13.4, blend weight next to the closing spread.
- **Comparison:** v4's recorded RMSE 12.863 over the same 1,023 games (research/nfl_efficiency_weight_results.json, closing spread 12.389). If the game count differs from 1,023 I report that and the difference.
- **Gate (SS only):** SS margin RMSE no worse than 12.863.

## Stage 2: futures
- Markets: division, playoff, No. 1 seed, conference, Super Bowl. Outcomes from model/replay/nfl_<season>.csv (y_ columns). Gain = v4 log loss - variant log loss (clipped 0.002-0.998), mean over checkpoints per season, then averaged over seasons.
- **Pass (SS):** combined mean gain > 0 with its 90% season-bootstrap lower bound > 0 (4,000 draws, seed 1); better in at least 3 of 4 seasons; no market's mean gain below -0.0005; and the Stage 1 gate met.

## Decision
- **Pass:** SS runs as a shadow beside v4 for the rest of 2026 and is archived every refresh. It is forward-scored before any live decision. v4 stays frozen.
- **Fail:** recorded; nothing changes.

## Limits, stated now
- Four test seasons is a small sample and the season bootstrap is coarse.
- A margin-only filter throws away the efficiency information v4 uses, so Stage 1 is expected to be hard for SS. A Stage 1 fail is a real result, not a bug.
- Checkpoints are weeks 0-16, as in the existing replay.
- If the existing model/replay/nfl_<season>.csv v4 columns disagree with a fresh v4 run, the fresh run is the baseline and the difference is reported.

## Result (5 Nov 2026): FAIL
research/nfl_state_space_test.py and research/nfl_state_space_results.json. Parameters fitted on 2010-2021 only (2005-2009 burn-in): rho 0.575, q_off 10.0, q_wk 0.675, s_g 12.5, hfa 1.875 (model/replay/nfl_ss_params.json). q_wk landed on the upper edge of the single refinement grid, and the rule allowed one refinement only, so it was not extended.
- **Stage 1 (1,023 games, 2022-2025, weeks 2-18):** SS margin RMSE 12.887 vs v4 12.863 (recorded) and the closing spread 12.389. The gate (no worse than v4) is not met. SS is better in 2022 (11.70 vs 11.74) and 2025 (13.13 vs 13.28), worse in 2023 (13.42 vs 13.38) and 2024 (13.22 vs 12.97). Win log loss 0.6388 vs 0.6368. Blend weight on SS next to the closing spread -0.11, so about 0.
- **Stage 2 (futures, 4,000 sims, BT_REST=1, fresh v4 baseline):** SS combined gain +0.0010 (90% -0.0030 to +0.0050), better in 1 of 4 seasons (2023 +0.0109 carries it; 2022 -0.0024, 2024 -0.0008, 2025 -0.0038). By market: division -0.0034, playoff +0.0007, No. 1 seed +0.0016, conference +0.0025, Super Bowl +0.0035. Division is below the -0.0005 limit.
- **SS-tau (diagnostic):** combined gain -0.0002 (90% -0.0084 to +0.0043), better in 3 of 4 seasons but 2025 is -0.0130; division -0.0060. It does not pass and gives no case for a follow-up.
- **Baseline check:** fresh v4 vs the checked-in model/replay/nfl_<season>.csv differ by about 0.002-0.004 in playoff probability (simulation noise plus the rest penalty), so the fresh run is the baseline as the rule says.
- **Decision:** fail on both stages. Nothing changes; no shadow. v4 stays frozen.
- **Reading:** the filter's rating uncertainty (team by team, shrinking through the season) did not beat a constant tau, and a margin-only mean is no better than v4 on games. Gains in the long-shot markets (conference, Super Bowl) are consistent in sign but small and inside noise.
