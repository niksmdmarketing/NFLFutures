# NBA early-season diagnostic: independent review, 5 November 2026

Target: WORKLOG entry in public 9b825fd, read at f5fcc9c. Diagnostic only, no model change. I agree with not retuning the model on this result.

## Exact numerical reproduction

Read nba_2013.csv through nba_2026.csv; select 5 <= gp_avg <= 20; join each season/team to week 0. Clip probabilities to [0.002,0.998] and select logit(current)-logit(preseason)>0.7. This reproduces every published cohort number:

| Market | Rows | Unique team-seasons | Predicted | Actual |
|---|---:|---:|---:|---:|
| Title | 169 | 71 | 15.160% | 15.385% |
| Playoff | 538 | 184 | 87.577% | 86.245% |
| No. 1 seed | 211 | 84 | 31.606% | 35.545% |
| Finals | 201 | 85 | 22.026% | 18.408% |

The two-logit regressions also reproduce the reported coefficients and ordinary standard errors: preseason coefficient title -0.04484 (SE 0.18526), seed1 -0.33521 (SE 0.15233); title calibration slope 1.24701.

## Qualification 1 — repeated checkpoints need clustered uncertainty

The quoted SEs match ordinary row-independent logistic-regression errors. The outcome repeats within team/season and outcomes are coupled across teams in each season. Treating rows as independent understates uncertainty.

A season-clustered sandwich calculation on the same regression gives preseason-coefficient SE **0.43345** for title and **0.33716** for seed1, rather than 0.185/0.152. Title slope's clustered SE is **0.22427**, so an approximate normal 95% interval includes 1 (roughly 0.81-1.69). There are only 14 season clusters; these robust errors are themselves approximate, not definitive proof of calibration.

The 169 title observations are repeated checkpoints from 71 team-seasons, not 169 independent title contests. Bootstrap whole seasons for any substantive confidence claim.

## Qualification 2 — describe what the test actually asks

- A logit increase of 0.7 means about a doubling of ODDS, not generally a doubling of probability. At a 50% prior it corresponds to about 67%, not 100%.
- gp_avg is league-average games played at a checkpoint, not every team's own games played. Say so.
- A pooled early calibration slope above 1 does not specifically prove that the reaction to new results is correct; it mixes priors, team strength and tail calibration. The conditional prior/current regression is more directly relevant, but still a development diagnostic.
- There is no clear broad over-reaction signal here, particularly for title. Finals is more overconfident in the selected group (22.0% vs 18.4%), so avoid a universal claim that every early market is conservative.
- These replay seasons were used in earlier model development/settings selection. This is not a fresh independent validation of the deployed weight 8, nor does it settle any particular team's roster/availability assumptions.

## Decision and reproduction

No calculation error found in the reported cohort figures. No model fix is justified solely by this diagnostic. Prefer: "This historical diagnostic did not show clear evidence for a general early-season shrinkage change," rather than "the model does not over-react."

The original WORKLOG entry did not include its executable calculation or clipping convention; this review preserves a standalone reproduction in research/review_20261105/reproduce_diagnostics.py and results in nba_early_diagnostic_reproduced.json. It records the exact sample, optimizer, naive errors and season-clustered errors. No forecast or model setting changed.
