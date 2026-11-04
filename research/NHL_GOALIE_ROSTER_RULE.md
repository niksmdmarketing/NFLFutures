# NHL starter-goalie roster component: fixed-scale research rule

Written 5 November 2026 (Sydney), before generating or inspecting this comparison. Report only; no live change.

## Comparison fixed in advance
Baseline first: the live RAPM-skater replay settings: NHL_SHOT_W=1, NHL_SHOT_PO=1, NHL_RS_SHOT_W=0.2, NHL_XG=adj, NHL_PO_FADE=3, NHL_LINEUP_C=1, NHL_LINEUP_N=5, NHL_LINEUP_PRE=0, NHL_LINEUP_VAL=rapm, NHL_LINEUP_GS=0, RAPM_LAM=300000, RAPM_KBOX=1. All other research options off/default; 2,000 simulations, existing replay seeds.
Variant: exactly the baseline except NHL_LINEUP_GS=0.438, fixed to SCALE_G, with starter GSAx per unblocked shot times the existing 40-shot conversion. No parameter search or in-season goalie-rating refit. This is distinct from NHL_GOALIE_INSEASON_RULE.md.

Seasons: 2014–2018 and 2021–2025 (start-year labels; 10 complete normal-alignment seasons). Existing weekly checkpoints, before-cutoff lineup information only. Player ratings for season y use seasons earlier than y. Never replace missing RAPM data with points/GSAx silently. Both arms must use identical team/checkpoint/outcome keys, complete seven markets, identical inputs and simulation settings. Missing required inputs block the comparison rather than redefine the sample.

## Scoring and gate
Run research/nhl_holdout.py BASELINE VARIANT in that order. Binary log loss clipped to [0.002, 0.998], equal weight to each season and each of playoff, division, Presidents, round 2, round 3, conference and Cup. Gain = baseline minus variant. Combined 90% season-bootstrap interval: 4,000 draws, seed 1. Pass only if its lower bound is strictly above zero AND every market mean gain is at least -0.0005. Report per-season and per-market results and both gates, regardless of outcome. No minimum number of winning seasons added. No selection or alternative scales after seeing outcomes.

## Operational and interpretation limits
This isolates the roster component in the existing historical replay, which has no dated injury archive. It does not establish the complete live injury-adjusted pipeline or a betting edge. The 0.438 scale was fitted using overlapping historical seasons, so this is development evidence, not untouched validation. Starter means the recorded starter in already-completed games used to estimate the recent lineup; no future game's actual starter is used. No live model, forecasts, website, workflows or adoption policy change. Preserve input hashes and exact code identity. Commit this rule before running.
