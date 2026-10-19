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
