# NFL futures: team uncertainty that shrinks with games played. DRAFT rule for review before any code or results (26 Oct 2026, Sydney)

Status: **draft, sent to GPT for review.** Nothing has been run. The final version will be committed before the test.

## Why
- In the corrected 13-season replay (research/NFL_SIMULATOR_LOGIC_CHECK.md), v4 is too cautious in-season. Calibration slopes at weeks 4 / 8:
  - division 1.31 / 1.25;
  - make-playoffs 1.28 (1.06-1.56) / 1.21 (1.00-1.47);
  - conference 1.51 / 1.73.
- Pre-season is calibrated (division 1.01, make-playoffs 0.93). Single games and win totals were fine in earlier checks.
- In pipeline/simulate.py each simulated season draws team strength once, N(rating, tau = 5.0), and keeps it for the rest of the season. Tau is the same at week 16 as before the season, although the ratings by then rest on many more games.
- The persistent component (tau) correlates a team's remaining games, which widens its win distribution and pulls futures probabilities toward the middle. The per-game component (sigma = 11.37) is independent noise.
- TypeSafe chose this structural test (80%) over a statistical recalibration layer (13%).

## Prior exposure (disclosed)
- research/replay_nfl.py already has a linear "tau fade" option (BT_TAUFADE, share of tau removed by the end of the season). It was explored on 2022-2025 and not adopted.
- The 2013-2025 replay rows have been inspected (the slopes above).
- This is therefore not an untouched test. The candidate below has no fitted parameter, to limit the room for tuning.

## Candidate (one form, no fitted parameter)
For a checkpoint after week w, with n = mean regular-season games played by the 32 teams:
- **Persistent uncertainty:** tau_n = tau0 / sqrt(1 + n · tau0² / sigma0²), with tau0 = 5.0 and sigma0 = 11.37 (frozen v4 values). This is the posterior sd of a normal prior with sd tau0 updated with n games of noise sigma0.
  - Values: n = 4 -> 3.75; 8 -> 3.13; 12 -> 2.74; 16 -> 2.47.
- **Per-game noise:** sigma_n = sqrt(tau0² + sigma0² - tau_n²), so the total per-game sd stays at the frozen sqrt(5.0² + 11.37²) = 12.42. Single-game win probabilities keep their v4 spread; only the split between team-level (correlated) and game-level (independent) uncertainty changes.
- Pre-season (n = 0) is identical to v4 by construction.
- Everything else as in v4: ratings, scale 0.89, home edge 1.8, playoff home edge, neutral-site fix, correct 6/7-seed format by season, 3,000 simulations, same random seeds. The 3-club sweep option stays off.

## Replay and scores
- research/nfl_futures_diagnosis.py, v4wf model, seasons 2013-2025, checkpoints weeks 4, 8, 12 and 16 (pre-season unchanged).
- Same out-of-sample ratings as the corrected replay. The only difference is tau_n and sigma_n.
- Markets: division, make-playoffs, No. 1 seed, conference, title.
- **Primary score:** mean log loss over the division and make-playoffs markets at weeks 4, 8 and 12. These are the markets and weeks the betting work uses.
- **Also reported:** calibration slope and intercept per market and week (season-bootstrap 90%), Brier score, and each other market and week separately.

## Gates (all must hold)
1. Primary log loss better than v4. Season-block bootstrap lower bound of the paired gain above 0 (one-sided 90%). Better in at least 8 of 13 seasons.
2. Division and make-playoffs slopes at weeks 4 and 8 closer to 1 than v4's. No slope in these markets and weeks below 0.85 (no swing into over-confidence).
3. No other market at any checkpoint worse than v4 by more than 0.002 mean log loss (No. 1 seed, conference, title; division and make-playoffs at week 16).
4. Equal 2013-19 and 2020-25 weighting is reported. The gain must not come only from 2013-19 (positive mean gain in 2020-25).

## Decision
- **Pass:** a shadow version of v4 with tau fade, archived live beside v4 and scored against Polymarket. It becomes the betting number only by a separate decision after forward evidence. v4 stays the displayed model for 2026.
- **Fail:** recorded; this branch stops. The fallback is TypeSafe's second choice, a pre-registered recalibration layer, as a separate rule.
- No profit claim either way.

## Questions for review
1. Is holding the total per-game sd constant right, or should sigma stay at 11.37 (which would also sharpen single-game probabilities)?
2. Is the Bayesian form with no fitted parameter better than a fitted fade, given the prior exposure?
3. Is n = mean games played right, or should tau_n vary by team's own games played?
4. Are the gates (especially 2 and 4) strict enough, or too strict for 13 seasons?
5. The replay omits the QB layer. Does that bias this test?
