# NFL futures: a Bayesian-inspired uncertainty schedule. Rule fixed before any code or results (26 Oct 2026, Sydney)

Status: **final.** GPT reviewed the draft; all its changes were accepted (TypeSafe 89% to accept and run). Nothing had been run when this was committed. Displayed v4 stays frozen.

## Why
- In the corrected 13-season replay (research/NFL_SIMULATOR_LOGIC_CHECK.md), v4 is too cautious in-season. Calibration slopes at weeks 4 / 8:
  - division 1.31 / 1.25;
  - make-playoffs 1.28 (1.06-1.56) / 1.21 (1.00-1.47);
  - conference 1.51 / 1.73.
- Pre-season is calibrated (division 1.01, make-playoffs 0.93).
- pipeline/simulate.py draws each team's strength once per simulated season, N(rating, tau = 5.0), and keeps it all season. Each game adds independent noise N(0, sigma = 11.37).
- The persistent component correlates a team's remaining games, widening its win distribution and pulling futures probabilities toward the middle. Tau is the same at week 16 as pre-season.
- TypeSafe chose this structural test (80%) over a statistical recalibration layer (13%).

## Disclosed exposure
- research/replay_nfl.py has a linear "tau fade" option that was explored on 2022-2025 and not adopted.
- The corrected 2013-2025 calibration figures above were inspected before this rule.
- The baseline's own settings (tau, sigma, scale, home edge, rating weights) were selected on overlapping seasons.
- The schedule below has no newly fitted parameter, but its choice followed this exposure. The replay is not an untouched validation set.

## Candidate (one form)
At each forecast snapshot, n = the average number of completed regular-season games per team available at the forecast cutoff.
- tau_n = 5 / sqrt(1 + n · 25 / 11.37²). This is the normal-normal posterior sd formula for a fixed strength observed with known noise; it is used as a schedule, not as an exact posterior. Values: n = 4 -> 3.75; 8 -> 3.13; 12 -> 2.74; 16 -> 2.47.
- sigma_n = sqrt(11.37² + 2(25 - tau_n²)). The simulated margin carries independent team uncertainty from both sides, so this keeps 2·tau_n² + sigma_n² = 2·5² + 11.37². For a given matchup, ratings and home edge, the marginal game win probability is unchanged. Only the dependence across a team's games changes. Conference and title probabilities can still move through qualification and selection.
- tau_n and sigma_n are fixed for the whole snapshot, including its simulated remainder and playoffs. They are not shrunk again with simulated future games.
- n = 0 (pre-season) is identical to v4 by construction.
- Not tested here (no retrospective choice between variants): team-specific n with matchup-specific compensation; sigma kept at 11.37 (sharper single games). Either would be a separately labelled later experiment.

## Both arms identical except tau_n and sigma_n
- Same out-of-sample v4wf ratings (research/nfl_futures_diagnosis.py) and scale 0.89.
- Home edge 1.8; playoff home edge as v4; neutral sites get no home edge.
- Correct playoff format by season (6 seeds to 2019, 7 from 2020); 3-club sweep option off.
- No QB layer in either arm.
- **Monte Carlo:** 5,000 simulations per snapshot. Paired random numbers: both arms use the same seed, so the strength and game draws are the same standard normals, scaled by each arm's tau_n and sigma_n. Two independent seed sets (A and B) are run for both arms.
- **Probabilities** are clipped to [0.001, 0.999] in both arms before scoring.

## Scores
- **Cells:** market (division; make-playoffs) × checkpoint (after weeks 4, 8, 12): six primary cells.
- **Per season:** mean team-level binary log loss in each cell; the six cells averaged equally.
- **Primary score:** the season values averaged equally over 2013-2025.
- **Gain** = v4 loss - challenger loss (positive = challenger better).
- **Bootstrap:** resample whole seasons (paired forecasts and all observations within a season kept together), 10,000 draws, seed 20261026.
- **Non-regression cells, fixed now:**
  - No. 1 seed, conference and title at weeks 4, 8, 12 and 16;
  - division and make-playoffs at week 16.
- **Also reported for every cell:** calibration slope and intercept (season-bootstrap 90%), and Brier score.

## Gates (all must hold, on the average of seed sets A and B)
1. Primary gain: one-sided 90% bootstrap lower bound > 0, and gain positive in at least 8 of 13 seasons.
2. Point-estimate gain positive separately for division (its three cells) and for make-playoffs (its three cells).
3. Division and make-playoffs slopes at weeks 4 and 8 closer to 1 than v4's, and none below 0.85.
4. No non-regression cell worse than v4 by more than 0.002 mean log loss.
5. Primary gain positive in 2020-25. This is reported as an exposed historical subgroup, not independent confirmation.

**Monte Carlo agreement:** seed sets A and B must give the same outcome on every gate. If they differ, the result is **inconclusive**, not a pass.

## Decision
- **Pass:** a core-model shadow (v4 plus this schedule), archived live beside displayed v4 and scored against Polymarket.
  - Before the forward run, a separate note fixes the forward evaluation dates, the price timestamps, and the fee and settlement treatment.
  - Promotion would need point-in-time evaluation with the production QB layer and forward evidence. A historical pass is not a claim of proven improvement or profitability.
- **Fail (any gate):** recorded; this candidate stops. Gates are not relaxed after results.
- **Inconclusive:** recorded as such, with no change. The fallback is TypeSafe's second choice, a pre-registered recalibration layer, under its own rule.

## Scope
This is a core-model experiment without the QB layer. Uncertainty shrinkage could interact with missing QB information, so the effect need not transfer to the live model; the direction of that bias is unknown.
