# AFL: current model vs team-stats model vs player model. Rule written BEFORE any result (19 Oct 2026)

Asked by the user ("Let's do AFL from scratch"): does the depth of Wheelo team and player data beat the current AFL rating? TypeSafe settled the design questions (19 Oct 2026): pass/fail on strictly pre-game lineups (80%), each challenger primary with a correction for three tests (53%), every game from the opening round on (67%).
Data: the clean tables built by research/afl_data_build.py from Wheelo round files 2012-2026 (3,097 matches). Raw and clean Wheelo data stay on the user's computer; only code and derived numbers are committed.

## Point in time
Matches are ordered by (season, round). Every match of round r is predicted only from matches in earlier rounds of the same season and from earlier seasons. Wheelo values are post-game, so a round's values may be used from the next round on. The opening round (round 0, from 2024) and round 1 are predicted from pre-season information (plus round 0 results for round 1). Finals are predicted the same way. No venue data: the listed home team gets the home term, as in the live model. Draws count as half a win in log loss.

## Models
**A - current live model, unchanged** (pipeline/afl_site.py as of 19 Oct 2026): opponent-adjusted margin rating (srs) with home advantage 7, prior = 0.65 x last season's full-season srs, prior weight 12 games, game sd 32. No tuning.

**B - team-stats model.** For each of 12 stats fixed now - ShotsAtGoal, Inside50s, TotalClearances, CentreClearances, ContestedPossessions, GroundBallGets, MetresGained, Marks, InterceptMarks, Intercepts, Tackles, DisposalEfficiency - the per-match differential (home minus away) gets an opponent-adjusted team rating with the same machinery as A (ridge with a free home term, prior 0.65 x last season's end rating, prior weight 12 games). Predicted margin = intercept + ridge regression on the 12 rating differences (home minus away). The regression is fitted on the point-in-time predictions for 2013-2018; its ridge penalty is chosen by leave-one-season-out within 2013-2018 from {1, 10, 100, 1000} (stats standardised on 2013-2018). Expected score is not used (it only exists from 2021 and has its own shadow; research/AFL_WHEELO_XSCORE_RULE.md).

**C - player model.** Each player-game value v = Wheelo RatingPoints (2020 values x 1.25 for the 16-minute quarters). A player's rating before a round = decayed mean of his earlier game values, weight 0.5^(games ago / H), shrunk toward a replacement value R with n0 pseudo-games: (sum w v + n0 R) / (sum w + n0). R = mean value of players' first 5 career games, computed on 2013-2018. Ratings follow the player, not the team, and carry across seasons. H in {5, 10, 20, 40} and n0 in {2, 5, 10} are chosen on 2013-2018 by margin MSE. Team strength = sum of ratings over the lineup. Predicted margin = h + beta x (strength_home - strength_away), h and beta fitted on 2013-2018.
- Pass/fail lineup (strictly pre-game): the players who played in the team's previous match (for round 0/1 that is last season's final match, so trades and retirements are not seen; a known weakness).
- Best case, reported only: the players who actually played.

**D - combined.** Predicted margin = h + wA x (A's margin minus home term) + wB x (B's margin minus intercept) + wC x (C's margin minus h), weights fitted by least squares on 2013-2018 point-in-time predictions; C uses the pre-game lineup.

Win probability for B, C, D = Phi(margin / sd), sd = that model's margin RMSE on 2013-2018. A keeps sd 32.

## Test
2012 is warm-up only (priors, player history). Tuning seasons 2013-2018. Test seasons 2019-2026 (8 seasons, about 1,650 games; 2020 shortened, kept and flagged). Every test game is scored, all models on identical games.

## Gates (each of B, C, D against A, all six must pass)
1. Pooled margin MSE below A, with a season-bootstrap (2,000 draws) one-sided interval at 98.33% (the 5% one-sided level divided by 3 for three challengers) above zero.
2. Better than A in at least 6 of the 8 test seasons.
3. Better than A in both early (rounds 0-8) and later (round 9 on, finals included) games.
4. Pooled log loss below A.
5. Calibration slope (actual margin on predicted margin) between 0.8 and 1.2.
6. Gain still positive without 2020.
Reported, not gated: C and D with actual lineups; finals alone; gain by round block; B's stat weights; C's chosen H and n0; D's weights.

## Decision
TypeSafe decides. A challenger that passes may go into the 2027 AFL build (March) as a shadow challenger against A; if several pass, TypeSafe is asked which. Failures are recorded and stay unused. No change to the live AFL page before the 2027 season either way.

## Outcome (19 Oct 2026) - combined model D passes; team stats alone and players alone fail
Run: research/afl_three_way_test.py (a `--mechanics` plumbing run on the tuning seasons came first; test seasons untouched until the full run). Results: research/afl_three_way_results.json. 1,649 test games, 2019-2026.
Tuning choices: B ridge penalty from leave-one-season-out; C half-life H = 20 games, n0 = 10 (n0 at the edge of its grid; not re-tuned); D weights h 6.45, current rating 0.00, team-stats model 0.81, player model 0.29.

| Model | Margin MSE | Gain vs A | Seasons better | Log loss | Gates |
|---|---|---|---|---|---|
| A current live | 1116.7 | - | - | 0.5880 | - |
| B team stats | 1110.1 | +0.6% | 4 of 8 | 0.5884 | fail (1, 2, 4) |
| C players (previous-match lineup) | 1190.7 | -6.6% | 0 of 8 | 0.6138 | fail |
| D combined (previous-match lineup) | 1087.0 | +2.7% (lower bound 10.8 points) | 7 of 8 (2019 worse) | 0.5843 | **pass all six** |
| Best case: D with actual lineups | 1077.5 | +3.5% | 7 of 8 | 0.5852 | reported only |

D: gain 36.7 early (rounds 0-8) and 25.9 later; slope 0.99; gain without 2020 30.0.
Reading: neither the stats nor the players beat the current rating on their own, but together they do, and once they are in, the current margin rating adds nothing (weight about 0). The player model on its own is poor because Wheelo rating points measure involvement more than winning impact; it helps as a second opinion on who is on the park.
Decision (TypeSafe 99%): D goes into the 2027 AFL build as a shadow challenger beside the current model and the expected-score shadow (research/AFL_WHEELO_XSCORE_RULE.md); B and C alone stay unused. No change to the live AFL page before the 2027 season.
