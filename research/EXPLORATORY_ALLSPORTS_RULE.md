# All-sports exploratory search for better futures models (frozen 9 Nov 2026, before any arm is scored)
Owner direction: try every sport, assume nothing. DeepSeek leads (relays 020, 021); Claude runs; TypeSafe on decisions. Prices are never inputs.

## Status of every number: EXPLORATORY and IN-SAMPLE
No sport has a clean untouched block (WORKLOG: NBA TAU_PRE 2.0 and current-season weight 8 chosen on 2013-26; NBA TAU_FADE tested on all 14 seasons; AFL/NBL tau, fade, GAME_SD, drift, df tests ran on the full pools; AFL 2019-26 spent by the M2 rule; NHL 2015-25 exposed by the canonical rule). So NOTHING can pass, nothing is adopted, no live change. Output: (i) ranked table per sport, (ii) one forward-shadow candidate per sport for 2027, (iii) null arm per sport. Every number labelled in-sample.

## Arms (frozen; live values in brackets)
- NBA (9): DeepSeek's 1.0/1.25/1.5 were not valid fade shares (BT_TAUFADE is a 0-1 share of TEAM_TAU removed by game 82); Claude mapped to the shares already used in WORKLOG, flagged for DeepSeek review: TAUFADE {0, 0.5, 0.8} x TEAM_TAU {1.1, 2.2 (live), 3.3}, TAUFADE_START 9. Plus the single most informative arm: TAU_PRE 1.0 (live 2.0), nothing else changed. Null = live.
- AFL (6): BT_M = 1,x,x from gp >= 10 (BT_M_FROM=10), x {1.4, 2.0, 2.8} x GAME_SD multiplier {1.0, 1.1}. Most informative: x 2.0, mult 1.0.
- NHL (9, run on the GitHub Action, cannot run here): TAU_PRE {1.0, 1.25, 1.5} x PRIOR_SCALE {0.8, 1.0, 1.2}. Most informative: TAU_PRE 1.0, PRIOR_SCALE 1.0.
- NBL (6, Action): TAU0 {2, 4 (live), 6} x TAU_FLOOR {0.15 (live), 0.5}. Most informative: TAU_FLOOR 0.5 at TAU0 4.
- NFL (4, 2022-2025, descriptive only, cannot nominate): BT_SCALE {0.9, 1.1} x BT_SIGMA {0.9, 1.1} as multiples of the live values.
Family: 34 arms. Every arm run enters the table, including failures. Lever and direction fixed here. No re-parametrising from the same pool.

## Scoring (per sport)
- Null arm (live vs live) first; half-width recorded before any arm is scored.
- Per-arm: calibration slope and paired log loss on every stage (preseason, quarters) and market the replay holds; paired Bayesian season-cluster bootstrap (exponential weights, seed 20261108, clip 0.001/0.999, small L2).
- Candidate rule: highest pooled gain on the discovery block (earliest 60% of seasons) subject to per-stage, per-market no-harm (no stage/market worse than -0.002 at the 90% lower bound) and holding with its best season removed; reported on the later 40% and leave-one-season-out (both leaky; they test reproducibility, not validity).
- Decision market per sport, must move toward slope 1 on the check block: NBA preseason playoff; NHL preseason r3-r2 contrast toward 0; AFL Q3 playoff (reported, not gating). Moving away, or toward with the interval containing 0, names NO 2027 candidate. This clause overrides every other gain in the run, including win totals and other stages.
- Win totals: AFL S2/S3/S4 (full distribution saved); NBA S2 (mean_wins); NHL S2 (pts_mean); NBL/NFL none. Title/finals/seed1 descriptive only.
- Cross-sport: the same lever direction in 2+ sports is corroboration only; no pooling of slopes across sports.
- Concentration: report each candidate's gain with its single best season removed.
