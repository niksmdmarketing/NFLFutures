# NFL ratings: shift weight from points margin to play efficiency. Rule, version 1

Written 5 Nov 2026 (Sydney), before any variant weights were fitted or any result was seen. Amendments are added below with dates; nothing above them is edited.

## Why
- Today's v4 ratings put 51% of the spread on this season's points margin (SRS) and 16% on last season's. Play efficiency (pass/rush EPA and success, sacks, special teams) carries about 15% combined (measured 5 Nov 2026).
- The weights were learned on 2010-2021 game margins. Margin and efficiency are strongly correlated, so that fit cannot cleanly separate them. The game has also changed since then.
- Public NFL analytics generally finds efficiency more stable than margin. If the market leans on margin, a model that leans on efficiency could find value.
- TypeSafe: leave the fitted weights alone (78%); if one reweighting is tested, this was the runner-up (16%) after the NHL goalie (64%). The owner asked for it.

## Variant (fixed before fitting)
- **E50 (primary):** both SRS weights (c_srs, p_srs) = 0.5 x frozen v4. The 24 efficiency weights are refitted on 2010-2021 regular-season game margins, with the halved SRS term held fixed as an offset. The fit uses the same point-in-time features and ridge alpha as research/nfl_walkforward_weights.py, plus an intercept.
- **E0 (reported only):** SRS weights 0, efficiency weights refitted the same way.
- Everything else is as frozen v4: pseudo-counts k, r, the sd scaling, rating_scale 0.89, tau, sigma, hfa, and the final-week rest penalty (17.891) in both arms. No re-tuning.

## Test seasons
2022-2025 only (the weights never saw them). The simulation spread (tau/sigma) was tuned on 2022-2025 win totals, and scale/hfa on 2018-2025. Both arms share those settings, so the comparison is fair but not fully unseen.

## Stage 1: games (2022-2025 regular season, weeks 2-18, point-in-time features)
- **Reported:** margin RMSE for frozen v4 vs E50 (and E0), per season.
- **Reported:** win-probability log loss using sigma 13.4, and the least-squares blend weight on each model next to the closing spread.
- **Gate:** E50 margin RMSE no worse than frozen v4 overall.

## Stage 2: futures (research/replay_nfl.py)
- Checkpoints: before the season and after every week, 2022-2025, 4,000 simulations, BT_REST=1 in both arms. Coefficients come from a file (BT_COEF_FILE).
- Markets: division, playoff, No. 1 seed, conference, Super Bowl. Gain = baseline log loss - variant log loss (clipped 0.002-0.998), mean over checkpoints per season, then averaged over seasons.
- **Pass:** combined mean gain > 0 with its 90% season-bootstrap lower bound > 0 (4,000 draws, seed 1); better in at least 3 of 4 seasons; no market's mean gain below -0.0005; and the Stage 1 gate met.

## Decision
- **Pass:** E50 runs as a shadow beside v4 for the rest of 2026 and is archived every refresh. It is forward-scored before any live decision. v4 stays frozen.
- **Fail:** recorded; nothing changes.
- E0 cannot pass or rescue a fail; it is reported to show the direction.

## Limits, stated now
- Four test seasons is a small sample, and the season bootstrap is coarse.
- The offline script that trained v4 is not in the repo. The walk-forward reconstruction matches the frozen weights only loosely (correlation 0.66). E50's efficiency weights therefore come from the reconstruction pipeline, while the baseline is frozen v4 as live.

## Result (5 Nov 2026): FAIL
research/nfl_efficiency_weight_test.py and research/nfl_efficiency_weight_results.json.
- **Stage 1 (1,023 games, 2022-2025, weeks 2-18):** margin RMSE v4 12.863, E50 12.883, E0 12.919. E50 is better only in 2022; the gate is not met.
    - On the training seasons (2010-2021) E50 fits slightly better (13.508 vs 13.523). The improvement does not carry over to unseen seasons.
    - The closing spread is better than every arm (RMSE 12.389). Next to it, the blend weight on every arm is about 0.
- **Stage 2 (futures, 4,000 sims, BT_REST=1):** combined gain +0.0004 (90% -0.0033 to +0.0037), better in 3/4 seasons.
    - Division -0.0028 and playoff -0.0035 are below the -0.0005 limit. No. 1 seed +0.0058, conference +0.0009, Super Bowl +0.0014.
    - 2025 is -0.0063.
- **Decision:** fail on both stages. Nothing changes; no shadow.
