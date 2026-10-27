# NFL props: non-linear game script in team pass-attempt volume. Rule written BEFORE code or results (27 Oct 2026, Sydney)

Status: **final** (27 Oct 2026, 17:18 Sydney). GPT accepted the candidate with the clarifications frozen in the section at the end, which takes precedence; TypeSafe: freeze and run now (96%). Nothing had been run when this was committed.
- Asked by the user (improve NFL models; props game-script). TypeSafe: draft this refinement (58%; park props until props prices exist 36%).
- One candidate; no tuning after results.

## What exists
- **Team pass attempts** (the volume behind QB pass-attempt and receptions props) come from a negative-binomial model on seven features (research/nfl_games_props/core.py VOLUME_FEATURES). One of them, elo_gap (pre-game Elo difference / 400, home edge included), already carries game script, but only linearly.
- **Why non-linear:** big favourites run late and big underdogs throw late, and the relationship is plausibly curved, with close games near the league norm.

## Candidate (one form)
- VOLUME_FEATURES plus elo_gap², with everything else unchanged: the same ridge/Poisson volume model and negative-binomial dispersion fit, the same player allocation, and the matchup factor where v1.2 applies it.
- **Not in this rule:** replacing Elo with our own v4/v5 projected margin needs weekly point-in-time ratings for every past week. It is noted as possible later work.

## Test
- **Data:** research tables from research/nfl_games_props/build.py (teams.parquet, players.parquet), as in the receiver-allocation and matchup tests. These are revised nflverse vintages, a lagged retrospective test.
- **Folds:** walk-forward. Test seasons 2021-2025; for each, models are fitted on 2018 to the previous season (receiver_allocation_test's folds).
- **Baseline:** must reproduce receiver_allocation_test's challenger volume and reception scores on the same rows (identity check before any candidate score).
- **Scores:**
  1. **Team pass attempts:** RPS of the negative-binomial pmf (normalised at 100 attempts), log score, randomised-PIT deciles, mean error, and these split by |elo_gap| tercile.
  2. **Receptions:** the receiver test's conditional RPS, log score, PIT and the fixed groups.

## Gates (all must hold)
1. **Team-attempt RPS:** better than the baseline, with a positive paired season-block lower bound (C.season_bound) and better in at least 4 of 5 seasons.
2. **Team-attempt log score:** not worse.
3. **Every team-attempt PIT decile** within 0.07-0.13.
4. **Receptions:** RPS not worse than the baseline by more than 0.1%; log score not worse.
5. **Largest |elo_gap| tercile:** team-attempt RPS not worse.

## Decision
- **Pass:** a v1.3 shadow candidate (v1.2 + elo_gap²), archived forward under its own identifier by a separate decision, not displayed.
- **Fail:** recorded; stop this branch. No other forms (cubic, splines, interactions) are tried in response.
- No betting edge is claimed either way. There are no props prices to test profit.

## Clarifications frozen after GPT's review (before any code or score)
1. **Form and fit.**
   - **Curvature:** signed elo_gap plus elo_gap², the only form; |gap| is not tested or selected. The volume model is sklearn's PoissonRegressor (log link) after standardisation, so the curvature applies to log expected attempts.
   - **Refitting:** every fold refits the coefficients on its training seasons only, with the unchanged procedure (run.model('volume'), alpha 0.1). The negative-binomial dispersion is re-estimated by the unchanged procedure (C.fit_nb on that fold's training predictions), not copied.
   - **Range check:** predictions are clipped to [5, 70], as in the baseline. For each fold, predicted attempts are also reported over an elo_gap grid from -1.5 to 1.5 (other features at their training means), to check that the quadratic does not reverse or explode in the observed range.
2. **Scores and gates.**
   - **Gate 1:** positive aggregate team-attempt RPS gain (mean within season, seasons equally weighted), with a one-sided 90% paired season bootstrap lower bound above zero (10,000 draws, seed 20261027, the 5 season blocks), and improvement in at least 4 of 5 seasons. All five season gains and a leave-one-season-out summary are reported.
   - **Log score** = negative log probability; lower is better.
   - **PIT:** randomised count PIT with fixed random numbers shared across arms (seed 20261023).
   - **Gate 3:** applies to the pooled out-of-sample team-attempt PIT deciles (0.07-0.13). Season, tercile and reception-group histograms are descriptive, with sample sizes, and baseline PIT is shown beside the candidate's.
   - **Gate 4:** the relative deterioration in mean receptions RPS must be at most 0.1%, and the log score must not be worse. Eligibility, groups and weighting are frozen as in the matchup test's baseline rows (every receiver-game with an appearance and a known team attempt count, zero receptions included). Selection does not depend on realised receptions.
   - **Gate 5:** the highest absolute-gap tercile, with boundaries from each fold's training data; team-attempt RPS must not be worse. Signed-gap terciles (favourites, middle, underdogs) are also reported.
   - **Identity:** the baseline receptions scores must match the matchup test's baseline rows (/home/outputs/nfl_matchup_20261026/paired_scores.parquet) exactly before any candidate score is used. The scored observations are identical across arms, and the forecasts are analytic (no simulation noise).
3. **Projected margin:** a separate future candidate, not in this test.
4. **Downstream QB pass-attempt props (descriptive, not gated):**
   - Expected starters are QB rows with is_qb = 1 and an appearance.
   - Their pass-attempt pmf is a beta-binomial allocation of the team-attempt pmf, with a starting-role share and concentration fitted on that fold's training QB rows. This is the same construction for both arms.
   - RPS and log score are reported for each arm.
5. **Reading:** a pass supports the archived shadow; a fail rejects this candidate under these gates and does not show that linear Elo is optimal.

## Outcome (27 Oct 2026, Sydney): FAIL. Stop this branch; linear Elo stays.
Run: game_script_test.py; results in game_script_results.json; scores in /home/outputs/nfl_game_script_20261027.
- **Identity:** 27,614 of 27,614 baseline receptions rows matched the matchup test's baseline exactly (max difference 0).
- **Team pass-attempt RPS:** 0.043306 → 0.043291, an aggregate gain of +0.0000153 (about 0.04%).
  - One-sided 90% lower bound -0.0000105; better in 3 of 5 seasons (2021 -0.00002, 2022 +0.000004, 2023 +0.00005, 2024 -0.00004, 2025 +0.00008).
  - **Gate 1 FAIL.**
- **Gate 2 (team log score):** pass, 3.4591 → 3.4588.
- **Gate 3 (pooled PIT):** pass.
- **Gate 5 (largest |gap| tercile):** pass, 0.04266 → 0.04257.
- **Gate 4 (receptions):** RPS +0.003% (within 0.1%), but log score slightly worse (1.627731 → 1.627758). **FAIL.**
- **Shape:** the fitted curve is an inverted U on log attempts. Predicted attempts peak near a small favourite and fall at both extremes; for example, the 2025 fold gives about 32.5 at a gap of ±1.5 against about 34.1 near 0. The baseline is a slight upward line.
  - Underdog tercile RPS improved slightly; the middle got worse.
- **QB pass attempts** (descriptive): RPS 0.06973 → 0.06968.
- **Reading:**
  - Curvature in game script carries at most a tiny signal for team pass volume; it is not reliable across seasons and does not help receptions.
  - The candidate is rejected under these gates. This does not show that linear Elo is optimal.
  - No other forms are tried. Projected-margin replacement stays a separate future idea.
