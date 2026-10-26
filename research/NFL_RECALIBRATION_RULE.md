# NFL futures: walk-forward recalibration layer for division and make-playoffs. Rule fixed before any code or results (26 Oct 2026, Sydney)

Status: **final.** GPT reviewed the draft; its revisions were accepted (TypeSafe 73% to accept and run). Nothing had been run when this was committed. Displayed v4 stays frozen. A pass authorises shadow forecasts only, not betting deployment.

## Why
- The uncertainty-schedule test (research/NFL_TAU_FADE_RULE.md) failed. It fixed v4's in-season caution, but the gain came only from 2013-19.
- This layer was that rule's named fallback and TypeSafe's second choice.

## Disclosed exposure
- The v4 replay probabilities and calibration slopes have been inspected:
  - all seasons: division 1.31 / 1.25 / 0.96 at weeks 4 / 8 / 12; make-playoffs 1.29 / 1.21 / 1.13;
  - 2020-25: division 1.22 / 0.95 at weeks 4 / 8; make-playoffs 1.28 / 1.03.
- The uncertainty-schedule result is known, and the baseline's settings were chosen on overlapping seasons.
- These are forward-in-time calibration fits on an exposed baseline, not an untouched evaluation.

## Data
- The v4 arm of research/nfl_tau_fade_rows.csv: probabilities averaged over seed sets A and B (10,000 simulations per snapshot), with outcomes.
- Before fitting, verify that the arm uses the corrected settings: 6 seeds to 2019 and 7 from 2020, neutral-site fix, sweep option off, tau 5.0, sigma 11.37, scale 0.89, no QB layer.
- The original 3,000-simulation corrected replay (research/nfl_futures_diagnosis_rows_format_fix.csv) is used only as a consistency check, never as an alternative chosen by which one passes.
- **Checkpoint w** means after all week-w regular-season results are known (week > w results masked). This is the same definition historically and live.
- **Cells:** division and make-playoffs, each after weeks 4, 8 and 12.

## Candidate (one form)
- **Slopes:** one per cell (six in all), no intercepts. Prior b ~ N(1, 0.25²) restricted to b > 0. Estimator: penalised maximum likelihood (MAP) of the final reconciled probabilities on binary outcomes, maximised over b in (0.05, 4).
- **Decided outcomes:** a v4 probability of exactly 0 or 1 (no simulation in 10,000 disagreed) is treated as decided and kept fixed. Such teams take no part in any rescaling.
- **Division:** q_i ∝ p_i^b within each division, summing to 1. Identical to v4 when b = 1.
- **Make-playoffs** (given the final division probabilities of the same snapshot):
  - q_i = logistic(b · logit p_i + c) for undecided teams, with one c per conference and snapshot.
  - c is solved by bisection so the conference's probabilities sum to its playoff spots (6 to 2019, 7 from 2020) minus the decided teams.
  - **Floor:** each team's playoff probability is at least its division probability. Deterministic reconciliation:
    1. Solve c.
    2. Any team below its floor is set to the floor and removed from the free set.
    3. Re-solve c for the free set with the remaining spots.
    4. Repeat until no team is below its floor.
- **Fitting order:** within each checkpoint, the division slope is fitted first (it affects only division probabilities). The playoff slope is then fitted given those division probabilities.
- **Identity check:** b = 1 for both markets reproduces the v4 probabilities within 1e-9, apart from the floor, which v4's own simulations already satisfy.
- These are coherent marginal probabilities for the two markets, not a joint distribution over playoff fields.

## Walk-forward
- For test season Y, both slopes per checkpoint are fitted only on completed seasons 2013 to Y - 1.
- Test seasons 2016-2025 (ten seasons; the first fit uses 2013-2015).
- Priors, transforms, reconciliation, scoring weights and gates are fixed. No choice among alternative forms (shared slope, week-4 only, etc.) after results.

## Scores
- **Per test season:** mean team-level binary log loss in each of the six cells (probabilities clipped to [0.001, 0.999] only for scoring); the six cells averaged equally.
- **Primary score:** the ten seasons averaged equally.
- **Gain** = v4 loss - recalibrated loss (positive = better).
- **Bootstrap:** whole paired seasons (all teams, markets and checkpoints together), 10,000 draws, seed 20261026. It summarises variation in the historical walk-forward results; it does not fully account for model-selection exposure.
- **Also reported:**
  - each cell's gain, and each checkpoint's 2020-25 gain;
  - leave-one-season-out primary gain, including dropping 2025 (a diagnostic, not permission to remove a season);
  - pooled walk-forward calibration slope and intercept per cell, with intervals and sample sizes;
  - fitted slopes per season;
  - Brier score.

## Gates (all must hold)
1. Primary gain: one-sided 90% bootstrap lower bound > 0, and positive in at least 7 of 10 test seasons.
2. Aggregate gain positive separately for division and for make-playoffs.
3. Aggregate primary gain positive in 2020-25 (an exposed subgroup).
4. No cell worse than v4 by more than 0.002 log loss (equal-season weighting).
5. **Guardrail:** pooled walk-forward recalibrated slope in every cell within 0.80-1.25. An undefined or unstable slope makes the result inconclusive.

Seven of ten seasons is a consistency check, not strong evidence by itself.

## Decision
- **Pass:** refit once on 2013-2025 and freeze the specification.
  - Shadow forecasts are issued only at the tested checkpoints (after weeks 4, 8 and 12); unchanged v4 at every other time.
  - Archived beside v4 and scored against Polymarket. Any 2026 checkpoint already past is labelled retrospective.
  - Before the forward run, a separate note fixes the evaluation dates, executable-price timestamps, fees and settlement treatment.
  - Promotion needs later archived evidence with production inputs (QB layer).
- **Fail (any gate):** recorded; this candidate stops without changing scope or gates. The betting number stays v4.
- **Inconclusive:** recorded; no change.
- The 10% expected-value threshold is an operating policy that this test does not validate. No profit claim.
- **Scope:** a QB-free layer tested on QB-free probabilities; it does not establish that applying it to full production probabilities improves them.

## Outcome (26 Oct 2026, Sydney): FAIL on all five gates. Candidate stopped.
Run: research/nfl_recalibration_test.py; results in research/nfl_recalibration_results.json; predictions in research/nfl_recalibration_predictions.csv.
- **Checks:** identity reproduces v4 (max difference 2e-16). No floor violations in v4. The first run stopped at the identity check because of a grouping bug (fixed before any result was produced).
- **Primary gain** -0.0005; one-sided 90% lower bound -0.0086; 6 of 10 seasons better.
  - By season: 2016 +0.007, 2017 +0.017, 2018 +0.005, 2019 +0.006, 2020 +0.014, 2021 -0.006, 2022 -0.004, 2023 -0.003, 2024 +0.014, 2025 -0.055.
- **By market:** division -0.0006, make-playoffs -0.0005.
- **By cell:**
  - week 4 helps: division +0.0030, make-playoffs +0.0030;
  - weeks 8 and 12 hurt: division -0.0008 / -0.0039, make-playoffs -0.0025 / -0.0019.
- **2020-25:** -0.0066 overall (week 4 +0.0022, week 8 -0.0137, week 12 -0.0084).
- **Pooled slopes, v4 -> recalibrated:** division 1.39 / 1.22 / 0.90 -> 1.11 / 0.89 / 0.80 (weeks 4 / 8 / 12); make-playoffs 1.26 / 1.14 / 1.06 -> 1.03 / 0.86 / 0.85. The week-12 division slope (0.797) breaches the 0.80 guardrail.
- **Consistency check** (3,000-simulation replay): same verdict, primary gain -0.0005.
- **Reading:**
  - Sharpening v4's probabilities helps at week 4. At weeks 8 and 12 it over-corrects, most in recent seasons; v4's mid-season caution in older seasons doesn't carry into recent ones.
  - 2025 is again the largest loss.
  - No week-4-only version is tried in response; the rule forbids choosing a form after results.
  - The betting number stays v4, with the 10% expected-value operating threshold.
