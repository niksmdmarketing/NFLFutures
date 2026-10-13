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

## In-season rating update for AFL and NBL: recency-weighted ratings, no gain
- Rating refit with exponentially down-weighted older games (half-life 6/12/24 rounds or weeks) instead of equal weights: every market within 0.003 log loss
  of the live model, title/finals/top-4 slightly worse, make-finals slightly better (0.3565 -> 0.3542 AFL, NBL flat). No evidence of usable in-season form beyond
  the equal-weight rating. Not deployed.

## Review round after GPT critique (13 Oct 2026)
- Injury-free replays are NOT an upper bound on the live model: the live model may be better or worse. Replay scores describe a different model.
- Slopes now carry intercepts and season-cluster 90% intervals (model/replay/CALIBRATION_CI.md, research/replay_ci.py). What the intervals support:
  - Clearly off (interval excludes 1): NBA title/seed1/playoff in the last quarter are too timid (title 1.42 [1.11, 2.04]); NHL preseason and first-quarter title/finals too timid (preseason finals 2.37 [1.99, 2.93]); AFL playoff/top-8 mid-season too extreme (third quarter 0.69 [0.59, 0.85]); AFL last-quarter finals/seed1 too timid.
  - Not distinguishable from calibrated or from off: most NBL cells, NBA conference, NHL title after the first quarter, AFL title. Ten to fourteen seasons cannot settle title markets.
- The earlier note that a 5-season NBA window was "false" is withdrawn: it was a noisier estimate of the same quantity.
- Gains under 0.003 log loss are not called noise by themselves any more; none of the AFL/NBL/NHL variants was deployed, and none is claimed to be harmful or useless.
- No 'points already banked' correction: simulations start from current standings, so it would double-count.

## Future-information audit (13 Oct 2026)
- Soccer (private repo, research/soccer_leak_check.py): scrambling every score after the checkpoint leaves the probabilities unchanged (difference 0.0).
- AFL (research/replay_leak_check.py afl 2023 10): scrambling every result after round 10 and the finals leaves checkpoints up to round 10 unchanged (0.0); later checkpoints do change, so the test can detect leaks.
- NBA: read, not run (the box-score downloads are outside the network allowlist here). _fit_ratings sees only earlier seasons plus current-season games on or before the cutoff; no direct leak found.
- NBL, NHL: not yet checked empirically (NHL uses params_before = earlier seasons only).
- Selection, not leakage: several settings were chosen on these same seasons and so flatter the replay scores a little: NBA decay 0.2 / current-season weight 4 ("chosen on the point-in-time backtest", per the code comment), AFL/NBL tau and shrinkage constants, soccer K. Soccer K was confirmed walk-forward; the others have not been.
- Format knowledge (finalist count, play-in era) is read from the season's own final outcome. It is public before each season, so not a leak of results, but it is not strictly 'known at the time' for the earliest seasons.
- NBL (research/replay_leak_check_nbl.py 2022 70): scrambling every score from 10 weeks into the season and the finals leaves earlier checkpoints unchanged (0.0); later ones change.
- NHL (research/replay_leak_check_nhl.py <data> 2023 70): scrambling goals and results from 10 weeks in leaves earlier checkpoints unchanged (0.0); later ones change.
- Result: soccer, AFL, NBL and NHL replays pass the future-results check; NBA is read-only reviewed (needs its box-score downloads to run). This tests results leakage only, not the selection of settings on the same seasons.

## Walk-forward tests of settings chosen on the replay seasons (13 Oct 2026; research/replay_walkforward.py)
- AFL rating-uncertainty start TAU0 (8/14/20/28): the live 14 is best pooled (0.2546 vs 0.2574 / 0.2561 / 0.2613); walk-forward picks 14 from 2018 on and equals the default overall (0.2589 vs 0.2588). No change.
- NBL TAU0 (2/4/6/8): live 4 is best pooled; walk-forward choosing T2 scores slightly worse than staying at 4 (0.3306 vs 0.3277), all differences inside the interval. No change.
- NBA ratings decay / current-season weight (live: 0.2 and 4), 14 seasons, 400 sims: decay 0.5 and weight 2 are clearly worse. Nearby settings are slightly better: decay 0.1 with weight 8 improves every market (title 0.0969 -> 0.0928, finals 0.1858 -> 0.1841, division 0.2140 -> 0.2132, seed 1 0.1034 -> 0.0993, playoffs 0.3083 -> 0.3063; mean 0.1844 -> 0.1819), better in 9 of 14 seasons, but the season-cluster 90% interval on the difference (-0.0060 to +0.0012) includes zero and the setting was picked from a grid of eight on the same seasons. Walk-forward (decay 0.2, weight 8 is chosen every year from 2015) scores 0.1910 vs 0.1929 for the live setting. Exploratory. NOT deployed; candidate for prospective checking only.
- replay_nba.py now accepts BT_DECAY, BT_CW and BT_OUTDIR (an earlier run without BT_OUTDIR overwrote the committed CSVs in the working copy; restored from git before anything was committed).
- NBA future-results check (research/replay_leak_check_nba.py 2024 70): scrambling scores, ortg and possessions of every box-score row from 10 weeks into the 2024 season on (including playoffs) leaves earlier checkpoints unchanged (0.0); later ones change. All five sports' replays now pass the check.

## Where the AFL mid-season "make finals" over-confidence sits (13 Oct 2026; replay checkpoints at 25-90% of the season, 14 seasons)
- Pooled it is calibrated (predicted 45.3%, actual 45.3%); the middle (35-65%) is fine (49.5% said, 47.5% happened).
- The miss is in the tails. Teams given 5% or less: 7 of 113 team-seasons made the finals (6.2% against 1.1% said; about 1.2 were expected). Teams given 5-15%: 17% made it against 9.5% said (15 of 88). Teams given 85-95%: 86.5% made it against 90.4% said (83 of 96). So longshots are too unlikely and near-certainties slightly too certain.
- Not tied to a stage of the season: in the 15-85% zone the gap is -2 to -3 points for rounds 5 to 20 alike. Season gaps swing between -14 and +15 points with no pattern; the team pattern (e.g. SYD and BRI beat the model, GCS, STK, ADE fell short) rests on 6-11 seasons per team and is not strong enough to call.
- Reading: the model's spread of possible outcomes for the final ladder is too narrow at the extremes; tau, game spread and recency tests did not widen it usefully. Seven longshot cases is a small base, so this is a lead, not a verdict. Not deployed. Candidate test: team-specific variance, judged only on held-out seasons or live data.

## NFL read-only replay (13 Oct 2026; research/replay_nfl.py)
- Frozen v4 model, untouched: ratings.base_ratings + simulate.simulate, every week 0-16, seasons 2022-2025 only (weights trained 2010-2021; the spread was tuned on 2022-25, so not fully unseen). QB and injury layers are off (no weekly history). 4000 sims.
- Gain over a flat guess is small before the season (title +0.007, division +0.021, playoffs +0.015) and grows through the year (last quarter: playoffs +0.38, division +0.28, seed 1 +0.17 on top of the base).
- Calibration with 4 seasons (season-cluster 90% intervals are very wide and not reliable with 4 clusters): conference winner too timid in the third and last quarter (slope 1.9 [1.2, 3.0] and 1.8 [1.4, 2.9]), No. 1 seed too timid late (2.1), division a little too extreme from the third quarter (0.75 [0.58, 0.96]), playoffs well calibrated from the third quarter. Title: about right. Four seasons can't settle any of this. v4 is frozen, so nothing was changed.
- History page for NFL at /replay.html (site root), data/replay.json; pipeline/replay_site.py SPORTS["nfl"] (dir "" = root, nav link after Matchups, caveat text shown on the page). pipeline/sport_archive.py now also archives the live NFL futures (data/futures.json: p_sb, p_conf, p_div, p_seed1, p_playoff) so the 2026 season is added to the page from now on.
- NFL future-results check (research/replay_leak_check_nfl.py 2024 8): scrambling all play-by-play numbers and game scores/results after week 8 of 2024 (and the playoffs) leaves checkpoints up to week 8 unchanged (0.0); later ones change. All six replays (NBA, NHL, AFL, NBL, NFL, soccer) now pass.

## Season-end scoring plan
Futures resolve only at the end of a season, so the live archives (forecast-archive branch; private repo forecast_archive/soccer) can be scored then. Do this per sport when its season is over:
1. Score the live snapshots against the real outcomes with the same tools as the replays (research/replay_score.py, replay_slope.py, replay_ci.py), at the same stages of the season, with season-cluster intervals (one season is one cluster, so say so).
2. Re-check the known issues on the new season only: AFL make-finals tails (longshots under 5% and near-certainties over 85%); NBA late-season title timidity; NHL early title/conference flatness; NFL conference winner and No. 1 seed timidity; soccer late-season title/top-two timidity.
3. Test the exploratory NBA setting (decay 0.1, current-season weight 8) and the soccer prior weight (30) on the new season only, as held-out evidence. Change a deployed setting only if it improves the new season's scores without hurting other markets and tests pass; otherwise write it up undeployed.
Approximate end dates: AFL 2026 (done, Grand Final played), NBL March 2027, NFL Super Bowl February 2027, soccer leagues May 2027, NBA and NHL finals June 2027.
A monthly read-only health check (scheduled task, 1st of each month 8:52 Melbourne) checks the archives, workflows and pages, and says when these dates have been reached.

## NFL: playoff simulation and walk-forward weights (13 Oct 2026)
See model/v5_notes.md. Replay extended to 2013-2025 with walk-forward weights (13 out-of-sample seasons). Playoff home edge 4.0
is the only change with an interval above zero (conference and title only); added as archived challenger_v5. v4 unchanged.

## NHL: early conference/Cup flatness (13 Oct 2026)
Replay 2014-18, 2021-25 (settings from earlier seasons). Preseason/first-quarter conference and Cup slopes 2.37/2.25 and
1.57/1.58; playoffs, division, best record calibrated. An after-the-fact recalibration would only gain 0.005 (conference)
and 0.003 (Cup) in early log loss, so the cost is real but small. Knobs added to research/replay_nhl.py (NHL_TAU_PRE,
NHL_PRIOR_SCALE, NHL_PO_SCALE, NHL_PO_FADE; nhl_model.simulate(po_scale=1.0) default = live behaviour). 3,000 sims:
- prior x1.25 / x1.5: conference/Cup better but make-playoffs (-0.006/-0.015) and division worse: rejected.
- no preseason widening (TAU_PRE 1.0): no change. Constant playoff multiplier 1.3: +0.0002.
- fading playoff multiplier (x2 at season start -> x1 by game 82): overall +0.0003 (90% -0.0005 to +0.0012), better 6/10;
  first quarter +0.0012, 7/10; conference/Cup only; early slopes 2.37 -> 1.99 and 1.57 -> 1.25, later stages stay near 1.
TypeSafe low confidence (0.19; deploy 46%, record 30%, challenger 24%); interval includes zero so by the deploy rule it is
NOT live: added as an archived challenger (futures.json c_final/c_cup, archived as c_finals/c_title).

## NBA: current-season weight and late-season caution (13 Oct 2026)
14-season replay (2013-2026, 2,000 sims). Knobs: BT_CW, BT_DECAY, BT_TAUFADE (nba.TAU_FADE, default 0 = live), BT_TEAM_TAU.
- current-season weight 4 -> 8: mean log loss -0.0018 (90% -0.0011 to +0.0046), better 9/14 seasons, every market better
  (title 0.0021, finals 0.0004, division 0.0007, seed 1 0.0029, playoffs 0.0029). DEPLOYED (TypeSafe 75%, confidence 0.62).
  History CSVs and nba_score/nba_slope.json regenerated with weight 8. (CALIBRATION_CI.md NBA rows not regenerated.)
- Fading team uncertainty (50%/80% by game 82) fixes the late title slope (1.42 -> 1.18) but makes conference/division
  over-confident mid-season; walk-forward selection over all six settings gained nothing (-0.0003). Not deployed.
- Still open: last-quarter title (slope 1.38 [1.10, 1.89]) and seed 1 (1.46 [1.23, 1.98]) remain too cautious.

## AFL: heavy-tailed game margins (13 Oct 2026)
Make-finals longshots mid-season (model 5% or less) made the top 8 3.1% of the time vs 0.8% said (873 team-rounds,
correlated within seasons); near-certainties (85-95%) 86.5% vs 90.2%. Student-t game margins (df 4/6/10, same spread;
afl_site.GAME_DF, default 0 = normal) did not help: overall -0.0005 to 0.0000, late season worse, tails unchanged.
Together with the earlier tau/fade/drift/spread/recency tests, no setting fixes the tails; AFL left unchanged.
The 2026 top-10 format has only the live 2026 archive as evidence.

## Live check (13 Oct 2026, pipeline/live_check.py)
Each sport's History page now scores this season's published forecasts from the forecast-archive branch:
- NFL games: every completed game scored once from the latest snapshot before its date, v4 and the v3 challenger, using
  each model's own single-game probability (first 13 games: v4 0.646, v3 0.639, coin flip 0.693).
- Other sports: the Outlook page's pre-game win chances (schedule.json, next 8 days) are archived with every snapshot
  (from 13 Oct) and scored the same way once results arrive.
- Futures: from half-way through a season, team-markets at exactly 0%/100% in the newest snapshot count as settled and
  every earlier snapshot is scored (live model and archived challengers, same rows). After the season this is complete.
Team ratings are also archived (rating_x100) for later checks.

## NBA awards: forward simulation + 65-game rule (14 Oct 2026) - DEPLOYED
research/nba_awards_replay.py (core in pipeline/nba_award_sim.py). Seasons 2010-2026, checkpoint every 14 days from
day 21, logit weights leave-one-season-out. Live method (stats to date) vs simulation of each candidate's season to the
end (rates shrunk to last season over 10 games, availability shrunk to 85%, health sd 0.12, talent sd 0.08, team win%),
65-game rule from 2023-24 counted as 15+ minute games (strict 20-minute counting wrongly excluded real winners, e.g.
Wembanyama 2025-26 DPOY with 63 games of 20+).
- mean -log p(winner): 0.09 better (season-cluster 90% 0.034 to 0.147); MVP 0.11, DPOY 0.11, Sixth Man 0.11, ROY 0.03.
- first quarter: favourite said 58% vs won 31% (live) -> 47% vs 34% (sim); later stages similar or better.
- lower noise (talent 0.04, health 0.06) slightly worse. Deployed in nba_site.awards with stats-to-date fallback.

## NFL awards: weekly replay 2018-2025 (14 Oct 2026)
research/nfl_awards_replay.py: weeks 4-16, live projection method, no historical injury lists. Live weights are fitted
on 2010-2025 (in-sample); honest leave-one-season-out refits score worse (expected) but show the same pattern.
- Favourite calibration (live weights): weeks 4-6 says 29% / won 23%; weeks 8-10 28% / 35%; weeks 12-16 32% / 51%.
- Late sharpening, temperature chosen leave-one-season-out per award and stage: OROY T 0.5 from week 8 (+0.33, 7/8
  seasons), DROY T 0.5 (+0.83, 7/8), OPOY T 0.7 (+0.08, 6/8); MVP/DPOY/CPOY and every early-season choice no gain.
  DEPLOYED for those three awards from week 8 (awards.LATE_T; TypeSafe 99%).
- Comeback Player: winner outside the candidate pool 25% of the time; favourite says 22%, wins 11%. The page already
  marks it "No proven skill" (names to watch, not odds).

## NHL awards: dated-snapshot replay 2011-2025 (14 Oct 2026)
research/nhl_award_snapshots.py (GitHub Actions, NHL stats API, games on or before each checkpoint every 21 days) +
research/nhl_awards_replay.py (live method rerun, weights leave-one-season-out). Team per player = season-end team.
- Favourite calibration (live): Hart under-confident throughout (said 25-40%, won 31-48%); Vezina over early (41%/22%)
  and under late (64%/77%); Norris under late (46%/61%); Art Ross/Richard under mid/late (Richard mid 49%/67%).
- Race noise: talent gamma shape 20 -> 50: Art Ross +0.071 (11/15), Richard +0.072 (11/15), awards +-0.01. Shape 100 over-
  confident early. Stronger rate prior (k 36/44) adds a little for races (+0.11 combined) but untested on the awards.
- Logit temperature (leave-one-season-out per award and stage): only Vezina late helps (T 0.6, +0.07, 10/13).
DEPLOYED: TALENT_SHAPE 50 and Vezina late T 0.6.
