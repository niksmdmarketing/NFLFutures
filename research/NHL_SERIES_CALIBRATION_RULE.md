# NHL playoff series calibration: is the live series probability calibrated? Rule fixed before any logging or scoring (8 Nov 2026, Sydney)

Status: **final before building. Nothing in this rule has been run.** Live NHL futures stay unchanged whatever the result; any change needs its own dated rule and a fresh look.

## Why
research/NHL_PO_SCALE_RULE.md (Amendments 1-6): the nine-season Cup slope (live 1.591, 90% [1.07, 2.38]) cannot separate a series-variance defect from a regular-season or prior defect, because every futures market is a compound (P(make playoffs) x P(win round 1) x ...). The only quantity that isolates the series channel is P(A beats B | A and B meet). About 15 realised series a season, 135 over the nine seasons.

## Estimand (written down so it cannot drift)
For each realised playoff series s (home-ice team h, opponent o): q_s = the model's P(h wins the series | h and o meet), computed at the end of the regular season (all 82 games played, ratings and tau draws as the live path would use them, no knowledge of any playoff result), averaged over the simulated tau draws. Outcome y_s = 1 if h won. Scoring is conditional on the two teams meeting. It says nothing about seeding, bracket or who reaches which round, and no such claim may be made from this data.

## Stage 1: diagnostic of the live setting (no knob, no tuning)
- Live configuration: canonical string of NHL_GOALIE_CANONICAL_RULE.md, TAU_PRE live, po_gap_only off. Baseline is rebuilt in-session, never read from a stored file.
- Statistic: logistic calibration slope of y_s on logit(q_s), intercept free, season-clustered wild bootstrap 90% interval (Rademacher weights, 9 clusters, 10,000 draws, seed 20261108). Also reported: mean log loss and Brier of q_s, and the slope by round (1, 2, 3, final).
- Clustering: a pre-registered band for the within-season correlation, rho in {0.05, 0.10, 0.20}. The finding stands only if it holds at rho 0.20. The minimum detectable slope movement is computed after logging and before scoring from the logged q_s spread (sd of logit q_s, a prediction-only quantity) and the band, and written into this file as a dated amendment. Outcomes are not used to set it.
- Outcomes: **Calibrated** if the interval contains 1. **Defect** if the interval excludes 1 at rho 0.20. **Insufficient** if the interval contains 1 and the half-width exceeds the minimum detectable movement. No other outcome.

## Stage 2: only if Stage 1 says Defect
A separate dated rule names one knob setting in advance, with the live setting reproduced bit for bit as the assertion (both knobs at the live schedule), and states its own minimum detectable movement. No grid on these seasons. If Stage 1 says Calibrated, the Cup-slope flatness is not in the series channel and the po_scale question is closed for this data.

## Logging requirement
simulate() gains an optional list of (home, away) pairs and returns the mean series-win probability for each pair computed analytically from the per-simulation game probabilities (no extra random draws, so every existing output is unchanged; tested against the sampled frequency). The replay adds one end-of-regular-season checkpoint per season and writes series_<season>.csv: season, round, home, away, q, outcome, home-ice flag, plus knobs.json beside it. Realised pairs come from games_<season>p.json.

## Disclosed exposure
Live PO_FADE and TAU_PRE were chosen on the same seasons for Cup and title log loss. Series outcomes were not used. Seasons 2015-2018 and 2021-2025 as in the canonical rule.
