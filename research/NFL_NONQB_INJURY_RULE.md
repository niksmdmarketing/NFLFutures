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
