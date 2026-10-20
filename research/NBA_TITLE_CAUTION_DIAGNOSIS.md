# NBA late-season title "caution": diagnosis from existing replay files (20 Oct 2026)

No model change. Source: the full-live-model weekly replay, model/replay/nba_<season>.csv, 13 seasons (2013-2026 without 2020), 13 champions. Stages are quarters of each season's checkpoints.

## Calibration of the title market by stage (logistic intercept and slope; slope above 1 = too cautious; season-bootstrap 90%)
| Stage | Intercept | Slope (90%) |
|---|---|---|
| Pre-season | 0.57 | 1.25 (0.90-1.93) |
| First quarter | 0.51 | 1.27 (1.01-1.77) |
| Second quarter | 0.27 | 1.19 (0.89-1.91) |
| Third quarter | 0.56 | 1.36 (1.09-2.08) |
| Last quarter | 0.64 | 1.42 (1.14-2.14) |

## Where it comes from (last half of the season; title probability per checkpoint, averaged)
| Title-favourite rank at the checkpoint | Predicted (Q3 / Q4) | Actual share of checkpoints won by that team (Q3 / Q4) |
|---|---|---|
| 1st | 0.45 / 0.44 | 0.52 / 0.51 |
| 2nd | 0.18 / 0.20 | 0.20 / 0.23 |
| 3rd | 0.11 / 0.12 | 0.16 / 0.12 |
| 4th-6th | 0.16 / 0.16 | 0.11 / 0.14 |
| 7th and below | 0.09 / 0.08 | 0.01 / 0.00 |

- The slope above 1 is mostly the long-shot tail: teams outside the top six late in the season carry about 8-9% of the title probability between them and won none of the 13 titles. The leading favourite is slightly under-rated (about 0.44 vs 0.51), driven by Golden State 2017/2018 and Boston 2024.
- Late-season favourites won 5 of 13 titles (2015, 2017, 2018, 2023, 2024) against about 5.8 expected, so the favourite is not clearly under-rated.
- Given the conference finalists (last checkpoint, title probability divided by conference-final probability): 12.9 predicted titles vs 13 actual; by rank 6.8/7, 2.8/3, 2.0/3, 1.1/0. Calibrated once the final four are set.
- Among playoff teams, the leading title chance among them: 5.6 predicted vs 7 actual; teams ranked 9th-20th in that list: 0.5 predicted vs 0.

## Reading
The caution is an over-rated long-shot tail that arises before the conference finals (upsets in the first two rounds are given too much room), not a general under-rating of favourites, and the sim is calibrated once the final four are known. This matches the earlier playoff-game finding (WORKLOG 14 Oct 2026: playoff margins = 1.22 x rating gap, 90% 1.08-1.35), but that correction applied directly (gap x 1.2, extra home edge) did not improve log loss in the 14-season replay (-0.0001 to -0.0004), and 13 champions cannot calibrate much.
Same pattern as the NFL investigation: the "too cautious" slope comes from the tails and from few outcomes, and a blanket sharpening is not supported.

## Decision
No change. Watch the long-shot tail in the 2026-27 live archive (title probability carried by teams ranked 7th and below after the All-Star break, and conference-final calibration).
