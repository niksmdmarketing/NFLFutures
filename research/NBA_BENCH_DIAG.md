# NBA bench/fringe diagnostic (22 Oct 2026). Diagnostic only; no model change

Script and reading rule: research/nba_bench_diag.py (committed before running, 2972347). Results: research/nba_bench_diag.json.
Development seasons 2022-2026, walk-forward fits, given appearing. Fixed pre-game groups: bench (start10 < 0.5), risk (stage-one P(minutes < 15) >= 0.2), established (stage-one expected minutes >= 25).
This bench group is broader than GPT's bench-role test group, so their figures are not directly comparable.

## Minutes (M2b)
- Bench: forecast mean 0.16-0.35 minutes too high each season. Share of actual minutes below the forecast median 0.521-0.528 (ideal 0.50); below q75 0.758-0.773 (0.75); below q90 0.893-0.906 (0.90). P(>= 20) over-forecast by 1.7-2.8 points; P(>= 30) about right.
- Risk group: the same pattern. Established players: close to calibrated.
- Verdict under the written rule: no consistent pattern. A small upward placement in the middle of the distribution; the upper tail is calibrated. Neither a clean shift nor too much spread.
- M2 shows the same pattern, larger (median share 0.58-0.60), as expected from the known truncation bias.

## Per-minute part (rate x actual minutes vs actual)
Actual minutes are hindsight and depend on fouls, blowouts and performance, so this narrows possibilities rather than proving a cause.
- Points: over per minute for bench and risk groups in all five seasons (risk +2.5% to +4.0%; larger than the minutes part).
- Assists: over per minute for bench (+0.9% to +1.8%) and risk (+0.7% to +3.3%) in all five seasons.
- Rebounds: under per minute for the risk group (0% to -3.2%), which partly offsets the minutes over-forecast.
- Established players: no consistent per-minute bias.

## Reading
- The remaining fringe over-forecast is part minutes (small, mid-distribution) and part per-minute production (points and assists too high, rebounds slightly low).
- Per-minute rates are shrunk toward position-group rates. A plausible mechanism is that the shrinkage target is set by rotation players, which suits fringe players poorly. This is a hypothesis.
- Decision (TypeSafe 65%, in line with GPT's advice): no change now; record and let the forward test decide.
- If a change is ever tested, the candidate is one role-based shrinkage target for per-minute rates (position group x projected-minutes tier), under its own rule (TypeSafe 30%). A minutes change is not supported (5%).

## Comparison with GPT's faster-minutes-memory candidate (22 Oct 2026)
GPT's local test (two-appearance half-life for the normal-night mean input; rule written before results; failed one gate, the bench under-15 check) compared on its own fixed groups from its paired scores, appearing players, M2b vs candidate:
- Bench mean over-forecast falls in all five seasons (2022 0.27 to 0.16; 2023 0.22 to 0.17; 2024 0.48 to 0.44; 2025 0.18 to 0.13; 2026 0.28 to 0.21 minutes). P(>= 20) over-forecast falls in all five seasons (by 0.1 to 0.6 points). The risk group follows the same direction, but less.
- The share below the forecast median barely moves (mixed by season) and the upper tail is unchanged. So it removes roughly a fifth to a third of the mean bias but not the mid-distribution placement.
- It cannot address the per-minute part (points and assists high, rebounds low for fringe players): stat rates are unchanged by construction, so its prop gains come through minutes only.
- Established players: P(>= 30) under-forecast grows slightly in four of five seasons (about 0.1 to 0.6 points).
- Reading: faster memory and a per-minute role adjustment target different parts of the fringe error and are not substitutes. Neither is adopted; the frozen M2/M2b forward test continues.
