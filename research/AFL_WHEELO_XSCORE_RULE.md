# AFL: do Wheelo expected scores (xScore) improve team ratings? Rule written BEFORE any result (19 Oct 2026)

TypeSafe (19 Oct 2026) listed this as the held AFL step. Wheelo data are used privately with the source's permission; raw files stay on the user's computer and are never committed. Only derived numbers appear here.

## Data and point in time
Wheelo match-stats round files (dynamic/match_stats/YYYYRR.json), seasons 2012-2026: for every match both teams' Score and xScore (Wheelo's expected score from shot quality), plus home and away team. These are post-game values, so a round's values may be used for any later round. A round is predicted only from earlier rounds of the same season and earlier seasons. Rounds are the time unit (match dates inside a round are not used). Finals are scored but follow the same rule.

## Models (all identical machinery; only the margin target differs)
Team rating = ridge regression of the match margin on team indicators (+1 home team, -1 away team) plus a home-advantage term, fitted on all earlier games of the season, with prior = c x last season's end-of-season rating of the same model (new teams 0).
- A (actual): margin = Score_home - Score_away.
- X (expected): margin = xScore_home - xScore_away, then rescaled by the factor s fitted on the tuning seasons (regress actual margin on xMargin, no intercept) so both are in points.
- M (mix): margin = 0.5 x actual + 0.5 x rescaled expected. The weight 0.5 is fixed now.
Hyperparameters ridge lambda in {2, 4, 8, 16, 32} and prior weight c in {0.4, 0.5, 0.6, 0.7, 0.8} are chosen on the tuning seasons 2013-2018 by margin MSE of model A only, then used unchanged for X and M. Win probability = Phi(predicted margin / sd) with sd per model fitted on the tuning seasons.
Last season's end-of-season ratings come from the same model run through that whole season.

## Test
Seasons 2019-2026 (2020 shortened, kept and flagged; 2026 is complete). Every game from round 2 on, predicted from the rating fitted on earlier rounds. Measures: margin MSE, win-probability log loss, calibration slope. Comparison M vs A (primary) and X vs A (reported). Season-level bootstrap (2,000 draws) for the pooled MSE difference.

## Gates (all)
1. Pooled margin MSE of M below A, 90% bootstrap interval above zero.
2. M better than A in at least 6 of the 8 test seasons.
3. M better than A in both early (rounds 2-8) and later (rounds 9+) games.
4. Pooled log loss of M below A.
5. Calibration slope of M between 0.8 and 1.2.
6. The gain without 2020 is still positive.
Reported, not gated: X alone vs A; gain by round block; the fitted rescale factor s.

## Decision
TypeSafe decides. Pass: expected scores go into the AFL rating build planned for the 2027 season (March), as a challenger shadow against the current model first. Fail: recorded; Wheelo xScore stays unused. No change to the live AFL page either way before the 2027 season.

## Amendment 1 (19 Oct 2026, written before any result): xScore only exists from 2021
Checking the staged files showed Wheelo's xScore is present only for seasons 2021-2026 (2012-2020 files carry Score but no xScore). The 2013-2018 tuning / 2019-2026 test split cannot be run for X and M. Changes, all fixed now:
- Ridge lambda and prior weight c are still tuned on model A only, on 2013-2018 actual scores (no xScore needed), using the same grids.
- The rescale factor s and the per-model sd are fitted on 2021-2022 (tuning seasons for X/M).
- Test seasons are 2023-2026 (4 seasons, about 860 games). The 2021 and 2022 seasons and 2020 are not scored. Prior for X and M in 2021 is zero (no earlier xScore season); from 2022 it is the prior-season end rating of the same model.
- Gate 2 becomes "M better than A in at least 3 of the 4 test seasons". Gate 6 (without 2020) is dropped as moot.
- Because 4 seasons make a season-level bootstrap meaningless, the bootstrap for gate 1 resamples whole rounds (2,000 draws) from the pooled test games.
- The result is labelled low power whatever the outcome: a pass means "worth a 2027 shadow", never "adopt".

## Outcome (19 Oct 2026) - passed all gates, low power
Run: research/afl_wheelo_xscore_test.py, results research/afl_wheelo_xscore_results.json. Tuned on actual scores 2013-2018: lambda 4, c 0.8 (c is at the edge of its grid; not re-tuned). Rescale s = 0.994. Three 2024 round-23 matches have no xScore in the source and were dropped from every model, so all models are scored on the same 812 games (2023-2026).
- Margin MSE: actual 1155.5, mix 1124.0, expected-only 1120.2. Mix gain 31.5 (round-bootstrap 90% interval 15.2 to 47.3).
- Mix better in 4 of 4 seasons (gains 18, 57, 16, 36), in early rounds (49) and later rounds (24).
- Log loss 0.5707 to 0.5608; calibration slope of the mix 1.03.
- Reported: expected-only is slightly better than the 50/50 mix, so the fixed 0.5 weight is not optimal; the weight stays fixed for the shadow and can be reviewed after the 2027 season.
Decision (TypeSafe 97%): run expected scores as a shadow challenger in the 2027 AFL build from March; no change to the live AFL page before then. Low power (4 seasons, one set of weights and hyperparameters), so a pass means "worth a shadow", not adoption.
