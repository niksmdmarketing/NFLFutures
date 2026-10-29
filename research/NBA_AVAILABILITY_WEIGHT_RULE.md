# Availability baseline weight 4 versus 8 — registered 29 October 2026

No original preregistered gate exists for the team's 4→8 deployment. Its
reported 90% interval crossed zero. Do not call the new comparison the same
validated test, and do not count TypeSafe percentages as statistical evidence.
This rule is committed before candidate outcome scores are calculated.

## One candidate and fixed comparison

Freeze all settings. Team fit current-season weight stays 8; decay .2; ridge
24; availability value BETA .45; owner overrides off; no roster/RAPM layer in
this limited historical replay. Only nba_avail.RATING_W[0] changes 4→8, with
older weights unchanged. Rebuild player availability from earlier box scores
at every checkpoint; aggregated weight-4 adjustments cannot be reweighted.

Use research/nba_avail_futures_test.py's synthetic Out inference (last 5 games,
15 for long-term), not invented historical return estimates. That test's claim
to be a lower bound is unsupported. This is an undated, team-engine research
comparison and cannot establish an improvement to the complete live pipeline.
nba_return_test.py changes return-time distributions and is not the baseline
weight test; leave its fitted return parameters unchanged.

Seasons 2013–2026; exclude bubble 2020. Primary excludes shortened 2021;
report 2021 separately and in sensitivity. Checkpoints 20/40/60/80% on the
existing replay's league calendar, using only regular-season box scores up to
that checkpoint. Era-aware simulation: no play-in before 2021, 72 games in
2021 and 82 otherwise. Both variants have identical team ratings and schedules.
Future game outcomes are hidden during fitting. Official reports are not inputs
to this synthetic test. No fitting/tuning of the one candidate on test outcomes.

Two fixed seeds: 20261029 and 20261030, 2,000 simulations each per variant per
checkpoint. Modify no source defaults; reset the local RNG for each call by
temporarily supplying that seed to the simulator's default_rng constructor.
Same seeds are not a claim of common random numbers; report each seed and
gate the averaged probabilities, with a seed-direction robustness check.

## New gates, fixed now

Score binary log loss separately for playoffs, conference, title, with clipping
at .002/.998 as in the earlier synthetic test. Primary score is equal-market,
equal-season, equal-checkpoint mean. Difference = old loss minus candidate loss.
Resample whole primary seasons 10,000 times, seed 20261029; require the 95%
interval entirely above zero, improvement in at least 8 of 12 primary seasons,
no market's average loss worse, and positive combined gain for both simulation
seeds. Sensitivity including 2021 must have positive combined gain.
Missing required data makes the test incomplete, not a pass on fewer seasons.

Calibration/Brier changes, checkpoint losses, episode counts and all-season
results are reported as diagnostics. If any gate fails, retain weight 4. Even
if all pass, this is candidate evidence only; full-pipeline and prospective
validation still precede any live change. No deployment in this branch.

## Separate deployment review, protocol only

Also preregister the team's current-season fit weight 4 versus 8 with the same
seasons, era handling, cutoffs, seeds, markets and gates above, availability
weight held at 4 and other layers identical between variants. Regenerate both
sets; committed weekly CSVs are weight 8 and do not preserve the counterfactual.
This second experiment is not run as part of the availability-only comparison.
Its historical seasons are development evidence because the earlier grid and
deployment already used them. Preserve the existing live setting meanwhile.
