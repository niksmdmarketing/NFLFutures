# Notes for NFL model v5 (v4 stays frozen through the 2026 season)

- QB layer: point-in-time test 2019-2025 favours lambda ~0.75 over 0.5 (model/qb_backtest.json).
- Match-level calibration vs outcomes 2006-2025: our pre-game probabilities are under-confident (logistic slope ~1.22;
  model/match_vs_market_nfl.json). Recheck sigma/tau jointly for v5.
- Closing lines remain more accurate than our ratings at every stage; best log-odds weight on our ratings ~0.05-0.2.

## Futures replay 2011-2025, simulation layer (13 Oct 2026)
- Weekly replay of v4 extended to 2011-2021 (rating weights in-sample there) for diagnosis; 2022-25 stays the out-of-sample check. The 2011-21 CSVs are not published (in-sample).
- v4 is too cautious in both periods: conference winner slopes 1.3-1.7 at every stage, No. 1 seed 1.3-1.5, division/playoffs 1.0-1.4 early.
- Candidates (research/replay_nfl.py BT_TAU / BT_SCALE / BT_TAUFADE, 1,500 sims, mean log loss over five markets):
  tau 5 -> 3.5: 2011-21 +0.0022 (9 of 11 seasons), slopes about 1.0-1.3; 2022-25 better in 2022-24 (+0.002 to +0.005) but 2025 -0.016, mean -0.0012.
  rating_scale 1.0 / 1.1, tau fade 60%, scale 1.0 + fade: in-sample +0.001 to +0.0015, out-of-sample -0.0004 to -0.0018 (2025 again).
- Decision (TypeSafe 97%): keep v4; tau about 3.5 is the leading v5 candidate. Note tau 3.5 lowers total per-game sd to about 12.4 vs 13.4 observed, so sigma should be re-fitted jointly. Recheck with the 2026 live archive.

## Playoff simulation and walk-forward weights (13 Oct 2026)
- Game-level check (research/nfl_playoff_calibration.py, 2011-2025, point-in-time ratings): late regular-season games are
  too flat (probit sharpness k 1.20, 90% 1.07-1.33). Playoff games: strength gaps no more decisive (k 0.85, wide), but home
  teams won 65.8% vs 60.2% expected: playoff home edge about 4.1 points (90% 1.9-6.8) vs 1.8 assumed. Walk-forward estimates
  from earlier playoffs only were 3.3-8 points for every test season 2013-2025.
- Walk-forward weights (research/nfl_walkforward_weights.py): the offline weight fit is reconstructed (game-level ridge on
  point-in-time feature differences, alpha/k/r from settings). Coefficients differ from the frozen ones (correlation 0.66)
  but game-margin accuracy is the same (RMSE 13.48 vs 13.52 in 2010-21; 12.86 vs 12.82 in 2022-25). Season s uses weights
  fitted on 2010..s-1 only, giving 13 out-of-sample replay seasons (2013-2025) for a v4-like model.
- Futures replay on those 13 seasons (1,500 sims; gain = lower mean log loss over five markets):
  playoff home edge 4.0: +0.0008 (90% +0.0003 to +0.0013), better 10 of 13; conference +0.0034, title +0.0008, others unchanged.
  playoff home edge 3.0: +0.0005 (+0.0001 to +0.0008). tau 3.5: +0.0007 (-0.0026 to +0.0036), make-playoffs worse.
  tau 3.5 + edge 4: +0.0013 (-0.0023 to +0.0045). scale 1.0 + edge 4: +0.0011 (-0.0011 to +0.0030).
- Decision (TypeSafe 95%): run "playoff home edge 4.0" as an archived challenger beside v4 (settings challenger_v5,
  simulate(hfa_post=...)); v4 live output unchanged. No. 1 seed and conference remain somewhat timid; regular-season game
  sharpness (k 1.2) is the open item, but tau/scale fixes are not yet robust.

## Game-level sharpness, walk-forward (14 Oct 2026)
Fitting the late-regular-season sharpness k on earlier seasons only and applying it to the next season (2014-2025):
k drifts from 1.36 to 1.20 and the out-of-sample log loss is unchanged (-0.0003, better in 6 of 12 seasons). The k 1.2
finding is real on average but not stable enough to fix by scaling; consistent with the tau 3.5 futures result.

## v5 candidate rebuilt (14 Oct 2026)
research/replay_nfl.py now takes BT_QB (quarterback layer as live; expected starter = the QB who took the team's first
dropback in its next game). 13 walk-forward seasons 2013-2025, 1,500 sims, vs frozen v4 without the QB layer:
- playoff home edge 4: +0.0009 (90% +0.0003 to +0.0014), 11/13
- + QB layer 0.5: +0.0013 (+0.0004 to +0.0021), 10/13 (helps in season, slightly worse before the season); 0.75 and 1.0 worse
- + tau 4.0 / sigma 12.0 (same total spread): +0.0020 (+0.0002 to +0.0036), 9/13; late conference slope 1.49 -> 1.22
- + tau 3.5 / sigma 12.23: +0.0020 (-0.0005 to +0.0042), 9/13
- Roster snap continuity (share of last season's snaps back by week 2, 2014-2025): no relationship with how much of last
  season's strength carries over (interaction -0.25, 90% -0.88 to +0.34). Dropped.
TypeSafe (75%): challenger_v5 = edge 4 + tau 4 / sigma 12.0 on the live v4 ratings (which include the QB layer). Shown on the
futures page beside v4 (playoffs, division, conference, Super Bowl); v4 stays live until 2027.

## Rating inputs (14 Oct 2026) - recency adopted for the v5 candidate
pipeline/nfl_engine.py rebuilds the v4 components per game point in time with options; game-level walk-forward 2013-2025
(ridge on standardised components, win log loss / margin RMSE): baseline 0.6385 / 13.34. Recency half-life 3-6 weeks
+0.0012 to +0.0018 (7/13), half-life 4 + team-effect shrinkage 60 +0.0017 (9/13); garbage-time filter -0.0006; early-down
EPA + pass rate over expected -0.0017; season-before-last components -0.0029.
Futures replay (13 walk-forward seasons, with edge 4 / QB 0.5 / tau 4 / sigma 12): recency ratings 0.2347 vs 0.2360 for the
candidate on v4 ratings (+0.0012, 90% -0.0005 to +0.0026, better 11/13, every market better); the same engine without
recency -0.0004, so the gain is the recency. Total vs v4: +0.0032. TypeSafe 90%: candidate updated (run.py; weights in
model/challenger_v5_weights.json fitted 2010-2025). Live check 2026 week 5: correlation with v4 ratings 0.97.

## Player model from play-level participation (14 Oct 2026) - no gain, not adopted
research/nfl_participation.py: 2016-2025 scrimmage plays with the 11 offensive and 11 defensive players (nflverse
pbp_participation; 88-100% of plays). research/nfl_player_ratings.py: ridge (3000) of play EPA on offensive and defensive
player effects, earlier seasons at 0.5 per year back, point in time each week (top: Tagovailoa, Allen, Jackson; Bosa).
Team strength = sum of player effects x expected snap share, tested as an extra input on top of the recency engine,
game-level walk-forward 2019-2025 (research/nfl_player_test.py):
- with the lineup = players who took a snap in that game: +0.0015 (net), +0.0028 (injury delta), +0.0090 jointly, 7/7.
  LEAKY: in-game injuries and garbage-time backups reveal the result. Discarded.
- with the lineup known before kickoff (previous game's players minus Out/Doubtful on that week's official report):
  net +0.0002 (4/7), injury delta -0.0007 (4/7), jointly -0.0004 (4/7), usual-lineup strength +0.0001. No gain.
Conclusion: with free data, non-QB player effects add nothing measurable over team ratings + the QB layer; the earlier
non-QB injury idea (TypeSafe: gain too small) is consistent with this. Not adopted.

## QB-availability prior (16 Oct 2026) - added to the v5 candidate (in season only)
Prompted by the 2026 model-vs-market gaps (Baltimore: Jackson started 12/17 in 2025; Cincinnati: Burrow 7/17). The prior
half of the rating describes last season's QBs, while the QB layer only compares with this season's main QB.
Candidate: w_prior x (value of this season's main QB - dropback-weighted value of last season's QBs), w_prior =
k_pass / (dropbacks so far + k_pass) (research/nfl_qb_prior_test.py, ratings.qb_prior_adj).
- Game level 2008-2025, weeks 1-10 (2,651 games, point in time): free slope 0.96 (se 0.22); margin RMSE 13.566 -> 13.518
  at weight 1.0; walk-forward weight choice better in 11/15 seasons. The market already prices it (market-minus-model gap on
  the term: slope 0.75, corr 0.31); beyond the closing spread it adds 0.27 +/- 0.23.
- Futures replay, 13 walk-forward seasons on the v5 candidate (BT_QBPRIOR in research/replay_nfl.py): including the
  preseason checkpoint +0.0006 (6/13, preseason clearly worse); in season only weight 0.75 +0.0011 (6/13), weight 1.0
  +0.0013 (90% -0.0008 to +0.0035, 6/13), every market equal or better on average; on v4 ratings +0.0012 (6/13).
- 2026 week 5 effect: BAL +1.1, CIN +1.5, HOU +0.8, NYG -0.5 (toward the market), SF +1.2 (away), MIN +2.5, MIA -2.1.
TypeSafe 60% (low confidence 40%): added to challenger_v5 at weight 1.0 (settings qb_prior). v4 unchanged.

## 16 Oct 2026: early-season rating stretch (TypeSafe's top idea, 33%, low confidence) - rejected
BT_EARLY in research/replay_nfl.py: ratings x (1 + e x (1 - games played / 10)) from week 1, on the live v5 candidate
(13 walk-forward seasons, 1,500 sims): e 0.25 -0.0003 (90% -0.0017 to +0.0008, 7/13), e 0.5 -0.0012 (7/13). Conference
slightly better, playoffs/division worse. Not added. The game-level compression (x1.24) does not carry over to futures.

## NHL roster continuity (17 Oct 2026) - no gain, not adopted
research/nhl_continuity_test.py: share of last season's skater ice time in the opening lineup, interaction with the preseason prior, walk-forward 2019-2025 (281 team-seasons): RMSE 0.4922 -> 0.4918, better 2/7, interaction -1.24 (se 0.83).

## Caution investigation, step 1: are the rating gaps too small? (20 Oct 2026) - no
Prompted by a review (second assistant, adopted with TypeSafe 99%/100%): diagnose where the caution sits before changing shrinkage.
research/nfl_caution_diagnosis.py: walk-forward game predictions 2013-2025 from the engine caches (each test season fitted on earlier seasons only); slope of actual margin on predicted margin, and win sharpness k (probit on predicted margin / residual sd).
- v5 engine inputs (h4a60): margin slope 0.88 (se 0.04); by weeks 1-4 0.78, 5-9 0.98, 10+ 0.87; win k 0.95 (se 0.05). v4 inputs (base): 0.89, k 0.95. Same with no ridge on the final regression.
- By season the slope is below 1 in 11 of 13 (2019 1.02, 2024 1.10); 2025 0.91, so 2025 is not unusual here.
- So the team-rating gaps are, if anything, slightly too WIDE in game terms, not too small; v4's rating_scale 0.89 roughly cancels this. Lowering shrinkage would widen them further, so the "fix it at the source" idea is not supported as stated.
- This does not match the earlier under-confidence findings (pre-game probability slope ~1.22 in model/match_vs_market_nfl.json; late-season k ~1.2 in research/nfl_playoff_calibration.py). Those use the live v4 path (frozen weights trained on 2010-2021, so in-sample for those years, the QB layer, scale 0.89, S = sqrt(sigma^2 + 2 tau^2)). Next: reconcile the two on identical games before any change; if the gap is real it sits in that path or in the season simulation, not in the rating shrinkage.

## Caution investigation, step 2: same games, both rating paths (20 Oct 2026)
research/nfl_caution_same_games.py, results research/nfl_caution_same_games.json. Identical regular-season games 2013-2025 (3,407), identical point-in-time features (v4 components, no recency, no QB layer).
Quantities: margin slope = actual margin on predicted margin (1 = gaps right, >1 = too small); probit k = sharpness of P(win) on gap / 13.39 with a free home term (the earlier "1.2" measure).

| Rating path | margin slope all | 2022-25 (out of sample) | 2025 | probit k all | k 2022-25 | gap sd |
|---|---|---|---|---|---|---|
| Engine, walk-forward (before any scaling) | 0.89 (0.04) | 0.89 (0.07) | 0.91 | 0.96 | 0.98 | 5.8 |
| v4 frozen weights, raw dR | 1.01 (0.04) | 0.95 (0.07) | 0.96 | - | - | 5.4 |
| v4 as simulated (0.89 x dR) | 1.13 (0.05) | 1.06 (0.08) | 1.08 | 1.22 | 1.16 | 4.8 |

Answers: the 0.88 of step 1 is before any scaling (engine predictions). The earlier 1.2 is a different quantity (win sharpness, not margin slope) on the v4 path after the 0.89 rating_scale; on the same games and that path it reproduces (1.22). The two are reconciled: v4's raw gaps are about right, and the 0.89 scale is what makes v4's simulated games look cautious. Most of it is in 2013-21, where v4's weights were fitted; out of sample (2022-25) v4 is 1.06 +/- 0.08, i.e. not clearly cautious at game level. The v5 candidate applies the same 0.89 to engine ratings whose gaps are about 12% too wide, so v5 lands close to 1 at game level.
Implication: game-level caution is small out of sample; the futures-level caution (conference winner slopes 1.3-1.7) is more likely in the season simulation (season-long uncertainty tau and how long it persists, playoff setup) than in the ratings. Next: check win-total spread and title-favourite calibration in the replay outputs, by season, including why 2025 deteriorates.

## Caution investigation, step 3 (20 Oct 2026)
Full summary and learnings: research/NFL_CAUTION_DIAGNOSIS.md. Short version: single games and win totals are about right out of sample; the caution is in the conference-winner market from week 4 (v4 slopes 1.5-1.7, intervals above 1; v5 1.3-1.6) and the late No. 1 seed (1.4). v5 pre-season expected wins too spread (slope 0.84); 2025 was a high-surprise season where that hurt.

## Jalen Hurts out for the season (20 Oct 2026)
Confirmed 19 Oct (Eagles/agent statement; ESPN): blood clots, on IR since ~17 Oct, out for 2026; Tanner McKee starts. The live model already had McKee as PHI expected QB for every remaining game (depth chart after the IR move): v4 qb_adj -2.27, v5 the same (no one-game Out note). TypeSafe (100