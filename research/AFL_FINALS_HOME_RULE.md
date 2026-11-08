# AFL finals home edge: held-out check. Rule, version 1

Written 8 Nov 2026 (Sydney), before the result. Amendments below, dated; nothing above them is edited.

## The defect under test
pipeline/afl_site.py simulates the finals with `play(a, b)` giving the FIRST-named side +3.0 points, while the home-and-away season uses `A.HGA = 7.0`. Two issues: (1) the finals edge 3.0 is a hard-coded constant never validated against finals results; (2) the grand final is played between the two preliminary-final winners (`play(p1w, p2w)`), a neutral-style game at the MCG, yet the first-named side (the qualifying-final side) gets +3.0, so the sim carries an unexplained asymmetry.

## Test (no prices; results only)
- Data: AFL finals 2012-2025 from the same afltables frame the live model uses (pipeline/afl.py team games), listed home/away as recorded.
- Ratings: A.srs on the same season's home-and-away games only (no finals games), so no finals result enters its own prediction. Predicted finals margin for the listed home side = r_home - r_away. Residual = actual margin - prediction; its mean over games is the finals home edge in points.
- Groups: (a) non-grand-final finals (QF, EF, SF, PF) with a listed home side; (b) grand finals, reported separately (expected edge 0 for the first-named side).
- Split: discovery finals 2012-2019, evaluation finals 2020-2025 (2020 was played under COVID hub conditions; reported with and without 2020 as a sensitivity, no choice made after seeing it).
- Deciding number: the evaluation (a) mean residual with a 90% bootstrap interval over games (4,000 draws, seed 1), compared with 3.0 (current) and 7.0 (regular season). About 8-9 non-GF finals a season, so about 50 games: stated as limited.
- Decision: replace 3.0 with the evaluation estimate only if (i) the discovery estimate is within the evaluation interval and (ii) the evaluation interval excludes 3.0. If the interval contains 3.0, nothing changes (unvalidated, still 3.0). The grand-final asymmetry is a correctness question, not an outcome one: set the grand-final edge to 0 only if group (b) evaluation interval contains 0, and report either way. Any change carries a dated version string and the no-harm measurement at N=2000 on regular-season outputs (they must not move) before it goes live.
- This is an accuracy fix (profit effect about 0): the model moves toward the finals home edge, which the market already prices.

## Result (8 Nov 2026, `research/afl_finals_home.py`; applied exactly as the rule above says)
Finals 2012-2025, 137 home-listed games (QF/SF/EF/PF 122 plus 2 wildcard finals, GF 15). Mean residual of the listed home side, points, 90% interval:
- Non-grand-final, discovery 2012-19: +5.94 [-1.06, +12.81] (n 64). Evaluation 2020-25: +3.21 [-3.38, +10.02] (n 58); excluding 2020: +2.35 [-4.94, +9.68] (n 50). All: +4.64 [-0.09, +9.47] (n 122).
- Grand final: discovery -16.23 [-40.68, +12.33] (n 8); evaluation +6.90 [-25.42, +39.76] (n 7); all -5.44 [-26.14, +16.34] (n 15).
Decisions by the rule: (1) the evaluation non-GF interval contains 3.0 (and 7.0), so the finals edge stays 3.0, unvalidated, evidence too thin to separate 3 from 7 (about 50 games). (2) the grand-final interval contains 0, so the grand-final edge is set to 0 (`play(p1w, p2w, 0.0)` in `pipeline/afl_site.py`). The interval is very wide (+/- 30 points), so the data barely supports this; the change rests on the neutral-venue logic and the pre-registered rule, and corrects an asymmetry that favoured the qualifying-final side with no basis.
No-harm check, same seed old vs new `simulate` on a synthetic 18-team, 150-game input (4,000 seasons): p1, p4, p8, p10 (ladder) max abs diff 0.0; preliminary-final and grand-final-appearance chances (pf, gf) 0.0; flag (premiership) max abs diff 0.009. Only premiership chances move, and by under 1 point in this example. Accuracy fix, profit effect about 0 (the market prices the finals). Version string: AFL grand final neutral 20261108.
