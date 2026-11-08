# M2 (AFL tau schedule) discovery and evaluation result, 9 Nov 2026
Rule: research/FUTURES_BAKEOFF_RULE.md Amendment 1 (frozen before this run). Scripts: research/m2_grid.py, research/m2_eval.py, replay_afl.py (BT_M). Data: regenerated replays with current code, scratch only.

## Discovery (AFL 2013-2018, 6 seasons; pooled playoff log loss, clip 0.001/0.999)
Live (1,1,1) 0.3203. Best of the registered 27: (0.7, 1.4, 1.4) 0.3161 (edge on m2, m3, and m1 at 0.7). One step outward (registered): best (0.7, 2.0, 2.0) 0.3156; still on the m2/m3 edge, not extended. Gain over live 0.0047 log loss (weak fit, as stated). Registered prediction was m1 = 1.0, m2 in [0.85, 1.0], m3 in [1.2, 1.4]: FOUND m1 0.7, m2 2.0, m3 2.0, so the prediction of the constants was WRONG (more tau in mid/late season, less early).
Runtime: about 7 s per replay-season; the whole grid took 3.5 minutes.

## Evaluation (arm (0.7, 2.0, 2.0) vs live, eval 2019, 2021-2026 = 7 seasons, 2020 dropped, 10,000 paired draws, seed 20261108, lambda 1.0, |slope|>5 in 0.0% of draws)
    eval seasons [np.int64(2019), np.int64(2021), np.int64(2022), np.int64(2023), np.int64(2024), np.int64(2025), np.int64(2026)], draws 10000, lambda 1.0, clip 0.001/0.999
    playoff  preseason      n  126 live slope 1.09 arm slope 0.86 contrast -0.231 [10% -0.258, 50% -0.230, 90% -0.206] half-width 0.026 |slope|>5 0.0%  LL live 0.5952 arm 0.5944 diff -0.0008
    playoff  first quarter  n  684 live slope 0.99 arm slope 0.78 contrast -0.210 [10% -0.246, 50% -0.210, 90% -0.180] half-width 0.033 |slope|>5 0.0%  LL live 0.5111 arm 0.5192 diff +0.0081
    playoff  third quarter  n  756 live slope 0.62 arm slope 0.82 contrast +0.194 [10% +0.161, 50% +0.198, 90% +0.233] half-width 0.036 |slope|>5 0.0%  LL live 0.4061 arm 0.3783 diff -0.0277
    playoff  last quarter   n  828 live slope 0.78 arm slope 0.83 contrast +0.055 [10% +0.045, 50% +0.055, 90% +0.064] half-width 0.009 |slope|>5 0.0%  LL live 0.1804 arm 0.1745 diff -0.0058
    top4     third quarter  n  756 live slope 0.78 arm slope 1.00 contrast +0.221 [10% +0.174, 50% +0.219, 90% +0.297] half-width 0.062 |slope|>5 0.0%  LL live 0.2795 arm 0.2716 diff -0.0079
    finals   third quarter  n  756 live slope 1.08 arm slope 1.45 contrast +0.365 [10% +0.291, 50% +0.370, 90% +0.444] half-width 0.076 |slope|>5 0.0%  LL live 0.2346 arm 0.2397 diff +0.0052

## Reading (Claude; for DeepSeek and TypeSafe to rule on)
- Primary decisive test: AFL Q3 playoff slope 0.62 -> 0.82 (toward 1), paired 90% interval [+0.16, +0.23] excludes 0, half-width 0.036 < 0.20. NOT falsified. (Stored pack figure 0.69 was the 14-season pool; this is the 7 eval seasons.)
- Registered predictions that FAILED: Q1 moved -0.21 (predicted < 0.10) and preseason -0.23, both away from or past 1 (live 0.99 / 1.09 -> 0.78 / 0.86 = too extreme). Q1 playoff log loss WORSE by +0.0081. Finals slope 1.08 -> 1.45 (too flat), finals log loss WORSE by +0.0052 (the rule said no-harm should hold on finals).
- Gains: Q3 playoff LL -0.0277, last quarter -0.0058, top4 -0.0079; Q3 top4 slope 0.78 -> 1.00.
- Caveats: constants outside the registered range and chosen on 6 seasons; the paired interval is narrow because arm and live share the same simulations (it measures the contrast, not generalisation); 7 eval seasons is about 56 playoff outcomes per checkpoint-pool.
- Ruling needed: does a pass require no worse than +0.002 in EVERY stage (then FAIL: Q1 +0.0081) or on the pooled decision market only?
