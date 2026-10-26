# NFL futures: walk-forward recalibration layer for division and make-playoffs. DRAFT rule for review before any code or results (26 Oct 2026, Sydney)

Status: **draft, sent to GPT for review.** Nothing has been run. The final version will be committed before the test. Displayed v4 stays frozen.

## Why
- The uncertainty-schedule test (research/NFL_TAU_FADE_RULE.md) failed. It fixed v4's in-season caution, but the gain came only from 2013-19.
- The rule named this as the fallback, and it was TypeSafe's second choice (13%).
- Purpose: a better-calibrated betting number for division and make-playoffs during the season, used as a shadow beside v4.

## Disclosed exposure
- The v4 replay probabilities and their calibration slopes have been inspected:
  - all seasons: division 1.31 / 1.25 / 0.96 at weeks 4 / 8 / 12; make-playoffs 1.29 / 1.21 / 1.13;
  - 2020-25 alone: division 1.22 / 0.95 at weeks 4 / 8; make-playoffs 1.28 / 1.03.
- The uncertainty-schedule result is known.
- The baseline's settings were chosen on overlapping seasons.
- This is an exposed historical test, not an untouched validation.

## Data
- v4 probabilities from the v4 arm of research/nfl_tau_fade_rows.csv: seed sets A and B averaged (10,000 simulations per snapshot), with outcomes.
- Corrected playoff format (6 seeds to 2019, 7 from 2020); neutral-site fix applied; no QB layer.
- **Cells:** market (division; make-playoffs) × checkpoint (after weeks 4, 8, 12). Six cells.

## Candidate (one form; TypeSafe chose the options)
- **Per cell:** logit p' = a + b · logit p, with p clipped to [0.001, 0.999] first.
- **Fitting:** MAP on Bernoulli outcomes, with priors a ~ N(0, 0.5²) and b ~ N(1, 0.25²) (TypeSafe 63%).
- **Walk-forward:** for test season s, fit on all seasons from 2013 to s - 1. Test seasons 2016-2025, ten seasons (TypeSafe 45%).
- **Coherence (TypeSafe 89%):**
  - Division: renormalise the four p' within each division so they sum to 1.
  - Make-playoffs: add one common logit shift per conference (solved numerically) so the conference's probabilities sum to the number of playoff spots (6 to 2019, 7 from 2020).
  - The fitted (a, b) are those from the uncoherent fit; coherence is applied afterwards, for both fitting diagnostics and scoring.
- No other markets or checkpoints are changed.

## Scores
- **Per test season:** mean team-level binary log loss (probabilities clipped to [0.001, 0.999]) in each of the six cells; the six cells averaged equally.
- **Primary score:** the ten season values averaged equally.
- **Gain** = v4 loss - recalibrated loss (positive = better).
- **Bootstrap:** whole-season resampling, 10,000 draws, seed 20261026.
- **Also reported:** each cell's gain; calibration slope and intercept before and after (season-bootstrap 90%); Brier score; fitted (a, b) per season and cell.

## Gates (all must hold)
1. Primary gain: one-sided 90% bootstrap lower bound > 0, and positive in at least 7 of 10 test seasons.
2. Point-estimate gain positive separately for division (three cells) and make-playoffs (three cells).
3. Primary gain positive in 2020-25, reported as an exposed subgroup.
4. No over-correction: the recalibrated calibration slope in every cell within 0.80-1.25 over the test seasons.

## Decision
- **Pass:** a shadow betting number (v4 plus this layer).
  - Parameters are refitted on 2013-2025 once and frozen for 2026, with live checkpoints mapped to the nearest of weeks 4, 8 and 12.
  - It is archived live beside v4 and scored against Polymarket. Before the forward run, a separate note fixes the evaluation dates, the price timestamps, and the fee and settlement treatment.
  - Promotion needs forward evidence and a check with the production QB layer.
- **Fail (any gate):** recorded; this branch stops, and the betting number stays v4 with the 10% expected-value threshold.
- No profit claim either way.

## Questions for review
1. Is per-cell (a, b) with these priors right, or should the slope be shared across weeks within a market?
2. Is renormalising after the fit acceptable, or should coherence be built into the fit?
3. Does mapping a live week to the nearest checkpoint (4, 8, 12) need a stated rule for weeks 1-3 and 13+ (e.g. no recalibration outside weeks 3-14)?
4. Are the gates appropriate for ten exposed seasons?
5. Should the data be the averaged 10,000-simulation v4 arm, or the original corrected replay (3,000 simulations)?
