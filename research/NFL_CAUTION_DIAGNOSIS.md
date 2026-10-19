# NFL "caution" investigation: summary and learnings (20 Oct 2026)

Written for outside review. No model, setting or live output was changed by any step below. v4 is the fixed reference; "v5like" is a research copy of the v5 challenger.

## Question
Earlier work said the NFL model is "too cautious" (favourites given too little chance). I proposed fixing it by reducing rating shrinkage. A review (GPT) objected that the cause had not been identified and asked for diagnosis first: single games, win totals, playoffs with the actual field, and results by stage and season. TypeSafe agreed (99-100%). This is that diagnosis.

## Method (all out of sample)
- Seasons 2013-2025 (13). Every forecast uses only information available at the time; rating weights are fitted walk-forward (season s uses 2010..s-1).
- Two models, both without the QB layers (the replay has no weekly QB history):
  - v4wf: v4 components and simulation (rating scale 0.89, season-long uncertainty tau 5, game noise sigma 11.37, home edge 1.8), walk-forward weights.
  - v5like: v5 engine ratings (recency half-life 4 weeks, team-effect shrinkage 60) and v5 simulation (tau 4, sigma 12, playoff home edge 4).
- Checkpoints: pre-season and after weeks 4, 8, 12, 16; 2,000 simulations each.
- Calibration slope = logistic slope of the outcome on the forecast's log-odds (1 = right; above 1 = too cautious; below 1 = over-confident). Intervals are season-cluster bootstrap 90%.
- Code and outputs: research/nfl_caution_diagnosis.py, nfl_caution_same_games.py, nfl_futures_diagnosis.py (+ _report.py, _ci.py); results in the matching .json/.csv files.

## Findings

### 1. Single games: rating gaps are not too small
On identical games (3,407):

| Path | Margin slope (1 = right) | 2022-25 | Win sharpness k |
|---|---|---|---|
| Engine, before any scaling | 0.89 | 0.89 | 0.96 |
| v4 raw ratings | 1.01 | 0.95 | - |
| v4 as simulated (x 0.89) | 1.13 | 1.06 +/- 0.08 | 1.22 |

The often-quoted "1.2" is v4's 0.89 rating scale applied to gaps that were already about right, and it sits mostly in seasons v4's weights were fitted on. Out of sample the single-game caution is small and not clearly different from 1. v5 lands close to 1. My shrinkage hypothesis was wrong: reducing shrinkage would widen gaps that are, if anything, already too wide.

### 2. Win totals: centre and spread are about right
| Stage | Win RMSE (both models) | Slope actual on expected (v4 / v5like) | Spread z-sd, 1 = right (v4 / v5like) | 80% interval cover (v4 / v5like) |
|---|---|---|---|---|
| Pre-season | 2.9 | 0.94 / 0.84 | 0.96 / 1.09 | 87% / 82% |
| Week 4 | 2.3 | 1.09 / 1.09 | 0.96 / 1.06 | 88% / 85% |
| Week 8 | 1.8 | 1.05 / 1.05 | 0.96 / 1.04 | 89% / 88% |
| Week 12 | 1.2 | 1.03 / 1.03 | 0.95 / 1.00 | 93% / 91% |

(Integer win totals inflate interval coverage above 80%; the z-sd is the cleaner measure.) Win-total uncertainty is not where the caution is: v4 is slightly too wide, v5like about right. The two models predict wins equally well at every stage. One real issue: v5like's pre-season expected wins are too spread (slope 0.84).

### 3. Playoffs with the actual field and seeds (diagnostic only)
Only 2020-2025 (the 7-seed format; 12 conference champions), so this is too small to conclude anything. Conference forecasts beat a uniform guess; title forecasts did not. No. 1 seeds won 6 of 12 conferences against 35% predicted by v4 and 43% by v5like (v5's larger playoff home edge moves in the right direction).

### 4. Futures by stage: the caution is market-specific
Calibration slopes with 90% intervals:

| Market | v4 wk4 | v4 wk8 | v4 wk12 | v5like wk4 | v5like wk8 | v5like wk12 |
|---|---|---|---|---|---|---|
| Conference winner | 1.46 (1.02-2.08) | 1.74 (1.27-2.39) | 1.59 (1.25-2.15) | 1.35 (0.94-1.82) | 1.58 (1.20-2.18) | 1.31 (1.03-1.68) |
| No. 1 seed | 1.05 | 1.26 | 1.43 (1.14-2.09) | 1.01 | 1.23 | 1.41 (1.11-2.08) |
| Super Bowl | 1.17 | 1.31 | 1.19 | 1.08 | 1.26 | 1.00 |
| Make playoffs | 1.28 (1.06-1.57) | 1.18 | 1.09 | 1.13 | 1.09 | 1.05 |
| Division | 1.29 | 1.26 | 0.97 | 1.17 | 1.14 | 0.91 |

Make-playoffs is over-confident at week 16 (0.76). The consistent, statistically clear caution is in the conference-winner market from week 4 on, and in the No. 1 seed late in the season. Win totals and single games are fine. So the error sits between "who is good" and "who wins the conference": seeding/bye, the playoff rounds, and how persistent the simulation's season-long uncertainty is. v5 reduces it but does not remove it.

### 5. Seasons and 2025
v5like beats v4 in the conference market in 11 of 13 seasons. 2025 is its worst season, and the loss is concentrated in the division and make-playoffs markets from pre-season to week 8 (pre-season -0.033 and -0.027 log loss). 2025 was a high-surprise season: pre-season win RMSE 3.4 against a typical 2.8 (New England 6.9 expected -> 14 wins, Seattle 8.5 -> 14, Jacksonville 7.8 -> 13, Arizona 9.0 -> 3). v5's narrower spread (pre-season win sd 2.76 vs 3.10) and more extreme pre-season forecasts were punished. 2024 was similarly surprising (RMSE 3.5) but v5 did not lose there, so "narrower is worse in surprise years" is a hypothesis, not a finding.

## Learnings
1. "Too cautious" was not one problem. Single games and win totals are about right out of sample; the caution is in the conference winner (and late No. 1 seed).
2. The headline "1.2" figure was a v4 artifact (the 0.89 scale), mostly in-sample. Out-of-sample checks must be on identical games and identical quantities before comparing numbers.
3. My first explanation (shrinkage) was wrong. Diagnosing before fixing saved a test that would have pushed in the wrong direction.
4. v5's real gains are in the conference market; its pre-season spread is a weakness and is the likely reason 2025 went badly.
5. The evidence base is thin where it matters most: 26 conference champions in 13 seasons, 12 in the playoff-field check. Several intervals are wide.

## Limitations
- No QB layers in either replay model (live v4 and v5 have them).
- v5like is a close research copy, not the exact live v5 (no QB-availability prior, no pressure term).
- v4's walk-forward weights are a reconstruction (correlation 0.66 with the frozen weights; same accuracy).
- The playoff-field check covers 2020-2025 only; 2013-2019 used 6 seeds and were skipped.
- 2,000 simulations per checkpoint; slopes for rare markets are noisy.

## Next (proposed, not run)
Candidate targeted tests, each pre-registered, walk-forward, reported by market, stage and season, against fixed v4:
- (a) v5 pre-season spread: how far last season carries into the pre-season forecast (expected-wins slope 0.84).
- (b) playoff structure: bye value and conference-round home edge.
- (c) late-season persistence of season-long uncertainty (tau fade) for No. 1 seed and conference.
TypeSafe leaned to (a) (61%), with "no change; wait for 2026 live scoring" at 25%, (c) 11%, (b) 3%. Note that (a) does not touch the conference-market caution, which is the clearest finding; (b) and (c) target it directly.
