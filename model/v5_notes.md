# Notes for NFL model v5 (v4 stays frozen through the 2026 season)

- QB layer: point-in-time test 2019-2025 favours lambda ~0.75 over 0.5 (model/qb_backtest.json).
- Match-level calibration vs outcomes 2006-2025: our pre-game probabilities are under-confident (logistic slope ~1.22;
  model/match_vs_market_nfl.json). Recheck sigma/tau jointly for v5.
- Closing lines remain more accurate than our ratings at every stage; best log-odds weight on our ratings ~0.05-0.2.
