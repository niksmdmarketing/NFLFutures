# NFL season simulator: logic check (26 Oct 2026, Sydney)

Asked by the user before any recalibration of the NFL in-season futures model. TypeSafe chose to check the logic first and only then consider a recalibration layer (71%). The code is pipeline/simulate.py (frozen v4 simulator).

## Findings
1. **Playoff format in the historical replays (research bug, live unaffected).**
   - research/nfl_futures_diagnosis.py simulated 2013-2019 with the 7-seed format (one bye). Those seasons had 6 seeds and two byes.
   - Simulated make-playoffs probabilities summed to 14 per season against 12 actual. Conference and Super Bowl paths used the wrong bye structure.
   - **Re-measured by era from the existing rows (v4, logistic calibration slope; above 1 = too cautious; season-bootstrap 90%):**

     | Market | Era | Pre-season | Wk 4 | Wk 8 | Wk 12 | Wk 16 |
     |---|---|---|---|---|---|---|
     | Make playoffs | 2013-19 (wrong format) | 1.18 | 1.30 | 1.43 | 1.33 | **0.59** (0.52-0.72) |
     | Make playoffs | 2020-25 (right format) | 0.67 (0.28-1.03) | 1.28 (0.94-1.76) | 1.03 | 0.93 | 1.12 |
     | Division | 2013-19 | 1.33 | 1.36 | 1.75 | 1.36 | 1.62 |
     | Division | 2020-25 | 0.72 (0.12-1.25) | 1.22 (0.68-1.95) | 0.95 | 0.76 (0.62-0.99) | 1.50 |

   - The week-16 make-playoffs over-confidence is entirely a 2013-19 artefact of the extra simulated playoff spot. The conference-market caution found earlier was also concentrated in 2013-19, where the bye structure was simulated wrongly.
   - research/replay_nfl.py and pipeline/nfl_backtest.py call the same simulator for pre-2020 seasons. The evidence they produced for those seasons (including v5 tuning and adoption evidence) carries the same caveat.
   - The live 2026 forecasts use the correct 7-seed format.
2. **Tiebreakers.**
   - With every result known, the simulator reproduced every actual seed and division winner in 2002-2025 (data/nfl_standings.csv), except 2015 AFC seeds 1-2.
   - That season DEN, NE and CIN all finished 12-4. DEN beat both NE and CIN, who didn't play each other, so the NFL head-to-head sweep gives DEN the No. 1 seed.
   - The code applied the 3+-club sweep only when every pair had played each other. With the corrected sweep (`sweep_fix=True`) and the correct format, all 24 seasons reproduce exactly.
3. **Neutral-site games.** The regular-season home edge (1.8) was applied to neutral-site games (3-9 a season; 9 in 2026). Effect on a 2025 week-8 test: at most 0.7 percentage points on any market.
4. **Team uncertainty** (tau 5.0) is constant across the season. Not changed. The week-by-week calibration in the correct format (table above) shows no clear late-season problem.

## Decisions (TypeSafe)
- **Neutral-site home edge: fixed live** as a bug fix (54%; shadow only 35%). This is a dated exception to the 2026 freeze. A simulation with no neutral games is bit-for-bit identical to before.
- **3-club sweep: shadow/research option only** (`sweep_fix`, default off; 54% shadow only, 35% fix live). Live v4 keeps the frozen behaviour through 2026.
- **Playoff format:** `n_seeds` option (default 7). The replay now passes 6 for seasons before 2020.
- **Next (91%):** rerun the 13-season calibration replay with the correct format, then decide whether any recalibration is needed. Rows: research/nfl_futures_diagnosis_rows_format_fix.csv.

Tests: tests/test_simulate_logic.py (format counts, 7-seed default, no home edge at neutral sites).
