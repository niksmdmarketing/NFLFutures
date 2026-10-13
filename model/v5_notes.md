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
