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
