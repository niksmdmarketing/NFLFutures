# NBA props: one smooth, role-aware per-minute rate adjustment. Rule written BEFORE any code or result (22 Oct 2026)

Agreed with GPT and the user after the bench diagnostic (research/NBA_BENCH_DIAG.md). For fringe players, per-minute production is forecast slightly too high for points and assists and slightly too low for rebounds; faster minutes memory cannot address this. This tests one adjustment to the per-minute rates only.

## Fixed parts
- **Minutes:** M2b, unchanged. So the test isolates the rates.
- **Rates:** the frozen version for each stat, unchanged in form: rebounds P+O, assists P+T, points P+T. These are the shrunk per-minute rate with the stat's adjustment, as in research/nba_minutes_m2b_test.py.
- **Spread:** each stat keeps its own dispersion, unchanged:
  - rebounds r_O and assists r_T (research/nba_props_simple_results.json);
  - points the D form r(mu) = exp(a + b log mu) with that season's a and b (research/nba_points_dispersion_results.json). Its a and b are not refitted.
- **Baseline:** these versions with M2b minutes (rebounds and assists v3; points pts-D1/M2b).

## Candidate (one form, each stat separately)
rate_R = rate x exp(theta_1 x (1 - start10) + theta_2 x (1 - app10))
- start10 is the share of the player's last 10 team games that he started. app10 is the share of the last 10 team games in which he appeared. Both are known before the game, and both are 0 to 1.
- An established starter who always appears (start10 = app10 = 1) gets no change.
- Projected minutes are deliberately not used. Role (starting, regular appearance) and expected minutes are related but not interchangeable, and minutes are the M2b model's job.
- **Smooth:** no tiers, bins or thresholds.
- **Missing values:** a missing start10 or app10 (no history) is treated as 0.5.
- **Strong restraint towards no adjustment.** Theta is fitted by penalised maximum likelihood with a normal prior of mean 0 and sd 0.05 on each theta, so a full-bench, irregular player is moved by about 5-10% only if the data insist. The multiplier is also capped to [0.85, 1.15].
- **Fitting:** on appearances of seasons 2017..s-1 only (walk-forward), given actual minutes, with that stat's negative binomial and its fixed dispersion. The rate inputs are exactly as in the baseline.
- No other form, feature, prior width or cap is tried. Every stat's result is reported, pass or fail.

## Data and scores
- Corrected tables (research/NBA_MINUTES_M2B_RULE.md correction; exported 22 Oct with manifest). Test seasons 2022-2026, 1-hour forecasts, the same candidate player-games as the M2b test.
- Scores as there: unconditional and conditional RPS, randomised PIT deciles given appearing, illustrative half-point over thresholds (floor of season-to-date average + 0.5), week-block bootstrap (2,000 draws). The team-season block is reported, not gated.
- **Fixed pre-game groups** (from baseline information only):
  - bench: start10 < 0.5;
  - risk: stage-one P(minutes < 15 | appear) >= 0.2;
  - established: stage-one expected minutes given appearing >= 25.

## Gates (each stat separately; all must hold for that stat)
1. **Better overall:**
   - unconditional RPS lower, with a one-sided 97.5% week-block lower bound of the gain above zero;
   - better in at least 4 of 5 seasons;
   - conditional RPS (given appearing) lower.
2. **Calibration:** the candidate's PIT deciles given appearing all within 0.07-0.13.
3. **Fixed-group bias improved:**
   - on the bench group and on the risk group, |mean forecast - actual mean| given appearing is smaller than the baseline's;
   - on the risk group, the absolute over gap (mean predicted P(over) - observed over frequency) is smaller.
4. **No meaningful harm to established players:**
   - on the established group, unconditional RPS no more than 0.25% (relative) worse;
   - |mean forecast - actual mean| no more than 0.02 worse.

## Decision
- **These seasons are development evidence.** A stat that passes becomes a frozen forward challenger for that stat only, with its own identifier and parameter file, archived beside the existing versions, by a separate decision. It is not adopted, and no site or live change follows.
- **A stat that fails** is recorded and dropped.
- No other adjustment or tuning follows from the results.
- No minutes change is part of this test.
