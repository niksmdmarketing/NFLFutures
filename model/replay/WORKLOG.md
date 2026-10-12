# Replay work log (Oct 2026, unattended session)

## NBA weekly replay (14 seasons 2013-2026, 2,000 sims per checkpoint, no availability adjustment)
- Files: model/replay/nba_<season>.csv, scored with research/replay_score.py, slopes with research/replay_slope.py.
- Five seasons alone suggested the conference-winner probabilities were far too extreme (slope ~0.5). With 14 seasons the slope is 0.87-1.03:
  five seasons is only ~10 conference outcomes, so slopes from short windows are noise. Use 14 seasons.
- Division / top seed / playoffs: well calibrated at every stage (slopes 0.98-1.2).
- Title: slightly too timid late in the season (slope 1.3-1.4); re-calibration would gain only 0.003 log loss, so no change made.
- 2020 (bubble, 42 weekly checkpoints) and 2021 (72 games) are in the sample and are odd seasons; not excluded yet.

## NHL weekly replay (10 seasons: 2014-2018 and 2021-2025)
- 2013 skipped (PHX/ARI code), 2019-2020 skipped (shortened / non-standard), earlier alignments rebuilt: 2014-16 30 teams, 2017-18 31 teams.
- Playoffs and division: slope ~1, well calibrated.
- Title and conference are too flat at season start (slope ~2.3) and converge to ~1.1 by mid-season. Tested a playoff-strength multiplier
  (1.5, 2.0): log loss 0.1165 -> 0.1160 (title), 0.1938 -> 0.1933 (conference), better in 5 of 10 seasons. Not worth deploying; the
  preseason slope is mostly 10 champions' worth of noise. Not changed.

## AFL round-by-round replay (14 seasons 2013-2026)
- Checkpoint before round 1 and after each round; real fixture replayed; ratings and tau exactly as the live model.
- The top-10 wildcard finals format began in 2026 (earlier seasons had 8 finalists). Read from the data; simulate() got a `finals8` switch (live default unchanged).
  A first run wrongly assumed 2024 and was corrected after the 'make finals' market scored badly in 2024-25.
- Calibration is good for most markets. 'Make finals' mid-season is a bit too extreme (slope ~0.7-0.8, recalibration gain 0.007-0.02 log loss).
- Tested rating-uncertainty variants (TAU0 8/10/14/20/28/40, fade 26/30/40): flat optimum at the current 14/30. No change.
- afl_site.py now holds TAU0/TAU_FADE as named constants (same values) so the replay can vary them.

## NBL weekly replay (13 seasons 2013-14 to 2025-26)
- Format by era read from the data: 4 finalists (to 2021-22) = top four, 1v4/2v3 best-of-three semis, no play-in; 6 finalists = play-in format.
  nbl_site.simulate got a `top4` switch (live default unchanged). Champion = winner of the last game.
- 'Make the finals' mid-season is too extreme (slope ~0.75), the same pattern as AFL; championship is slightly too timid early (slope 1.5-2.2 preseason).
- Tried TAU0 4/6/8, floor .15/.5, GAME_SD 14/16: current settings are best or tied on every market. No change.
- Both ladder-based sports (AFL, NBL) show over-confident 'make finals' mid-season while NBA/NHL are fine. Possible cause: ratings are re-fitted
  with the same shrinkage all season; a form/injury term is missing. Left for GPT to review; not tested further.

## AFL / NBL 'make finals' over-confidence: investigated, no fix
- AFL: random-walk form drift 0.7/1.4/2.5 points per round, game spread 28/36/40, tau variants: every change moves any market by < 0.002 log loss
  (make-finals best case 0.3565 -> 0.3545). NBL: tau and spread variants likewise flat or worse. The mid-season slope (~0.75) is real but small
  (recalibration would gain ~0.01 log loss) and none of the levers in the model fixes it. Not deployed. Open for GPT: a team-specific variance term, or
  a proper in-season rating update (e.g. Kalman) rather than a refit with fixed shrinkage.
