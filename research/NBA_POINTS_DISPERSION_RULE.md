# NBA points: spread of points given minutes. Rule written BEFORE any result (20 Oct 2026)

Follows the points diagnostic (research/nba_points_diag.py, nba_points_diag.json) and GPT's review of it. The diagnostic suggests three hypotheses, none of them established:
1. fringe minutes are too high (addressed by M2b, which is in the forward test, not here);
2. too little mass on scoreless and near-scoreless nights for low-scoring players;
3. too much shrinkage.

This rule tests (2) only. Shrinkage is not touched. A failed adjustment here is not carried into any later experiment.

## Reconciliation of the figures quoted so far
- **"85% predicted against 77% actual"** (research/nba_points_diag.json): corrected data (team-code and misparsed-team fixes); the points version P+T with M2 minutes; walk-forward fits for 2022-2026; given appearing; the over line = floor(season-to-date average) + 0.5. The group is that version's own forecasts with p(over) >= 0.8 (1,354 player-games). "Expected minutes <= 15" there means projected minutes given appearing under M2 (pre-game), not actual minutes.
- **The earlier "78% against 65%"** (research/NBA_MINUTES_TAIL_RULE.md): pre-fix data; a fixed group defined from stage-one minutes with P+T (2,473 player-games), with M2's predictions.

Different data and different groups, so the two figures are not directly comparable.

## Reference and challenger
- **Reference (R):** points P+T with M2 minutes, as in the minutes-tail rule.
  - Expected points given minutes m = rate x m.
  - Negative binomial with one dispersion r per test season.
- **Challenger (D):** identical, except that the negative binomial's size parameter varies smoothly with expected points μ = rate x m:
  - log r(μ) = a + b x log(μ), two parameters per test season;
  - fitted by maximum likelihood on the appearances of seasons 2017..s-1, given actual minutes, with the rate fixed exactly as in R;
  - the average (rate x m), minutes, appearance probabilities, adjustments and every other input are unchanged.
  
  No bins, thresholds or other forms are searched.

## Data, seasons and scores
- Corrected rows; test seasons 2022-2026; 1 hour before tip-off.
- Same player-games as the prop rule. Scores as in research/NBA_PROPS_SIMPLE_RULE.md: unconditional and conditional RPS (points 0-60), randomised PIT, week-block bootstrap.

## Fixed comparison groups (pre-game, from R's forecasts, shared by R and D)
- **A. Confident overs:** R's p(over) >= 0.8 at the formula line, given appearing.
- **B. Low projected minutes:** R's expected minutes given appearing <= 15.
- **C. Low-minute risk:** P(minutes < 15 | appear) >= 0.2 under M2.
- **E. Established scorers:** R's expected minutes given appearing >= 25.

Each model's own confident group is also reported. Groups defined by actual minutes are diagnostics only.

## Reported for R, D and actual (overall and for each group, given appearing)
- P(0 points) and P(0 or 1 point), against the actual frequency.
- Average points against actual average points.
- High tail: the share of outcomes above each model's own 95th and 99th percentiles (should be 5% and 1%).
- Over/under calibration at the formula lines.
- Descriptive, for the later shrinkage question: predicted against actual average points, grouped by pre-game scoring-rate forecast and projected minutes.

## Gates (all must hold for D)
1. D passes all four original points gates against B1, B2, B3 and B3m (with M2 minutes):
   - 90% lower bound above zero;
   - better in 4 of 5 seasons;
   - PIT deciles 0.07-0.13 given appearing;
   - better given appearing.
2. **Not worse than R:** D's unconditional RPS is not worse than R's overall and for group E (point estimates).
3. **High tail:** D's exceedance of its own 99th percentile is at most 1.5%, and of its 95th at most 6%, given appearing, overall and for group E.
4. **Target improved:** on group A, D's over gap (predicted minus actual) is smaller than R's; and D's P(0 points) is closer to actual than R's for groups B and C.

## Decision
The written gates decide; TypeSafe helps interpret.
- **D passes:** D becomes the points version for a separate forward-test decision. Its own identifier is required before any live use.
- **D fails:** recorded and dropped. A shrinkage test, if any, starts from R, under its own rule and only if the average-points comparison shows a systematic bias.
- No live or site change follows from this test.

## Amendment 1 (20 Oct 2026, GPT review; before any code or result). Where it conflicts with the text above, this governs.
1. **Upper tail for whole numbers.**
   - For each forecast, take q95, the smallest score with F(q95) >= 0.95 (likewise q99), from the full points distribution (0-100, not the 60-point scoring clip).
   - Predicted exceedance = 1 - F(q).
   - The comparison is the observed share of outcomes above q against the average predicted exceedance.
2. **Tail gate (replaces gate 3).**
   - Overall and group E: |observed - predicted| <= 0.010 at the 95th and <= 0.005 at the 99th.
   - Groups B and C: D's absolute tail error is no larger than R's + 0.005 at each level.
   - Sample counts are reported.
3. **Gate 4, first part:** on group A, |average predicted over probability - observed over frequency| must be smaller for D than for R. Zero-point checks stay "closer to actual".
4. **log(μ):** μ = rate x m, with m >= 1 and the shrunk rate strictly positive (group rates are positive and m0 > 0). μ is also floored at 0.01 explicitly.
5. **Paired comparison:** the D-minus-R unconditional RPS improvement is reported with its week-block bootstrap 90% interval (gate 2 remains the point-estimate condition).
