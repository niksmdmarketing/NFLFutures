# Receiver participation-weighted target allocation — 24 October 2026 Sydney

Written after the conditional audit identified target-budget scaling as the reception model's main repeatable weakness, and before this candidate is run. Test exactly one candidate. Do not tune another form, threshold or coefficient after seeing the result. No website, live model, market input or automatic injury logic changes.

## Fixed candidate

Retain the current team pass-volume distribution, each receiver's smoothed target share, smoothed catch probability and beta-binomial concentration exactly. Retain the original strictly lagged candidate cohort and score the same appearing receivers as the corrected audit.

Fit the existing appearance classifier on seasons before each test season, using only its existing pre-game features. Let `s_i` be receiver i's current conditional-on-appearing target share and `a_i` the pre-game appearance probability. For the projection conditional on receiver i appearing, define:

`expected_budget_i = s_i + sum(a_j * s_j for j != i)`

`effective_share_i = s_i * min(1, 1 / expected_budget_i)`

This replaces only the old scale based on treating every candidate as certain to appear. It does not redistribute an absent player's targets beyond avoiding the false all-active scale. Target share remains role; catch probability remains production. The focal player's own probability is one because the forecast is conditional on that player appearing.

## Test

Walk forward over 2021–2025. Every fitted component uses seasons before the test year. Score the exact same receiver/game rows as the corrected audit and compare paired results with:

1. the unchanged current all-candidates-active allocation;
2. the unchanged unweighted last-10-appearances negative-binomial control.

Use conditional RPS normalised at 20 receptions, log score, randomized PIT, means, zero frequency, formula-line overs and discrete 95th/99th exceedance calibration. Retain the corrected audit's fixed groups. Use the same 4,000-draw season-block lower bound and seed 20261023.

## Gates

The candidate is a historical challenger only if all hold:

- RPS improves over the current allocation with a positive paired season-block lower bound and in at least four of five seasons.
- RPS beats last 10 with a positive paired season-block lower bound and in at least four of five seasons.
- Every overall PIT decile lies from 0.07 through 0.13.
- The absolute mean error for established receivers (season-control mean at least two) falls by at least 25%.
- RPS for season-control mean below two and candidate mean below one is not more than 0.5% worse than current.
- Overall log score is not worse; the absolute 95th-percentile exceedance gap is not more than 0.002 worse.

Passing is not a market edge. It does not validate automatic starter, roster, injury or news selection. If it fails, preserve the result and stop this branch; do not search alternatives in the same run.

Tests must prove: the focal player's appearance probability is replaced by one only in its own conditional denominator; competitor probabilities and player features are pre-game; rows and outcomes match the corrected audit; fold fits use earlier seasons; current-all-active scores reproduce the corrected audit; protected inputs remain byte-identical.
