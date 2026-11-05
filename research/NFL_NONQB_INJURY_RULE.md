# NFL: missing non-QB starters (injuries and reserve lists). Rule, version 1

Written 5 Nov 2026 (Sydney), before any injury feature was built or any result seen. Amendments are added below with dates; nothing above them is edited.

## Why
- In live v4, injuries count only through the QB layer. Absent offensive linemen, pass rushers, cornerbacks and others weigh 0% (measured 5 Nov 2026).
- The closing NFL line beats our model on games (RMSE 12.39 vs 12.86 on 2022-2025), and injury news is the most obvious information the market has and we lack.
- TypeSafe picked this as the next model change (74%, then 58%); the owner asked for it.

## Data (nflverse, all point-in-time)
- **Snap counts** (snap_counts_<y>.csv, from 2013): each player's offensive or defensive snap share per game.
- **Final injury report** per game week (injuries_<y>.csv): report_status Out or Doubtful.
- **Weekly rosters** (roster_weekly_<y>.csv): a status other than ACT (reserve/injured, PUP, suspended and so on) in that week.
- Players are linked through the roster's gsis_id and pfr_id. Seasons 2014-2025 are used, because 2013 is the first season with snap counts.

## Feature (fixed before building)
For team t before its regular-season game in week w (w >= 2):
- **Importance** of player p = mean snap share over t's earlier games this season in which he played at least one snap. He needs at least 2 such games; otherwise he is not counted.
- **Missing:** p is missing in week w if the week-w final report lists him Out or Doubtful, or the week-w roster shows him with a status other than ACT, and he has importance as defined.
    - QBs are excluded (they are covered by the QB layer), as are K, P and LS.
- **Groups:**
    - OL: T, G, C, OT, OG;
    - DL: DE, DT, NT, OLB, EDGE;
    - LB: ILB, MLB, LB;
    - CB;
    - S: S, FS, SS, DB;
    - WR;
    - TE;
    - RB: RB, FB.
    - A player's group comes from his roster position in that week.
- **Team feature** M_g(t, w) = the sum of the importance of missing players in group g. The game feature is home minus away.

## Baseline expectation
Frozen v4 base ratings, point-in-time, from research/nfl_walkforward_weights.py's game features (data/research/nfl_wf_features.npz): prediction = X . frozen coefficients + frozen intercept. This is the same baseline as research/NFL_EFFICIENCY_WEIGHT_RULE.md (no QB or pressure layer). Residual = home margin - prediction.

## Stage 1: does it explain margins? (games)
- **Fit (2014-2021, weeks 2-18):** residual = sum over g of beta_g x (M_g home - M_g away), least squares with no intercept. This is the primary model.
- **Pooled version (reported):** a single beta on the total missing share.
- **Test (2022-2025, weeks 2-18):** game-margin RMSE and win-probability log loss (sigma 13.4) of baseline vs baseline + injury term, overall and by season. Also reported: the blend weight next to the closing spread.
- **Pass:** all of the following.
    - Test RMSE is lower than baseline overall.
    - It is lower in at least 3 of 4 test seasons.
    - Win log loss is lower overall.
    - Every group coefficient with |t| > 2 on the fit seasons has the expected sign (missing your starters hurts your margin).
- **Fail:** stop. The model is not changed.

## Stage 2: futures (only after a Stage 1 pass; written as a dated amendment before it runs)
How absences carry into the season simulation (an Out listing for the next game only, reserve lists for longer), the replay settings, and the gates follow the NFL QB and rest rules.

## Limits, stated now
- Snap share measures playing time, not quality.
- Doubtful players sometimes play.
- A player who was out all season before week w has no importance and is not counted (the ratings already reflect his absence).
- 2022-2025 tests the injury coefficients out of sample. The baseline's simulation settings saw those seasons, but Stage 1 uses no simulation settings.

## Amendments
**5 Nov 2026, implementation fixes after the first run, which is recorded here and not used:**
- **The first run was flawed.** Its numbers were seen: test RMSE 12.913 -> 12.813, log loss 0.6348 -> 0.6259, 3/4 seasons, a nominal "pass". Two defects:
    1. **Player links:** snap counts were joined to injuries through the weekly roster's pfr_id, which is missing for many players. Almost no offensive lineman ever had an importance (OL feature about 0 in every season).
    2. **Positions:** from 2016 the roster's `position` column is coarse (DB, OL, DL), so cornerbacks were counted as safeties (CB = 0 from 2016).
- **Fix (no other change; groups, thresholds, seasons and gates are as written above):**
    - Links use the nflverse players table (players.csv: gsis_id <-> pfr_id), falling back to the roster's pfr_id.
    - A player's position is the weekly roster's `depth_chart_position`, else the players table's position, else the roster's `position`. Coarse labels go to groups as written (DB -> S, OL -> OL, DL -> DL).
- The rerun decides Stage 1. If it fails, the first run's "pass" does not count.

## Stage 1 result (5 Nov 2026, corrected run): PASS
research/nfl_nonqb_injury_test.py -> research/nfl_nonqb_injury_results.json (features in data/research/nfl_nonqb_injury_features.csv.gz). 1,681 fit games (2014-2021) and 959 test games (2022-2025). 89% of 2014-2025 games had features for both teams.
- **Test (2022-2025):**
    - margin RMSE 12.913 -> 12.829;
    - win log loss 0.6348 -> 0.6247;
    - better in 3 of 4 seasons (2022 worse: 11.655 -> 11.865).
    - Pooled single-coefficient version: RMSE 12.789, log loss 0.6257.
- **Coefficients (points per 1.0 of missing snap share, home minus away; t on the fit seasons):**
    - significant, all with the expected sign: OL -0.62 (t -2.1), DL -1.17 (-3.1), WR -1.58 (-3.3), RB -2.12 (-2.7);
    - not significant: LB -0.40, CB -0.21, TE -0.72, S +0.24.
- **Next to the closing spread:** the blend weight on the model goes from -0.03 to +0.11. The market still carries most of the weight (0.98). The closing spread's RMSE is 12.436.
- **Sensitivity (reported, not a gate):** using the final injury report alone (Out/Doubtful, no roster status) gives RMSE 12.877 and log loss 0.6330, better in 2/4 seasons. So most of the information is in reserve lists and game-day inactives, not in Friday's report.
- **Timing check:** players with a non-ACT roster status in week w almost never played that week (RES 0.2%, INA 0.0%, DEV 0.2% of rows, 2016/2020/2023/2025). The status is pre-game, not a post-game record. Inactives (INA) are announced about 90 minutes before kickoff, so that part of the information is game-day only.
- **Next:** Stage 2 (futures) is written as a dated amendment before it runs.

## Stage 2 amendment (5 Nov 2026), written before any futures replay with this layer
- **Known at a checkpoint after week w:** players with importance (at least 2 games with snaps through week w) whose week-w roster status is neither ACT nor INA (reserve/injured, PUP, suspended, non-football injury, practice squad, released and so on). QBs, K, P and LS are excluded. Game-day inactives and injury-report listings are for that week's game only, so they are not carried forward.
- **Duration:** each such player is assumed out for his team's next 4 regular-season games (the injured-reserve minimum since 2020). No playoff carry-over.
- **Per game:** home-margin shift = sum over g of beta_g x (missing share home - missing share away), using the Stage 1 coefficients fitted on 2014-2021 (research/nfl_nonqb_injury_results.json). Each team's missing share applies only to games within its own 4-game window. It is added to the edge through simulate's existing research `margin_adj` column, in points, unscaled.
- **Replay:** research/replay_nfl.py with BT_INJ=1 against the same baseline (BT_REST=1 in both arms), seasons 2022-2025, checkpoints after weeks 2-17 (BT_WMIN=2), 4,000 simulations.
- **Pass (a model change, so stricter than the rest fix):**
    - combined mean gain (division, playoff, No. 1 seed, conference, Super Bowl) > 0, with its 90% season-bootstrap lower bound > 0;
    - better in at least 3 of 4 seasons;
    - no market's mean gain below -0.0005.
- **Decision:**
    - **Pass:** a shadow next to v4 for the rest of 2026, archived and forward-scored (v4 stays frozen). Live only after the forward record.
    - **Fail:** recorded. The game-level result (Stage 1) stands as research.
