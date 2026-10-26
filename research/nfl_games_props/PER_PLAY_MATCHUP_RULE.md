# NFL per-play matchup features for team pass attempts. Rule written BEFORE code or results (26 Oct 2026, Sydney)

Asked by the user ("Do it", 26 Oct 2026, 13:37), following the critique of GPT/Codex's team-margin interaction study.
- TypeSafe ranked this the next test (71%).
- TypeSafe chose the two-stage structure (99%), 300 pseudo-dropbacks (71%), and that both the team-attempt RPS and log score must improve (99%).
- One candidate. No tuning after results. Research only: no live change, no betting edge claimed.

## Why
- Every prop distribution is built on the team pass-attempt forecast.
- The current volume model (7 features: own/opponent attempts, own/opponent plays, own pass EPA, opponent pass-defence EPA, Elo gap) has no protection/sack information and no success-rate matchup.
- GPT's study tested centred saddle products at the game-margin level. This test instead combines offence and opposing-defence per-dropback rates directly, and measures whether that helps the quantity props depend on.

## Data and timing
- **Source:** free nflverse play-by-play, regular season. Plays: play_type pass or run, EPA present, no two-point attempts, as in team_pbp. Dropbacks: qb_dropback == 1. Sack: sack == 1 on a dropback. Success: success == 1 on a dropback.
- **Per team-game:** offence counts (dropbacks, sacks, successes) and the same counts allowed by the defence.
- **Pre-game trait for a team:**
  - Built from the team's last 20 games in the current and previous season, with exponential game weights (half-life 5).
  - A game counts only once kickoff + 6 hours is before the target cutoff (kickoff - 1 hour).
  - Rate = (Σ w·events + 300·L) / (Σ w·dropbacks + 300), where L is the league rate of the previous full season.
  - Offence traits: sack rate allowed, success rate. Defence traits: sack rate generated, success rate allowed.
- These are revised current nflverse files, not original publication vintages. The 2021-2025 seasons were used in earlier props research.

## Stage 1: combination form (development seasons only, 2013-2020)
For each rate (sack; success), with y events out of n dropbacks for an offence team-game, offence trait O, opposing-defence trait D and league rate L:
- **Additive:** p = clip(L + a + b_o(O - L) + b_d(D - L), 1e-4, 1 - 1e-4).
- **Log5 (odds scale):** logit p = logit L + a + b_o(logit O - logit L) + b_d(logit D - logit L).
- Fitting: binomial maximum likelihood, walk-forward (train 2010..s-1, test s, for s = 2013..2020).
- Choice rule per rate: log5 if its mean-season out-of-sample binomial log-likelihood per dropback is higher; otherwise additive. This fixes the form only; it is not a deployment decision. 2021-2025 is not used in stage 1.

## Stage 2: team pass attempts (primary, 2021-2025)
- **Baseline:** the research volume model exactly as in the props tests. Features C.VOLUME_FEATURES; model('volume') (standardised Poisson regression, alpha 0.1); trained on 2018..s-1 rows with actual attempts > 0; NB dispersion by C.fit_nb; pmf C.nb_pmf(clip(mu, 5, 70), dispersion, 100). It must reproduce the matchup test's baseline team pmfs.
- **Candidate:** baseline features plus two: the expected sack rate and expected success rate for the team's offence against the opponent's defence. Each comes from the stage-1 chosen form, with its coefficients refitted walk-forward on 2010..s-1. Everything else is identical.
- **Rows:** team-games of season s with actual attempts > 0.
- **Scores:** team-attempt RPS over the full 0-100 support; NB log score; randomised PIT; mean error.

## Gates (all must hold)
1. Team-attempt RPS better: positive paired season-block lower bound (C.season_bound) and better in at least 4 of 5 seasons.
2. Team-attempt log score better: positive paired season-block lower bound and better in at least 4 of 5 seasons.
3. Every candidate PIT decile within 0.07-0.13.
4. **Downstream receptions:** the receptions RPS of the props baseline receiver construction (matchup_test.py baseline: no matchup factor) using the candidate team pmf. It must be no more than 0.1% worse than with the baseline team pmf.

QB pass attempts are not scored separately: the QB first-role data is not in this environment. The QB forecast is a fixed share of the team pmf, so gates 1-2 carry it.

## Decision
- **Pass:** a v1.3 candidate (v1.1 team volume plus these two features), archived forward as a shadow by a separate decision. It is not displayed until forward review.
- **Fail:** recorded; this branch stops. No other forms, windows, shrinkage or feature sets are tried in response.

## Outcome (26 Oct 2026, Sydney): FAIL. Branch stopped.
Run: per_play_matchup_test.py, results in per_play_matchup_results.json (team-games 2021-2025).
- **Baseline reproduction:** receptions from the baseline team pmf matched matchup_test.py's baseline exactly (27,614 of 27,614 rows, max difference 0).
- **Stage 1 (2013-2020):** the additive and log5 forms are indistinguishable (log-likelihood per dropback differs by about 1e-6). The rule chose additive for sack rate and log5 for success rate.
  - Fitted weights, descriptive only: offence about 1.17 (sack) and 1.33 (success); opposing defence about 0.37 (sack) and 0.87 (success).
  - So sack rate is mostly the offence's own trait, and the defence's sack generation adds little.
- **Stage 2, team attempts:**
  - RPS 0.043306 -> 0.043304, gain +1.6e-6, season lower bound -6.4e-5, better in 3 of 5 seasons.
  - Log score 3.45911 -> 3.45896, season lower bound -0.0013, better in 3 of 5 seasons. 2025 was worst on both.
- **Gates:** 1 FAIL, 2 FAIL, 3 pass (PIT), 4 pass (receptions +0.008%, within 0.1%).
- **Reading:** the per-play sack and success matchup adds nothing measurable to team pass attempts beyond the current seven features, and probably little if any value is hiding there. Additive versus multiplicative combination makes no practical difference at these rate levels. No v1.3. No further forms, windows or features are tried in response.
