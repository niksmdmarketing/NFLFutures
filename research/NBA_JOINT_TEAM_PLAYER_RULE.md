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
