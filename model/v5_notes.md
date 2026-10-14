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
