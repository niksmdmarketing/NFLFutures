# AFL: does adding expected scores to the combined model make it the best? Rule written BEFORE any result (20 Oct 2026)

Asked by the user: put all three together (team stats + players + Wheelo expected scores) and, if it is the best model, make it the live AFL model.
Builds on research/AFL_THREE_WAY_RULE.md (models A, B, C, D unchanged, same code and weights) and research/AFL_WHEELO_XSCORE_RULE.md.

## New pieces
- X rating: opponent-adjusted rating on the expected-score margin (xScore home minus away), same machinery as B (free home term, prior 0.65 x last season's end rating, weight 12 games). Expected scores exist from 2021 only, so the 2021 prior is zero. The three 2024 round-23 games with no xScore use the actual margin in place of the expected margin.
- E (all in): predicted margin = h + wB x B' + wC x C' + wX x X', where B' and C' are B's and C's margins without their intercepts (C with the previous-match lineup) and X' is the X rating difference. Weights by least squares on 2021-2022 point-in-time predictions (the only seasons with expected scores before the test). sd = E's margin RMSE on 2021-2022.
- D is left exactly as fitted on 2013-2018.

## Test
Test seasons 2023-2026 (about 820 games), identical games for every model. Low power: 4 seasons.
Gates for E against D (the current best) and, separately, against A (the live model). All must pass against D for E to be called the best:
1. Pooled margin MSE lower, with a round-bootstrap (2,000 draws, whole rounds resampled) 90% one-sided lower bound above zero.
2. Better in at least 3 of the 4 test seasons.
3. Lower log loss.
4. Calibration slope 0.8-1.2.
Reported, not gated: early and later rounds; E's weights; all models' MSE on the test games, including the earlier 50/50 expected-score mix.

## Decision
"Best model" = E if it passes all four gates against D; otherwise D (which already passed its own test). The user has said the best model should be the live AFL model; TypeSafe is asked how and when, given that the site build cannot hold Wheelo data.

## Outcome (20 Oct 2026) - adding expected scores helps a little, not enough to be called better; D stays the best
Run: research/afl_all_in_test.py, results research/afl_all_in_results.json (866 test games, 2023-2026; the three-way code was refactored into a predictions() function first, and its results were checked to be identical).
E weights (fitted on 2021-2022): h 4.28, team stats 0.44, players 0.35, expected scores 0.39.

| Model | Margin MSE 2023-26 | Log loss |
|---|---|---|
| A current live | 1150.5 | 0.5693 |
| B team stats | 1143.0 | 0.5727 |
| C players | 1218.3 | 0.5943 |
| D combined | 1112.1 | 0.5663 |
| E all in | 1108.3 | 0.5619 |

E vs D: gain 3.8 (0.3%), 90% lower bound -5.4, better in 2 of 4 seasons; log loss and calibration pass; gates 1 and 2 fail. E vs A: passes all four (gain 3.7%).
By the rule, D is the best model. E is effectively tied with D; it is reported, not adopted. Its weights rest on only two fitting seasons.

## Going live (20 Oct 2026)
User: the best model should be live. TypeSafe (99%) on how: now, using only a derived ratings file. research/afl_model_d_ratings.py rewrites D as one rating per team plus a home term (checked: identical to the test's D predictions on 36 past games, max difference 0.0) and writes pipeline/afl_model_d_ratings.json (team ratings only, no Wheelo data). pipeline/afl_site.py futures now use D when that file is for the current season and covers every round already played; otherwise it falls back to the previous margin model automatically and says so. The previous model's rating is shown beside D's as "Old rating".
In season: after each round, stage the new Wheelo round file, rebuild the clean tables, run `python research/afl_model_d_ratings.py <clean_dir> --before <season> <next round>` and commit the ratings file. If that is missed, the page falls back to the old model until it is done.
The expected-score shadow (E, and the 50/50 mix) is still scored after 2027 alongside D.
