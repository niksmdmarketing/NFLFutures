# NBA joint team-and-player estimate for futures. Rule, version 1

Written 5 Nov 2026 (Sydney), before any joint-model fit, hyperparameter selection or replay. Amendments are added below with dated headings; nothing above them is edited. A flawed run is recorded, not hidden.

## Question
Does estimating player and remaining-team strength together, in one fit that replaces the overlapping player adjustments, give better NBA futures probabilities than the complete live model?

Single-game results are supporting evidence only. The test is the futures replay: season simulation, play-in and playoffs.

## Why this experiment (audit, 5 Nov 2026, from the repo)
- Player-first alone lost to the team rating in 12 of 12 seasons (research/NBA_PLAYER_FIRST_SUMMARY.md). The combined player term beat the bare team rating by 0.93%, but against the complete live pipeline it gave no single-game gain (research/NBA_GAMES_PT_RULE.md, failed 21 Oct 2026: log loss -0.00076, better in 2 of 5 seasons). The roster step, pre-season RAPM mix and availability layer already carry most of that information.
- Futures: the first additive player term scored -0.0023. The corrected version (in season only, scale-preserving) scored +0.0010 (90% -0.0031 to +0.0050), better in 7 of 11 seasons, 2026 alone -0.020; recorded as a fail and archived as a futures-only shadow.
- The corrected version was in season only, so the crude pre-season lineup cannot explain its remaining 2026 loss (GPT, 5 Nov). Open hypotheses: double counting between the player term, the team rating and the roster step; scale; the in-season "last 10 games" lineup; unstable weekly RAPM refits. This rule tests the first two directly. It does not claim to know the cause.
- The possession simulator failure (margin sd 18.1 vs 15.4, score correlation 0.18 vs 0.26, overtime 2.2% vs 5.0%) concerns game margins, totals and props. It is out of scope here.
- TypeSafe (5 Nov 2026, choice of next NBA hypothesis): joint estimate replacing the roster step and pre-season mix 68% (confidence 0.57); fix only the pre-season lineup 18%; wait for forward evidence 9%; joint score-distribution model 5%.

## The model (structure fixed now)
Data: lineup stints from ESPN play-by-play as built by pipeline/nba_rapm.py (home five, away five, margin, possessions), plus the team each five belongs to, taken from the game's box score. Seasons used at a checkpoint in season K: K (games so far), K-1, K-2.

For stint s in season k, with y_s = 100 x margin / possessions:

    y_s = eta + sum over home five (beta_p) - sum over away five (beta_p) + tau[home team, k] - tau[away team, k] + error

- beta_p: player rating (points per 100 possessions vs an average player), as in the live RAPM.
- tau[t, k]: remaining team effect for team t in season k (coaching, system, combinations, anything the player ratings do not carry). One per team per season.
- eta: home-court intercept. Stints are weighted by possessions x w_k, with w_K = w_c (the current-season weight, selected below), w_(K-1) = 1.0, w_(K-2) = 0.5 (the live RAPM weights).
- Penalties (ridge): lambda_beta x (beta_p - mu_p)^2 with lambda_beta = 3000 and mu_p = 2.5 x the player's box-score value (the live prior, nba._roster_values); lambda_tau x tau[t, k]^2 for k < K; for the current season lambda_tau x (tau[t, K] - rho x tau[t, K-1])^2.
- How the two effects are separated: players who share minutes are not identifiable one by one, and neither is a player-sum against a team effect. The ridge decides. A large lambda_tau pushes everything into the players; a small one lets tau absorb whatever the roster does not explain. lambda_tau and rho are the two knobs and are selected out of sample (below). I report how much of rating spread comes from each part.

Team strength used by the futures simulator at a checkpoint (points per 100 possessions, centred, one number per team):

    rating_t = scale x [ sum over p on team t of ( beta_p + development_p ) x minutes_p / 48  +  tau[t, K] ]

- development_p: the live development bonus (+1 per season short of 4 seasons played), applied once, after the fit, to the players only.
- minutes_p (per team game, 12-man rotation, scaled to 240): (G x minutes per team game so far this season + 10 x projected minutes per game) / (G + 10), G = team games played, absences counting as zero minutes. Projected minutes = the live roster-step minutes (last season's minutes with the returning-player rule) / 82. 10 is fixed, not tuned.
- Players with no rating get the live rookie value (-1.0).
- scale: one scalar per test season, fitted only on earlier seasons by regressing the rest-of-season net rating on rating_t at checkpoints 0, 20 and 41 games. The baseline gets no such scalar (it is the live model as is). Results without the scalar (scale = 1) are reported next to the primary.

## What it replaces and what it keeps (no player adjustment is allowed to count twice)
| Live component | In the challenger |
|---|---|
| Team rating (ridge on points per 100, current season x8, decay 0.2) | Replaced. Team results enter through stints and tau |
| Roster step (box-score impact, coefficient 1.5 to 1.0 by game 20) | Removed. Box values survive only as the prior mean mu_p, once |
| Pre-season RAPM mix (40%, fading to 0 by game 20) | Removed. The joint estimate is used at every checkpoint |
| Development bonus | Kept, applied once, to beta only |
| In-season player-term shadow (research/NBA_PLAYER_FIRST_RULE.md) | In neither arm |
| Playoff rotation term (top-8 minutes, power 1.5, cap 42 mpg, last season's playoff/regular minutes ratio) | Kept as live, computed from the joint beta + development. It measures the change from regular to playoff rotation, not regular strength |
| Game-level injury adjustment | Untouched, out of scope (futures use none) |
| Owner overrides | Off in every replay, as live replays |
| Simulation settings (TEAM_TAU 2.2, TAU_PRE 2.0 to game 16, GAME_SIGMA 12.2, play-in, format by era) | Identical in both arms. These were tuned with the live ratings, which favours the baseline; no retuning |

## Historical roster and minutes construction (point in time)
- Information at a checkpoint is limited to games before it. Weekly checkpoints, as research/replay_nba.py.
- Team of record: pre-season, the first team a player appears for in season K, counting only appearances in that team's first 10 games (so mid-season signings are not in the pre-season roster); in season, the team he last played for before the checkpoint. This is the live replay's convention (research/replay_nba.py _season_extras) tightened by the 10-game window. Both arms use the same rosters and the same roster-step minutes.
- Known leak: the replay knows who actually played for a team early in the season, so a trade or signing that happens before opening night is known, as the live pre-season would know it, but players who missed the whole season are invisible. BT_FULL_NOLEAK=1 keeps such players on last season's team and bounds this. Sensitivity gate G6 below uses it.
- Rookies and players with no prior minutes: live rookie rating and live minutes treatment. No draft-position or contract data.
- No injury layer in either arm for futures (live futures use none). Hurt players count through their minutes so far.

## Selection of hyperparameters (grid fixed now; no other tuning)
- w_c in {2, 4, 8}; lambda_tau in {1000, 4000, 16000}; rho in {0, 0.5}. lambda_beta, the box prior, the development bonus and the possession weights are the live values (they were chosen earlier on the same seasons; a known limit).
- For test season Y, choose the combination with the lowest mean absolute error between rating_t (before the scalar) and each team's rest-of-season net rating, summed over checkpoints at 0, 20 and 41 games, over seasons 2014 to Y-1 only. Ties go to the larger lambda_tau, then the smaller rho.
- Test seasons: 2016-2026 except 2020 (the replay skips the bubble), which is 10 seasons. 2014-2015 are selection data only.

## Baseline (the complete current model)
- research/replay_nba.py with BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1, which reproduce the committed model/replay/nba_*.csv. Re-run fresh for the test seasons; the committed files are checked against it and any difference reported. The fresh run is the baseline.
- Same checkpoints, same schedule with later results hidden, same simulation seed and number of sims (BT_SIMS, default 2000) as the challenger, same outcomes (the y_ columns).

## Evidence standard
- 2015-2026 is development evidence that has already been explored many times (several player-term rules in sequence on the same seasons). Freezing this rule limits further adaptation but does not make those seasons untouched. A historical pass therefore only qualifies the challenger for a forward shadow. It never changes the live model by itself.

## Stage 1: single games (reported, not gated)
- Pre-game margin MSE and log loss for challenger vs the live team-plus-roster rating, 2016-2026, on identical games, by season and early/later games.

## Stage 2: futures (the gate)
- Markets: title, conference (reaches the Finals), division, No. 1 seed, playoffs. Gain = baseline log loss - challenger log loss (probabilities clipped 0.002-0.998), mean over checkpoints per season, then the mean of the five markets per season, then averaged over seasons.
- **G1:** combined mean gain > 0 with its 90% season-bootstrap lower bound > 0 (4,000 draws, seed 1).
- **G2:** better in at least 7 of the 10 seasons.
- **G3:** no market's mean gain below -0.0005.
- **G4:** 2026 is not worse than -0.005 (it stays in G1 and G2 either way). The corrected additive term lost 0.020 there.
- **G5:** by forecast stage (pre-season, games 1-19, 20-41, 42-end), no stage's mean gain below -0.002.
- **G6:** the NOLEAK roster variant has a combined mean gain above 0.
- Reported, not gated: results without the scalar; per season and per market; calibration slope by market and stage; rating spread of each arm; the share of the challenger's rating variance from player sum vs tau; mean absolute change in rating vs the baseline.

## Decision
- **All of G1-G6 pass:** the challenger qualifies for a forward shadow. It is archived at every refresh beside the live forecast, not shown on the site, for the rest of 2026-27, with its parameter file hashed. An adoption rule for the forward result is written, as an amendment, before the first forward score is read. No live change on historical evidence.
- **Any gate fails:** recorded as a fail; nothing changes; no re-run with tweaks. A variant needs a new rule written first.
- TypeSafe helps interpret outcomes but does not override the written gates.

## Limits, stated now
- Ten test seasons, a coarse season bootstrap, and the same seasons used for earlier NBA player tests (forking paths).
- The challenger drops the game-level team rating that the live model uses for older seasons (it sees three seasons of stints, the live team rating sees four with decay). If it loses, that is one possible reason; it is not a tested one.
- ESPN play-by-play before 2020 lacks some free-throw detail; stints use the same construction as the live RAPM.
- Lineup stints are rebuilt from play-by-play and can contain errors; the live RAPM shares this.
- Selection of w_c, lambda_tau and rho uses 2014 onward only, so early test seasons choose from very little data.

## Amendment 1 (5 Nov 2026, after GPT's review and before any fit, selection or replay). Nothing above is edited; where this contradicts the text above, this amendment governs.
1. **Roster sensitivity is an absence sensitivity, not a lookahead bound.** The first-10-games rule, and the live replay's first-team-in-the-season rule before it, still reveal information at pre-season checkpoints: early-season transactions and who returns from injury. Keeping players who miss the whole season on last season's team addresses only that one part. G6 is renamed the absence sensitivity. The remaining lookahead is acknowledged, results at the pre-season checkpoint (week 0) are reported separately for every arm pair, and giving both arms the same rosters is not assumed to help them equally.
2. **Three arms**, so roster reconstruction is separated from the new mathematics:
   - **A0:** the unchanged live replay (rosters as in research/replay_nba.py: first team anywhere in the season, static through the season). This is the committed baseline.
   - **A1:** the live replay with the revised rosters: pre-season, the first team a player appears for within that team's first 10 games; in season, the team he last played for before the checkpoint. The revised rosters feed A1's roster step and RAPM mix exactly as the live code does (option BT_ROSTER=v2).
   - **A2:** the joint model with the same revised rosters as A1.
   - Gates G1-G6 compare **A2 against A1**. New **G7:** A2 against A0, combined mean gain point estimate above 0. A1 against A0 is reported on its own as the effect of roster reconstruction.
3. **Playoff calculation frozen for A2.** The regular rating is multiplied by the season's scale. The playoff rotation adjustment is computed in the same units and receives the same scale: delta = scale x PO_K x (po - reg), where reg = 5 x the minutes-weighted average of beta + development over the same 12-man rotation and the same minutes m (the blended minutes defined above, scaled to 240) that the regular rating uses, and po uses the top 8 of those minutes after the live last-season playoff/regular minutes ratio, power 1.5 and 42-minute cap (PO_K = 1). No second minutes adjustment enters. tau does not enter the playoff delta.
4. **Data and cutoffs.**
   - Stints: ESPN play-by-play 2012-2026. Both play-by-play and box scores were confirmed present on 5 Nov 2026 for 2002-2014 and later. For a fit in season K the stints are K, K-1 and K-2 (so the 2014 selection season uses 2012 and 2013).
   - Box-score priors and roster-step minutes: player box scores of K-1 and K-2 only, at every checkpoint of season K. No full-season K statistic enters an earlier checkpoint. In-season data enters only through stints and minutes dated before the checkpoint.
   - Experience for the development bonus: seasons since a player's first regular-season minutes in box data from 2002 through K. Players before 2002 are counted from 2002, which already puts them past the bonus.
   - Fallbacks: a game whose lineup cannot be rebuilt is dropped, as in the live RAPM. If a season has fewer than 60% of games usable, that season is left out of the fit and the rest keep their weights; counts are reported. If K-2 is unavailable the fit uses K-1 and K.
5. **Execution choices.**
   - Simulations: BT_SIMS = 2000 for every arm, the replay's default seed, identical schedule and outcomes.
   - Gain is computed on weekly checkpoints, each weighted equally within a season; the season gain is the mean over its checkpoints; the combined gain is the mean over the five markets, then over seasons.
   - Bootstrap: resample the 10 test seasons with replacement, 4,000 draws, seed 1; the statistic is the mean over seasons of the combined season gain; the 90% lower bound is its 5th percentile.
   - Forecast stages (G5) by the league-average games played at the checkpoint (gp_avg): pre-season = 0; early = above 0 and below 20; middle = 20 up to but not including 42; late = 42 and above. A stage's gain is the mean over its checkpoints within a season, then over seasons.
   - G6 (absence sensitivity) reuses the primary hyperparameters and scale; nothing is re-selected. It uses rosters where players absent all season stay on last season's team, in both A1 and A2.
6. **Wording correction.** The simulation settings (TEAM_TAU, TAU_PRE, GAME_SIGMA) were calibrated for the baseline's ratings and may interact differently with the challenger's. The direction is not guaranteed; the earlier phrase that this "favours the baseline" is withdrawn.
7. **Mechanics check before the full run.** One checkpoint (2022 pre-season and one in-season week) is inspected for mechanics only: that no data dated on or after the checkpoint enters; that the joint fit with lambda_tau set very large reproduces the live RAPM player ratings (correlation and scale); that rating units are points per 100, centred, with minutes summing to 240 over 12 players; and that the playoff delta uses the same minutes. No forecast performance is looked at and no hyperparameter is selected from it. After this the implementation is frozen, its commit hash is recorded in the results, and any later change needs a dated amendment before the full run, disclosed in the results.

## Amendment 2 (5 Nov 2026, implementation frozen at commit 71d47d6c6b1b, after the mechanics check and before any selection or replay result)
Mechanics output is in research/NBA_JOINT_MECHANICS_OUTPUT.txt (2022 pre-season and week 4). No forecast performance was computed or looked at. Findings and the choices they fixed:
1. **Two bugs found and fixed before freezing.** (a) The owner overrides were leaking into the box-score prior until they were switched off as in every other replay; the check "no player with first minutes in season K has a prior" caught it. (b) Two ESPN ids above 30 (All-Star and exhibition sides filed as regular season) created extra team-seasons; stints now keep only ESPN team ids 1-30.
2. **Fit correctness.** With lambda_tau = 1e9 the joint beta equals the live research RAPM on the 636 shared players: correlation 1.000000, max abs difference 0.00001, slope 1.00000. Normal-equation residual 2e-10.
3. **Data timing.** Stints of K-1 and K-2 end before season K starts; no season-K stint is used at the pre-season checkpoint; the latest season-K stint used at the in-season checkpoint is dated on the cutoff, never after. Box priors use seasons K-1 and K-2 only.
4. **Units and minutes.** Every team has 12 players and minutes summing to 240.000000; team strength by hand equals the function; the playoff delta by hand equals the function and scales exactly with the season scalar.
5. **Interpretation choices frozen (not in the rule text above):** (i) a current-roster player with no prior-season minutes gets projected minutes of 180/82 per game (the roster step's convention) and the live rookie rating if he has no rating; (ii) the development bonus applies only to players with minutes in an earlier season, so a player whose first minutes are in season K gets none (the live code only develops players with prior-stint ratings); experience is counted from regular-season box data of 2002 to K-1; (iii) projected minutes are divided by 82 literally, including after 72-game and shortened seasons; (iv) the game-level fit still supplies the home edge and pace used by the simulator, identically in every arm; (v) a player on the pre-season roster who has not played by a checkpoint keeps his pre-season team, a player who has played is on the team he last played for; (vi) in A1 the week-0 playoff rotation also uses the revised pre-season roster; (vii) the 2020 bubble season is out of the selection and test seasons, but its stints still feed fits of 2021 and 2022; (viii) selection checkpoints are the weekly checkpoints nearest to 0, 20 and 41 average games played; the scale is the least-squares slope through the origin of rest-of-season net rating (per 100, centred) on the pre-scalar rating over the same selection seasons, checkpoints and teams; (ix) the replay hooks are BT_ROSTER=v2, BT_JOINT=1, BT_JOINT_SCALE=0 and BT_FULL_NOLEAK=1; A0 is the unchanged replay and was reproduced exactly (max difference 0.0 in all five markets and mean wins) against the committed 2022 file for weeks 0-2 on this machine before freezing; the full comparison against every committed file is reported with the results.
6. **Usable play-by-play.** Share of games with rebuildable lineups is at least 96% in every season 2012-2026 (lowest 2019: 96.0%, 49 games), so the 60% fallback is not triggered. Stints come from the same rebuild code as the live RAPM, run here on the 2012-2026 play-by-play files.

## Result (5 Nov 2026): FAIL. All seven gates fail. Code frozen at 71d47d6c6b1b; scored output in model/replay/nba_joint_score.json
Test seasons 2016-2019, 2021-2026 (ten). Gain = baseline log loss minus challenger log loss, positive is better. Season-cluster bootstrap 4,000 draws, seed 1.

| Comparison | Combined gain | 90% interval | Seasons better |
|---|---|---|---|
| **A2 (joint) vs A1 (same rosters)** | **-0.0119** | -0.0238 to -0.0002 | 3 of 10 |
| A2 vs A0 (unchanged live replay) | -0.0151 | -0.0272 to -0.0032 | 3 of 10 |
| A1 vs A0 (revised rosters alone) | -0.0032 | -0.0046 to -0.0018 | 2 of 10 |
| A2 without the scalar vs A1 | -0.0205 | -0.0362 to -0.0052 | 3 of 10 |

A2 vs A1 by market: title -0.0119, finals -0.0175, division -0.0035, No.1 seed -0.0018, playoffs -0.0246. By stage: pre-season -0.0068, games 1-19 -0.0142, 20-41 -0.0141, 42+ -0.0101. By season: 2016 -0.022, 2017 -0.007, 2018 -0.054, 2019 -0.028, 2021 +0.010, 2022 +0.019, 2023 -0.025, 2024 -0.020, 2025 +0.025, 2026 -0.016.

Gates: G1 fail (gain -0.0119, lower bound -0.0238; even the upper bound is below zero). G2 fail (3 of 10). G3 fail (four of five markets below -0.0005 by wide margins). G4 fail (2026 -0.016). G5 fail (every stage below -0.002). G6 fail (absence sensitivity -0.0118, 3 of 10). G7 fail (A2 vs A0 -0.0151).

Other reported numbers:
- Single games (supporting, same 2.2 home edge and sigma 12.2 for all arms): margin MSE A0 182.6, A1 182.4, A2 187.6; win log loss 0.6195, 0.6195, 0.6303. Worse in early and later games alike.
- Rating spread across teams (mean sd, points per 100): A0 4.02, A1 3.98, A2 3.46 after the scale. Mean absolute rating change A2 vs A1: 1.51.
- Share of A2 rating variance from the player sum: 98.9%; correlation of player part and team part 0.10. The team effect carried almost nothing.
- Calibration slope of the reaches-Finals probability: A0 0.92, A1 0.90, A2 0.84; playoffs 0.99, 0.99, 0.92 (below 1 means overconfident).
- Selection chose the same corner of the grid in every one of the ten test seasons: current-season weight 2 (the lowest), team penalty 16000 (the highest), rho 0 (the lowest). Scales were 0.71 to 0.79. The grid could not go further in any of those directions, so the selected model is at the edge of what was allowed to be tried, and it effectively switched the team effect off.
- A0 against the committed replay files: 2022-2026 reproduced exactly (max difference 0.0 in every market). 2016-2019 and 2021 differ (title up to 0.037, playoffs up to 0.25, division and No.1 seed identical in 2016-2019; 2021 differs in all markets), so those committed files were not built with the same era settings as the current replay command. As the rule says, the fresh run is the baseline; all arms share it.
- Usable play-by-play: at least 96% of games in every season, so no fallback.

What this says and does not say:
- Under this design the joint model is clearly worse than the live pipeline for futures, and worse for single games. It is not a noisy near miss: it loses in 7 of 10 seasons, in every stage, and in four of five markets.
- A1 vs A0 is a separate finding. Removing the lookahead from the live model's rosters costs -0.0032 and 8 of 10 seasons. Part of the live replay's apparent skill (at least for 2016-2026) comes from knowing which players actually played for each team. The live forecast has no such knowledge, so the historical baseline is flattered by an amount of that order.
- The joint model lost by more than that, so lookahead in the baseline does not explain the fail.
- Not tested, so not claimed: whether a wider grid (lower current-season weight, higher team penalty, other prior strength) helps; whether the cause is the loss of the game-level team rating, the 3-season window, or the scale step; whether the weekly refit adds noise. All three were named in the rule as open.

Decision, as written: any gate fails, so this is recorded as a fail. Nothing changes in the live model. No re-run with tweaks; a variant needs its own rule written first. The selection corner and the roster finding are the two things a follow-up rule should start from.
