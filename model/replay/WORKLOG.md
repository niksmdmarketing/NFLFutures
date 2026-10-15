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

## NBA: playoff-series gap multiplier (14 Oct 2026) - not adopted
nba.PO_SCALE (default 1). 14-season replay with the live weight-8 ratings: x1.2 -0.0001 overall (title +0.0007, conference
-0.0009), x1.4 -0.0004 (title +0.0010, conference -0.0031). Conference finalists are already slightly over-confident
mid/late (slopes 0.76-0.91) while the title is cautious (1.2-1.3), so no single playoff-strength change fixes both.

## NBA awards preseason (14 Oct 2026) - DEPLOYED for MVP and DPOY
Preseason pool = last season's leaders (30+ games), a full season simulated from last season's rates (team strength from
the Futures page live; last season's win% regressed halfway in the replay). Versus scoring last season's final lines:
DPOY +0.069, Sixth Man +0.245, MVP -0.018 (log loss per season). Calibration of the favourite: MVP said 38% / won 35%,
DPOY 30% / 24%, Sixth Man 43% / 0 of 17 (no preseason skill). Flattening (temperature 1.5-3) helped Sixth Man only.
Live: MVP and DPOY show preseason chances; Sixth Man and Rookie stay empty until games are played.
- NFL Comeback Player pool: last-season cap 10 -> 13 games (adds e.g. Tannehill 2019). Winner outside pool 25% -> 12%,
  LOSO log loss 4.41 -> 4.19; deployed. Still "No proven skill" (Flacco 2023 and Alex Smith 2020 are part-time QBs).
- NHL rate prior k 18/22 -> 36/44 (with shape 50): Art Ross +0.057 (9/15), Richard +0.024 (8/15), Hart +0.031 (7/15),
  Vezina +0.018 (10/15), Norris -0.020 (6/15), Calder +0.007 (7/15). Mixed, not adopted.
- NBA game sigma 12.2 -> 11.6 / 11.0: -0.0002 / -0.0005 (title +0.0005, others slightly worse). Not adopted; the
  late title/seed-1 caution stays open (no setting tried so far fixes it without hurting other markets).

## AFL Coleman race chances (14 Oct 2026) - DEPLOYED (applies from the 2027 season)
research/afl_coleman_replay.py with pipeline/race_sim.py: home-and-away goals per match (fitzRoy AFL Tables), checkpoint
every 3rd round, 2013-2026. Grid K {2,4,8,12} x talent shape {3,5,8,20,50}: K 4, shape 8 best (log loss 1.869).
Favourite said/won: early 29%/15% (too short), mid 35%/31%, late 64%/69%. The Coleman table previously had projections only;
it now shows chances, with the early-season caveat on the page.

## AFL Brownlow (14 Oct 2026) - DEPLOYED temperature 1.4
research/afl_brownlow_replay.py: Footywire per-match stats to each 3rd round, 2013-2026, weights leave-one-season-out.
Winners keyed by AFL Tables player ID (name keys merged the two Josh Kennedys). Live method: favourite said 42-49%, won
19-25%; winner in the 30-player pool 78% early, 88% mid, 100% late. Temperature 1.4 chosen in all 14 LOSO folds: +0.052,
8/14 seasons; favourite then 30-36% said vs 19-25% won (still short). Page note now says the favourite wins about 1 in 4.
- Award chances are now archived with every sport snapshot (sport_archive.award_chances: name, team, per-mille, top 15
  per award) so the live check can score them when the awards are announced.
- Coleman settings, walk-forward check (choose on earlier seasons only, score the next, 2016-2026): 1.935 vs 1.863 for the
  fixed K 4 / shape 8 (chosen on all seasons). Shape 8 is chosen in every fold; K drifts (4-12). Expect about 1.9 live.
- NHL voted awards early in the season (first checkpoint, about 10% played): favourites over-confident (Norris 33-37% said,
  2 of 15 won; Vezina 38%, 3 of 15; Hart 24-30%, 3 of 15). Temperatures did not improve log loss on 15 seasons, so the
  page now shows an early-season caution under 16 games instead of a model change. Race note updated (now replayed).

## NFL season stat-leader races (14 Oct 2026) - DEPLOYED on the Awards page
research/nfl_leader_replay.py: most passing yards / passing TDs / rushing yards / receiving yards / receptions / sacks,
2012-2025, weeks 3-15 every 2. race_sim (counts: Poisson; yards: Normal per game, cv 0.45) with K x shape grid per stat.
Chosen: pass yds K4/50, pass TD K2/20, rush yds K2/20, rec yds K2/50, receptions K4/20, sacks K4/50 (log loss 1.616;
walk-forward choice 1.657). Favourite said/won: weeks 3-5 34%/37%, 7-11 44%/46%, 13-15 65%/68%. No injury input.

## NBA: late-only uncertainty fade (14 Oct 2026) - not adopted
nba.TAU_FADE_START (default 0 = live): the team-uncertainty fade starts only after N games, so mid-season division and
conference are untouched (the earlier full-season fade made them over-confident). 14-season replay, 2,000 sims, games 61+:
- fade 50% from game 55: +0.0000 overall (7/14); fade 80% from game 60: +0.0001 (90% -0.0001 to +0.0003, 9/14). Late title,
  division, seed 1 and playoffs all better (late title slope 1.26 -> 1.15, seed 1 1.54 -> 1.47) but late conference worse
  (0.1744 -> 0.1780).
- adding a playoff-gap multiplier x0.9 to offset the conference: +0.0001 (8/14), conference better, but title -0.0001
  overall; x0.8 worse for the title. Gains are within noise, picked from five variants on the same seasons, and the title
  market gets slightly worse, so nothing deployed. The late title/seed-1 caution remains open; the 2026-27 live archive
  will show whether it persists.

## NBA awards: late-season temperature (14 Oct 2026) - not adopted
research/nba_awards_replay.py now takes AW_TEMPS (logit temperatures for the simulation, 1 = live) and AW_LATE_ONLY.
Last third of the season, 2010-2026, temperatures 1 / 0.8 / 0.6, chosen leave-one-season-out (research/nba_awards_temp_loso.py):
- MVP: favourite said 61% / won 82% (too cautious), but T 0.8 is worse on average held-out (-0.082) despite 14/17 seasons better: the
  few misses get punished hard. Sixth Man the same pattern (-0.037, 13/17). DPOY: favourite 38% / 29% (slightly long); T 1 kept in every fold.
- ROY: T 0.6 picked in every fold, +0.057 held-out (14/17), but the favourite then wins less often (84% -> 70%), which points to the
  sharper logit re-ranking candidates rather than better calibration. Not deployed; the live award chances stay as they are.

## NBA roster step, prompted by ESPN BPI (14 Oct 2026) - DEPLOYED
The user supplied ESPN's 7 Oct BPI pages (private reference only; www.espn.com robots.txt disallows anthropic-ai and the BPI
feed only gives end-of-season values for past seasons, so no ESPN history was collected). Our preseason ratings agreed with BPI
(r 0.84) except for big offseason moves (Leonard to TOR, Giannis to MIA, Brown and LeBron to PHI, Young back for WSH):
the live roster step moved no team by more than 0.94 points per 100.
research/nba_roster_replay.py tests the roster step on 2014-2026 (13 seasons): preseason rating + c x (new - old roster
strength), new team = first team played for that season, scored against the actual season net rating (MAE per 100 poss).
- live (c 0.55, plus-minus weight 0.045, last season only): 3.090
- c 1.5, plus-minus weight 0.09, last season x2 + season before, players back from a near-lost season (<500 min, >=1000 the
  season before) valued on the season before: 2.967 (better 10/13; nested LOSO over 60 settings 0.101, 10/13; walk-forward
  0.060, 7/10). At 20 / 41 games c 1.0 is best (+0.037 8/13, +0.047 10/13), so c fades 1.5 -> 1.0 over the first 20 games.
- two-season minutes for injury-shortened seasons: no gain. TypeSafe: c 1.5 + returning fix (53%).
Effect on the 7 Oct comparison: correlation with BPI 0.838 -> 0.850; e.g. LAC +1.2 -> -0.1, PHI +0.1 -> +1.9, BOS 5.0 -> 3.7.

## NBA player ratings (RAPM) in the preseason rating (14 Oct 2026) - DEPLOYED
research/nba_stints.py rebuilds 10-man lineup stints from free ESPN play-by-play (sportsdataverse espn_nba_pbp, 2010-2026;
season minutes match box scores r 0.9995; a few games skipped per season, 49 at most in 2019). research/nba_rapm.py fits
RAPM (ridge 3000 toward 2.5 x box-score value, last season + half the season before). research/nba_player_replay.py,
2014-2026 preseason, MAE vs season net rating: live (with today's roster step) 2.967; RAPM team strength alone 3.03-3.15;
60% live + 40% RAPM 2.865 (better 10/13); weight chosen leave-one-season-out 0.4 in 11/13 folds: +0.092, 10/13. RAPM settings
picked from 6 configurations on the same seasons. At 20 / 41 games RAPM adds nothing (-0.007, -0.022), so the share fades
40% -> 0 by game 20 (pipeline/nba_rapm.py, nba._player_mix). TypeSafe: deploy now (74%, confidence 0.61).
2026-27 preseason: correlation with ESPN BPI 0.850 -> 0.886 (RAPM strength alone 0.891); rating spread 4.03 -> 4.62.
Futures log loss not replayed (the weekly replay has no roster or player step).
- Follow-up (WSH/IND gap vs ESPN; TypeSafe 99%: bug, then age, then injury/tank weight):
  1. Bug fixed: the live roster step valued returning players (Haliburton, Young) on their previous full season on both the
     old and new roster, cancelling the return; the old roster now uses minutes actually played (as the replay did). IND +1.25.
  2. Development: +1.0 per 100 for each season short of 4 played, in the player-rating part: preseason MAE 2.865 -> 2.807
     (better 9/13 vs no development). Veteran decline worse; development applied to the team-results part too worse (-0.007
     to -0.197). Birth dates exist only in 2025+ roster files, so experience (seasons since first minutes) is the age proxy.
  3. Last season's late-season drop (tanking) and level: no gain (-0.008, -0.005). Not added.
  2026-27 after all three: WSH -9.8 -> -8.5 (BPI -3.4), IND -3.4 -> -2.9 (BPI +0.4), UTAH -5.6 -> -5.1 (BPI -2.2).
- Young-player ratings (TypeSafe 38%): harder ridge for players with <=1-3 seasons (x2/x4/x8) or a softer box prior for them
  (0 or 1.0 instead of 2.5): preseason MAE 2.803-2.820 vs 2.807 now. No gain; not deployed. The user's ESPN 7 Oct snapshot is
  archived privately (private repo forecast_archive/espn_reference) with a season-end scoring script, as a reference only.

## NBA playoff rotation from player ratings (14 Oct 2026) - DEPLOYED
TypeSafe's next NBA step (44%). In playoff series each team plays at its regular rating + (top-8 rotation strength with
minutes concentrated on the most-used players, power 1.5, cap 42 mpg - regular rotation strength), from the RAPM ratings and
this season's minutes to date (preseason: projected minutes). 14-season weekly replay 2013-2026 (research/replay_nba.py
BT_PO_K / BT_PO_GAMMA): k 0.5 +0.0022 (90% +0.0005 to +0.0040, 8/14); k 1.0 power 1.5 +0.0031 (-0.0003 to +0.0066, 8/14;
title 0.0907 -> 0.0827, conference 0.1808 -> 0.1729, late title 0.0860 -> 0.0769); k 1.0 power 1.0 +0.0027 (+0.0001 to
+0.0055, 10/14); k 1.5 over-confident conference mid-season. Largest NBA futures gain so far. Late title slope barely moves
(1.26 -> 1.23), so the title is still a little cautious late. TypeSafe chose k 1.0 / power 1.5 (68%). Regular-season
markets are unaffected. Live 2026-27 top playoff adjustments: DEN +4.1, MEM +2.9, TOR +2.4.
- Rotation by minutes per game instead of total minutes (so stars who missed games, e.g. Wembanyama, rank by role): k 1.0
  power 1.5 +0.0028 (8/14), power 1.0 +0.0014; title about the same but conference over-confident (late conference 0.1744 ->
  0.1871, mid slope 0.77). Total minutes (which also carry availability) stays. San Antonio's lower title chance is what the
  validated version says.
- Role and availability separated (TypeSafe 97%): role = minutes per game; each top player misses the playoffs with a
  probability from a 2011-2026 logistic (share of team games missed, share of the team's last 15 missed; calibrated 1-88%)
  plus 8% x share of the season still to play, drawn per simulated season (400 scenarios). +0.0020 (8-9/14) vs +0.0031 for
  the live total-minutes version; title 0.0852 vs 0.0827, conference 0.1781 vs 0.1729, worse late in the season too, where
  the availability term is small, so minutes per game is the weaker role measure. Not deployed; total minutes stays.
  (nba.PO_DELTA_SCEN and replay BT_PO_AVAIL kept as research options, off.)

## NBA: San Antonio / Denver vs markets and ESPN (14 Oct 2026) - two changes DEPLOYED
Markets (Kalshi/Polymarket avg, 13 Oct) SA 22%, OKC 21%, DEN 3% and ESPN agreed with each other; ours was OKC 38, DEN 14, SA 5.
TypeSafe: investigate inputs first (44%). Found: SA's team rating (+4.7) is dragged by earlier poor seasons (last season
+7.8, last 30 games +13.0); last season's playoff games were unused; the playoff rotation ranked Wembanyama (managed 28.6
mpg, 34.1 in the playoffs) 7th by total minutes. 14-season futures replay vs the live playoff rotation:
- last-playoff role (minutes x last season's playoff/regular mpg ratio, 4+ playoff games): +0.0011 (10/14)
- earlier seasons' playoff games counted in the team ratings: +0.0010 (90% +0.0002 to +0.0018, 9/14)
- both: +0.0019 (-0.0003 to +0.0040, 10/14); title 0.0827 -> 0.0807, conference 0.1729 -> 0.1677, division and playoffs
  slightly better. TypeSafe: both (72%).

## NBA: full live model in the weekly futures replay (14 Oct 2026)
research/replay_nba.py BT_FULL=1 adds the live roster step (coefficient 1.5 -> 1.0 by game 20) and the RAPM preseason mix
(40% -> 0 by game 20, with development) to the replay, alongside the playoff rotation (k 1.0, power 1.5), last-playoff role
and earlier playoff games (BT_PO_*). Rosters are point in time except: this season's team = first team played for, so a
player who misses the whole season is known to; BT_FULL_NOLEAK=1 keeps such players on last season's team to bound this.
14 seasons 2013-2026, 2,000 sims, mean log loss over title/conference/division/seed 1/playoffs:
- this morning's model 0.1778; playoff changes only 0.1726; full live model 0.1649 (+0.0125 vs this morning, 90% +0.0053 to
  +0.0191, better 12/14); leak-bounded 0.1653 (+0.0070 vs playoff-only, 9/14). Every market better: title 0.0907 -> 0.0753,
  conference 0.1808 -> 0.1549, division 0.2138 -> 0.2076, seed 1 0.0987 -> 0.0933, playoffs 0.3047 -> 0.2934.
- Calibration: mid-season conference slope 0.92, division 0.95 (fine); the late title is still cautious (slope 1.5-1.6).
  Late-only uncertainty fade (80% from game 60) +0.0001 and 15% lower team uncertainty +0.0002: noise, not adopted.
- History CSVs (model/replay/nba_*.csv), nba_score.json and nba_slope.json regenerated from the full-model replay.
- Portland's +4.7 playoff boost: Lillard back (valued on his last full season) and last season's 5-game playoff minutes
  ratio (Holiday 1.31, several bench players 0.5) concentrating the rotation; consistent with the tested method.

## NBA: late-title calibration and in-season player ratings (14 Oct 2026) - neither adopted
1. Playoff games 2011-2026 (1,339, vs each team's regular-season rating at the playoffs): margin = 1.22 x rating gap
   (90% 1.08-1.35) + 3.5 home (model 2.3); residual sd 13.9. Applied on top of the full live model (14-season replay):
   gap x1.2 -0.0001, extra home edge +1.3 +0.0000, both -0.0004, x1.1 + home -0.0001. The playoff rotation (top-8 from
   player ratings) already carries the stronger-team effect; the late title slope (about 1.5) moves to 1.4-1.5 but log
   loss does not improve (14 champions is little to calibrate on). nba.PO_HFA_EXTRA kept as a research option (0).
2. Weekly refit of player ratings with this season's lineup stints (research/nba_rapm.fit cutoff/wcur; replay BT_INS,
   BT_INS_PO): kept in the team rating from game 20 at 15% -0.0008 (8/14), 30% -0.0018; refit used only in the playoff
   rotation -0.0008 (4/14); 15% without the playoff part -0.0004. Conference late improves (0.1492 -> 0.1444 at 15%) but
   playoffs, division and seed 1 get worse; not deployed. The team-results rating already absorbs this season's form.

## NHL: shot-based playoff strength + fading playoff multiplier (14 Oct 2026) - DEPLOYED
TypeSafe first chose skater + goalie player ratings (81%), but that roster step had already been tested and rejected
(pipeline/nhl_roster.py, t about -1.2). Second pick, playoff goalie (64%): 227 playoff series 2011-2025, the starter's
edge over the team's season goalie average did not predict series (coefficient -0.9, 90% -2.35 to +0.75). The same check
found expected-goal differential predicts series far better than goal differential (log loss 0.676 -> 0.651).
10-season weekly replay (research/replay_nhl.py; shot differential per game x league shooting % as the xG stand-in):
- shots in the whole rating 20/40/60%: +0.0007/+0.0009/+0.0005 (Cup/conference better, regular-season markets worse)
- shot-based rating only in playoff series: 60% +0.0023, 80% +0.0028, 100% +0.0031 (90% +0.0008 to +0.0054, 7/10)
- 100% + fading playoff multiplier (x2 at season start -> x1 at game 82): +0.0046 (90% +0.0021 to +0.0072, 8/10);
  Cup 0.1154 -> 0.1076, conference 0.1928 -> 0.1774; division, best record and playoffs unchanged. x1.3 constant +0.0041.
TypeSafe 73%: both live (nhl_model.shot_rates, PO_FADE, simulate(po_delta)); the page compares with the previous model.

## NHL: injured players in live futures (15 Oct 2026) - DEPLOYED
Source: CBS Sports NHL injuries page (robots.txt allows; one fetch per run, 6 h cache): status "IR. Expected to be out
until at least <date>", "Day-to-Day". PuckPedia (robots blocks, Cloudflare), ESPN and TSN (robots block anthropic-ai) not used.
Calibration (research/nhl_absence_test.py; lineups from research/nhl_lineups_collect.py, NHL stats API per-game rows):
12,572 games 2015-2025, residual margin vs a season-to-date team rating regressed on tonight's lineup value minus the
team's usual (skaters: usual ice time x value; goalies: tonight's starter vs start-weighted usual). Values from the two
prior seasons. Walk-forward 2017-2025:
- goalies only (GSAx/60, shrink 10/30/60 h): scale 0.31/0.45/0.63, t about 2.6; log loss +0.00015 (5/9)
- + skaters xG on/off (rel): skater scale 0.131 (se 0.043); +0.00035 (6/9)
- + skaters points per 60 vs position (shrink 20 h): skater scale 0.341 (se 0.089), goalie 0.438 (se 0.176); +0.00051 (6/9)  <- live
Replacement level from the same data: skaters with <25 games for the team -0.04, third-string goalies -0.035.
Live (pipeline/nhl_absence.py): each player lowers his team's margin only in remaining games before his return date
(simulate(game_adj)); out for season also lowers playoff strength. A futures replay is not possible (no free historical
injury lists). TypeSafe 82% live; page shows live vs no-injury points, playoff and Cup chances.

## NHL: roster term from lineups + fitted goals/xG split (15 Oct 2026) - DEPLOYED (xG playoff switch not deployed)
TypeSafe's next pick (61%): roster strength from lineups. pipeline/nhl_lineup.py values each game's lineup with the
calibrated player values (SCALE_SK x skater ice-time-weighted values + SCALE_G x starter); roster term = gp/(gp+k) x
(mean of last N games - season-to-date mean). Replay (research/replay_nhl.py, 10 seasons, 2000 sims, base = live
settings NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_PO_FADE=1; scratch nhll/):
- with a preseason part (now vs last season's lineups): c0.5 +0.0004, c1 +0.0006 (CIs span 0); preseason worse at c1
  (0.2700 -> 0.2723; opening-night injuries read as roster change)
- in-season only: c1 n5 +0.0005 (90% +0.0002 to +0.0008, 7/10), c1.5 +0.0005, n10 +0.0005, n3 +0.0005 (8/10); every
  market equal or better  <- live (LIVE_C 1, N 5); injured players are added back into the live "current lineup" so the
  injury layer is not double counted
Goals vs xG split (MoneyPuck game xG, research/mp_team_games.py): regular-season xG share 20% vs 0% +0.0001 (5/10), 40%
vs 20% -0.0004; shot stand-in 40% vs 0% -0.0008. Live 0.4 -> 0.2 (TypeSafe 49% for 20%).
Playoff rating from real adjusted xG instead of shots: +0.0004 alone (6/10), +0.0005 on top of the roster term
(CI -0.0008 to +0.0018). TypeSafe 52/48 (no confidence): not deployed; NHL_XG=adj in the replay reproduces it.

## NHL: player-based team strength from shifts (15 Oct 2026) - in-season part DEPLOYED, preseason part NOT
TypeSafe's pick (99%). Data: NHL shift charts + play-by-play for every regular-season game 2014-2026 (15,000 games;
research/nhl_shifts_collect.py, workflow nhl-shifts.yml, output on branch nhl-shifts-data: stints, shots, players).
xG model (research/nhl_xg.py, leave-one-season-out logistic: distance, angle, type, rebound, strength): log loss about
0.21-0.23 vs 0.23-0.25 base; season totals within about 3% of goals.
Skater ratings (research/nhl_rapm.py): ridge on stints (two rows per stint, xG per 60, seconds-weighted, state dummies),
seasons y-1/y-2/y-3 weighted 1/0.5/0.25; prior = points/60 vs position (nhl_absence.values) x RAPM_KBOX. Goalies GSAx/shot.
Preseason test (research/nhl_player_strength_test.py, season GD per game, walk-forward):
- lam 2000-200000 without prior: players alone corr about 0.3-0.6, blend worse than prior
- roster change (this lineup - last season's, same ratings): no signal (b -0.001, se 0.34)
- + points prior KBOX 1: lam 150000 skater b 0.46 (se 0.17); lam 300000: blend better 7/9, RMSE 0.4755 -> 0.4690,
  skater b 0.49 (se 0.12); lam 600000 6/9 0.4697; goalie ratings add nothing preseason (corr 0.01-0.08)
Weekly futures replay vs live settings (nopre1):
- preseason prior blended walk-forward (NHL_PS=1): -0.0028 (90% -0.0071 to +0.0009, 2/10); 2017 -0.0226 (Vegas
  expansion: their roster rated weak, they reached the Final), 2024 -0.0097, 2025 +0.0068. Early slopes improve
  (Cup 1.62 -> 1.26) but log loss is worse. NOT deployed (TypeSafe 64% yes at low confidence; replay rule says no).
- roster term with the new ratings (NHL_LINEUP_VAL=rapm): +0.0003 vs points/GSAx values (5/10, every market slightly
  better); +0.0008 vs no roster term (90% +0.0001 to +0.0014, 8/10). TypeSafe 80%: DEPLOYED via
  model/nhl_player_ratings_2026.csv (static: ratings use earlier seasons only; rebuild each September).
TypeSafe next (78%): keep refining the player ratings (aging, finishing, in-season updates).

## NHL: player-rating refinements - shooting talent, age curves, in-season updates (15 Oct 2026) - NOT DEPLOYED
TypeSafe's pick (78%). research/nhl_rapm.py: RAPM_FIN (goals - xG per shot shrunk by RAPM_KF shots, x shots/60),
RAPM_AGE "a,b" (+a per 60 per year under 26, -b per year over 29; ages from research/nhl_bios_collect.py), ratings_at()
(refit with this season's games before a date); design matrix now vectorised (same output, far less memory).
Preseason goal-difference test (walk-forward, 2015-2025, RMSE vs prior 0.4755):
- base ratings 0.4690; + finishing 1.0/300 0.4665 (1.5/300 0.4667, 1.0/150 0.4667, 0.5/300 0.4673)
- + age 0.03,0.03 0.4631; 0.03,0 0.4660; 0,0.03 0.4628; 0.02,0.05 0.4619; 0.02,0.08 0.4616 (best, 2.9% vs prior, 7/9);
  0.02,0.12 0.4623. The veteran decline carries the age effect.
Weekly futures replay vs live (lvr, 10 seasons):
- refined ratings in the roster term: +0.0004 (90% 0.0000 to +0.0007, 7/10); playoff market slightly worse (0.3506 -> 0.3512)
- preseason blend with refined ratings: full -0.0007 (6/10), half weight +0.0002 (7/10, CI -0.0015 to +0.0019)
- in-season refits every 4 weeks in the roster term: +0.0001 (7/10); plus 20% blend toward current-lineup player
  strength: +0.0001 (5/10; playoffs better, Cup/conference worse). Same as the NBA: in-season refits add nothing.
TypeSafe: refined roster ratings no (68%), half-weight preseason no (76%). Live keeps model/nhl_player_ratings_2026.csv
(base ratings). Conclusion: a better season goal-difference forecast does not translate into better futures here.

## NBA: Polymarket comparison and depth-chart minutes (15 Oct 2026) - NOT DEPLOYED
TypeSafe's pick (50%): compare preseason futures with Polymarket (15 Oct, margin removed), then check inputs for the gaps.
Biggest conference gaps: DET ours 25% vs 7%, OKC 43 vs 31, CLE 16 vs 7, DEN 14 vs 6 (we are higher); MIA 1 vs 10, MIN 1 vs
10, SA 24 vs 32, PHI 13 vs 21, NY 10 vs 18 (market higher). Title correlation 0.82.
Inputs: MIA's Giannis (impact 3.67) projected at 1,039 minutes (36 games last season; the returning rule needs <500);
MIN lost Randle and Reid, added LaMelo Ball and Kuminga, Cody Williams (impact -2.1) projected 1,629 minutes; DET and OKC
top-3 on player ratings. TypeSafe: who is right is mixed (87%): market likely right on MIA/MIN, model on OKC/DET.
Depth-chart minutes (pipeline/nba.py NBA_DEPTH=1, depth_minutes; also in nba_rapm.team_strength): on a new roster whose
projected minutes exceed 82 x 240, the lowest-rated players lose minutes first. Moves only NY/SA/HOU in 2026-27 (MIN is under
budget, so it does not address Minnesota). 14-season replay vs live (0.1649): 0.1638, +0.0008 (90% -0.0003 to +0.0020, 6/14);
title/conference/division better, No. 1 seed 0.0933 -> 0.0936 and playoffs 0.2934 -> 0.2940 worse. TypeSafe 59% yes at
confidence 0.18; replay rule (no market worse) says no. Kept off by default.
Note: research/replay_nba.py defaults to 2022-2026; pass 2013 2026 for the 14-season replay (live settings BT_FULL=1
BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1 reproduce 0.1649 exactly).

## NBA: owner judgement overrides for projected minutes (15 Oct 2026) - LIVE, not replay-tested
model/nba_overrides.json (pipeline/nba.py _overrides/_apply_overrides, applied to the roster step, player-rating team
strength and playoff rotation; disabled in all replay scripts via N.OVERRIDES_PATH = ""; replay output verified unchanged).
- Giannis Antetokounmpo (MIA) 2,300 min: 2025-26 he played 30 of MIL's first 46 games, 0 in Feb, 6 in Mar, none after 15 Mar
  (63/74/68 games at 32-35 mpg the three seasons before). Miami 40.9 -> 46.2 wins, conf 1.1% -> 12.4%, title 0.2% -> 4.1%.
- Cody Williams and Trey Lyles (MIN) 700 min each: Minnesota 41.0 -> 43.6 wins, conf 0.9% -> 2.1%, title 0.4% -> 1.1%.
TypeSafe: Giannis yes (66%), Minnesota yes (72%). Polymarket at the time: MIA conf 10% / title 3.6%, MIN 10% / 6.3%.

## NBA: general healthy-minutes projection (15 Oct 2026) - NOT DEPLOYED
TypeSafe's pick (71%; it also judged the NBA model not meaningfully improvable, 85%). pipeline/nba.py NBA_HM (projected
minutes = minutes per game over two seasons x expected games: last season + season before + 1 pseudo-season of 70 games),
NBA_HM_UP (keep the larger of this and actual minutes), NBA_HM_AGG (a traded player's whole season, all teams, instead of
his longest stint). Giannis 1,039 -> 1,877 projected. 14-season replay vs live 0.1649:
- HM up -0.0005 (7/14); HM up + whole season 0.0000 (8/14); HM replace (can lower) -0.0010 (5/14);
  whole season only +0.0002 (8/14; division and No. 1 seed worse). Conference and late title slightly better throughout,
  division and No. 1 seed worse. All off by default; the owner's hand overrides (model/nba_overrides.json) stay.

## 2026-10-15 NHL news trigger (operations, no model change)
- CBS injury cache 6 h -> 1.5 h, so every 2-hourly refresh reads a fresh list (worst-case lag ~8 h -> ~2 h).
- Hourly availability job runs `pipeline/nhl_news_trigger.py`: fresh CBS list vs the last published list, each change valued
  with the model's own absence costs (goals/game x games missed). A new absence or return worth >= 2.0 goals (TypeSafe 60%)
  starts 'Refresh site' immediately; 6 h cooldown per player; decisions logged to injury-monitor availability/news_trigger.jsonl.
- NBA: not triggered, because the availability layer is not used in NBA futures (no measurable replay gain).

## 2026-10-15 Team-gap audit: our model vs the market (NHL, NFL) - no model change
- Largest persistent gaps (6 days): NHL playoffs SJS -32pp, FLA -27, TOR -22, SEA +22, MTL -21; NFL BAL div/playoffs -25, SF div +21.
- NHL 2014-2022 (216 team-seasons, ~6 games in): market strength from first-6-game closing moneylines vs replay p_playoff.
  LOSO log loss model 0.549, market 0.549, both 0.543: the market adds real information (coef 4.4 +/- 1.6).
  Tested causes (last-season goal difference, team age, ice-time share of new players from lineups): together they explain
  ~15% of the gap each, but none predicts playoffs beyond the model; the predictive part is the unexplained residual.
- NFL 2006-2025 games, weeks 4-8: result ~ 0.15 model margin + 0.98 spread; gap explained 4% by points-to-date and last
  season (not predictive); residual predictive (0.51 +/- 0.07). Model margins alone too compressed early (x1.24 +/- 0.08).
- TypeSafe 60%: no systematic fixable cause; treat team gaps as market knowledge, not value. NFL early-stretch challenger
  (38%) not pursued for now.

## 2026-10-15 NHL: GPT critique - ablations in the 10-season replay; playoff fade 1 -> 3 DEPLOYED
Live settings reproduced exactly in research/replay_nhl.py (NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_PO_FADE=1 NHL_LINEUP_C=1
NHL_LINEUP_N=5 NHL_LINEUP_PRE=0 NHL_LINEUP_VAL=rapm RAPM_LAM=300000 RAPM_KBOX=1; 2016 identical to nhll/lvr).
- Preseason widening TAU_PRE 1.0 / 1.25 / 1.5: same (0.0000 / +0.0001); 2.0 -0.0005. Unchanged.
- Prior scale 0 (everyone average) -0.0164 (0/10); 0.8 -0.0007; 1.2 -0.0002; 1.4 -0.0013. Prior out-of-sample R2 0.33
  (2014-2025, slope 0.94), but 2023-2025 it trailed half of last season's goal difference.
- Playoff fade (GPT expected it too aggressive): 0 -0.0015, 0.5 -0.0006, 1.5 +0.0004, 2 +0.0007, 3 +0.0012 (90% +0.0004
  to +0.0019, 8/10), 4 +0.0014, 6 +0.0017, 9 +0.0019 (CI +0.0002 to +0.0034, 7/10); only title and conference change.
  Walk-forward choice from {0..3}: 3 every season, +0.0012 vs live (6/8). Early Cup slope 1.64 -> 1.43 (3), 1.30 (9):
  still too flat early, root cause not found. TypeSafe 43% deploy 3 (investigate root cause 38%).
- 84-game season from 2026-27 (found by GPT): award projections, playoff fade and news trigger fixed.
- TypeSafe next: stop NHL work (75%).

## 2026-10-15 NHL: GPT follow-up - shadow fade 1.0 archived; three cheap prior tests NOT deployed
- Live fade 3.0 frozen as provisional; the previous 1.0 now runs as an archived shadow (s_final, s_cup) for 2026-27 scoring.
- Prior knobs (pipeline/nhl_model.py, research only): NHL_PRIOR_PTS (last-season points residual beyond goal difference),
  NHL_PRIOR_PO (last season's playoff goal difference / 82), NHL_PRIOR_WIN (last N training seasons), NHL_PRIOR_HL
  (half-life weighting). k and tau are re-estimated per fold with each prior.
- Out-of-sample season GD RMSE (2014-2025; live 0.4586, 2023-25 0.4733): pts 0.4606, po 0.4590, win8 0.4615, win5 0.4622,
  hl4 0.4598: all worse, including in the weak 2023-25 seasons.
- 10-season replay vs live (fade 3): pts 0.0000 (4/10), po +0.0004 (CI -0.0014 to +0.0023, 5/10; title/conference better
  and early slopes near 1, but division and Presidents' Trophy worse), hl4 -0.0003 (3/10), win8 -0.0003 (1/10).
  None deployed (replay rule: no gain without harming another market).

## 2026-10-15 NHL: GPT round 3 - playoff-only prior GD and tiebreak audit (no model change)
- The earlier playoff-GD test had added it to the general prior. Playoff-only version (research/replay_nhl.py
  NHL_PO_PRIOR_K): last season's playoff GD / (playoff games + K) added to the playoff-series rating only, faded like the
  prior (k/(gp+k)). vs live fade 3: K20 -0.0010 (3/10), K40 +0.0001 (3/10), K80 +0.0004 (CI -0.0010 to +0.0020, 3/10);
  K40 with fade 1 vs fade 1: +0.0006 (3/10). Early slopes move to ~1 (K40: Cup 0.99) but log loss does not improve.
  Not deployed.
- Tiebreak audit on 10 completed seasons: simplified order (points, RW, ROW, GD) vs era-aware fuller order (points,
  RW from 2019-20 else ROW, ROW, wins, GD): 0 division winners, 1 playoff spot, 0 Presidents' Trophies differ; 2 team
  pairs tied through wins (H2H needed). Exact tiebreakers deferred with this evidence.
- Shadow fade 1.0 now uses the same simulation draws as live (common random numbers).
- Prospective protocol (2026-27 onward): primary score = combined Cup + conference log loss of live (fade 3) vs shadow
  (fade 1), weekly snapshots from the forecast archive, averaged within each season; Cup and conference reported
  separately; no verdict from one season alone.
- Naming: fade 1 = 2x preseason playoff-gap stretch (previous live, now shadow); fade 3 = 4x (live). Both fade to 1x by
  the end of the regular season, so once the playoffs start the two give identical series probabilities.
- Outcome labels now use the official end-of-season order (nhl_model.final_comp: points, RW from 2019-20 else ROW, ROW,
  wins, GD) in nhl_model.backtest and research/replay_nhl.py. Fixture tests/test_nhl_tiebreak.py: 2015-16 Detroit over
  Boston on ROW (both 93 points) - the old points/wins/GD order labelled Boston as the playoff team.
- Series-level telemetry (rating gap, home ice, series probability, winner, timestamp, version) to be built before the
  2027 playoffs, when the playoff schedule format can be checked.
