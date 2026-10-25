# Role versus production: two small NFL experiments

Written before running this extension. Local research only. Preserve prior forecasts, live model, website and workflows. No market inputs.

## Shared design

Use the existing 2020–2024 timestamp-screened injury-player table. Test 2021–2024, fit every parameter on preceding seasons only; retain the prior prototype's team-attempt volume trained on earlier 2018+ seasons. The injury-aware involvement forecast is common to baseline and challenger. Conditional-on-involvement scores are primary: improvements must not come solely from treating DNPs as zero. These are revised-data development comparisons, not untouched holdouts or verified original-vintage injury archives.

Role means expected workload, not ability. For attempts there is no player conversion skill term: QB style can affect team attempt volume, but this test holds that volume fixed. For receptions, target share is role; catch probability is the separate existing smoothed player production estimate and remains unchanged.

## QB: primary-passer mixture

Current baseline blends historical attempts/team attempts into one beta-binomial allocation. Challenger predicts whether a QB will be the primary passer, conditional on offensive involvement, and mixes two allocation distributions: primary passer versus relief/other role. This is not a claim of confirmed starting status. Actual most-attempts QB is an outcome label only, never a pregame feature.

Features: lagged historical attempt share, last available team-game QB share and primary-passer identity, snap/appearance history, whether the previous primary passer has an eligible Out/Doubtful report, own game/practice status. Logistic C=1 with training-only scaling/encoding. No threshold/feature search. The previous team game must finish plus six hours before the one-hour cutoff. Unknown reports remain unknown. Learn primary/relief mean attempt shares separately from earlier outcomes, shrink each by 100 team attempts towards 0.95/0.10, and fit their beta-binomial concentrations separately. These are marginal player distributions, not a joint QB substitution simulator.

Provide an explicit scenario function: if genuinely confirmed to have a primary role, mixture weight may be set to one. Do not use the actual game starter or eventual target-game attempts to set that weight in evaluation. Prior low backup workload must not determine primary-role mean. Preserve missing new-QB candidate coverage as a limitation; do not manufacture hindsight candidates.

## Receivers: missing-teammate target opportunities

Keep catch probability unchanged. For QB-excluded receiving candidates, compute unavailable target-share mass from other candidates' injury-aware involvement probabilities and historical target shares. Exclude the receiver's own unavailability when conditioning on him appearing. One pooled beta in [0,1], ridge penalty beta²/(2*0.5²), inflates existing target share by 1/(1-beta*other_missing_share), missing share capped 0.8. Fit target-count binomial likelihood on earlier involved players only. This allocates more to established target earners, not equal absolute targets to every player.

Use a common expected-target budget repair for both baseline and candidate: if summed involvement-probability-weighted target shares exceed one, rescale them to one. Report the frequency and score the original legacy baseline too; do not attribute budget repair to the absence term. Fit baseline and challenger count dispersion on their own preceding-season rates. The budget is in expectation; per-player marginal draws are not joint team allocations. Unseen/missing roster players remain an explicit residual opportunity bucket.

## Checks, reports and stop rule

Freeze comparison rows, formula-set lines and groups from the baseline: QB recent primary versus other; pregame prior-primary-Out cases; receivers with >=10% unavailable teammate target mass. Report actual primary changes only as hindsight diagnostics, not selection criteria. Report conditional and DNP-zero RPS, whole-distribution PIT, formula-line overs, means, per-season results and fixed subgroups. Use paired season bootstrap with the existing seed/4000 draws, one-sided 95% lower gain. Do not infer market edge.

Each experiment passes its research screen only if conditional RPS gain lower bound >0, improves >=3/4 seasons, unconditional RPS does not worsen, conditional PIT deciles are within 0.07–0.13 overall, and no prespecified subgroup loses more than 2% RPS. Otherwise retain the baseline. No alternate forms or tuning after results. Independent future forecasts remain necessary even after a screen pass.

Tests: current/future outcomes cannot affect role features; cutoffs and team IDs are respected; primary scenario restores a meaningful primary workload even after tiny backup history; mixture PMFs sum to one; receiver own missingness is excluded; expected target budget <=1; catch probabilities unchanged by redistribution. Save original inputs, parameters, code/rule hashes and paired scores privately.
