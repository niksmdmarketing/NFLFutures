# NFL "caution" investigation: summary and learnings (20 Oct 2026)

Written for outside review. No model, setting or live output was changed by any step below. v4 is the fixed reference; "v5like" is a research copy of the v5 challenger.

## Question
Earlier work said the NFL model is "too cautious" (favourites given too little chance). I proposed fixing it by reducing rating shrinkage. A review (GPT) objected that the cause had not been identified and asked for diagnosis first: single games, win totals, playoffs with the actual field, and results by stage and season. TypeSafe agreed (99-100%). This is that diagnosis.

## Method (rating weights out of sample; some simulation settings were not)
- Seasons 2013-2025 (13). Every forecast uses only information available at the time; rating weights are fitted walk-forward (season s uses 2010..s-1). Correction (after review): the simulation settings were not chosen walk-forward. The rating scale 0.89 was fitted on 2018-2025 and v4's tau/sigma on 2022-2025 final win totals; v5's tau 4 / sigma 12 and playoff home edge 4 were chosen on a replay of 2013-2025. So the pipeline as a whole has seen these seasons; only the rating weights are strictly out of sample.
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

### 3. Playoffs with the actual field and seeds (diagnostic only; superseded by sections 7 and 9)
First version, only 2020-2025 (the 7-seed format; 12 conference champions), so this is too small to conclude anything. Conference forecasts beat a uniform guess; title forecasts did not. No. 1 seeds won 6 of 12 conferences against 35% predicted by v4 and 43% by v5like (v5's larger playoff home edge moves in the right direction).

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

## Additions after review (20 Oct 2026)
GPT reviewed this summary. Accepted corrections: (1) the replay models are not the exact live models (no QB layers, no pressure term, reconstructed v4 weights correlating 0.66 with the frozen ones), so the findings justify targeted research, not a claim about the live probabilities; (2) see the corrected Method line on out-of-sample; (3) good win totals do not clear the simulation, because the order between teams decides the No. 1 seed and the bye; (4) "pre-season spread" mixes two things, the gaps between teams' expected wins (slope 0.84) and the uncertainty around each team, which must be tested separately; (5) several markets and checkpoints were examined, so the 90% intervals are exploratory.

### 6. Conference market: intercept and favourites (research/nfl_conference_favourites.py)
Teams ranked by their conference-title chance within their conference at each checkpoint; 26 conference champions.

| Stage | Model | Intercept, slope | Top favourite: predicted / actual | 2nd | 3rd | 4th-6th | 7th-16th |
|---|---|---|---|---|---|---|---|
| Week 4 | v4 | 0.99, 1.46 | 6.1 / 9 | 4.0 / 3 | 3.1 / 3 | 6.2 / 7 | 6.7 / 4 |
| Week 8 | v4 | 1.39, 1.74 | 7.1 / 11 | 4.5 / 4 | 3.4 / 4 | 6.3 / 6 | 4.7 / 1 |
| Week 12 | v4 | 0.99, 1.59 | 8.4 / 12 | 5.2 / 6 | 3.6 / 4 | 5.7 / 4 | 3.1 / 0 |
| Week 8 | v5like | 0.99, 1.58 | 8.3 / 8 | 4.9 / 9 | 3.7 / 5 | 5.9 / 4 | 3.2 / 0 |
| Week 12 | v5like | 0.46, 1.31 | 9.9 / 12 | 6.0 / 7 | 3.5 / 4 | 4.7 / 3 | 1.9 / 0 |

The slope above 1 comes from both ends: the leading favourite is under-rated (v4) and the long shots (7th and below in their conference) are over-rated; the middle is about right. v5 fixes much of the long-shot excess but still under-rates the leaders late in the season.

### 7. Playoffs with the actual field and seeds, now 2013-2025 (6-seed format to 2019, 7-seed from 2020; research/nfl_playoff_field_report.py)
| | v4 | v5like |
|---|---|---|
| Intercept, slope (conference winner) | 0.75, 1.59 | 0.31, 1.27 |
| 2013-19 (two byes) slope / 2020-25 (one bye) slope | 2.50 / 1.05 | 2.23 / 0.81 |
| No. 1 seeds: predicted / actual conference titles (26) | 9.5 / 16 | 11.6 / 16 |
| No. 2 seeds | 6.8 / 6 | 7.1 / 6 |
| Seeds 3-7 | 9.7 / 4 | 7.3 / 4 |

With the field and seeds supplied, the conference error remains: No. 1 seeds won 16 of 26 conferences against 9.5 predicted by v4 and 11.6 by v5like. So most of the conference caution arises in the playoff rounds, not in qualification or seeding. It is concentrated in the No. 1 seed: No. 2 seeds also had a bye in 2013-19 and are about right, which argues against a generic bye effect (and the bracket already gives the bye). It is strongest in 2013-19 and absent in 2020-25 (12 champions), so it may not be stable.

### 8. How simulated strength carries into the playoffs (code audit)
pipeline/simulate.py draws each team's season strength once per simulation (rating + Normal(0, tau)) and uses that same draw for regular-season and playoff games; playoff games add only game noise (sigma). Strength persists fully; it is not redrawn or discarded. In the actual-field check above the field is fixed, so the strength draw is not conditioned on having earned the seed.

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
- The playoff-field check now covers 2013-2025 (6-seed format to 2019, 7-seed from 2020); see sections 7 and 9.
- 2,000 simulations per checkpoint; slopes for rare markets are noisy.

## Next (proposed, not run; superseded by the review order below)
Candidate targeted tests, each pre-registered, walk-forward, reported by market, stage and season, against fixed v4:
- (a) v5 pre-season spread: how far last season carries into the pre-season forecast (expected-wins slope 0.84).
- (b) playoff structure: bye value and conference-round home edge.
- (c) late-season persistence of season-long uncertainty (tau fade) for No. 1 seed and conference.
TypeSafe leaned to (a) (61%), with "no change; wait for 2026 live scoring" at 25%, (c) 11%, (b) 3%. Note that (a) does not touch the conference-market caution, which is the clearest finding; (b) and (c) target it directly.

### Revised order (after review; TypeSafe 73% to adopt)
1. Done: actual-field check extended to 2013-19 (section 7) - the error persists after qualification and seeding, concentrated in No. 1 seeds.
2. Done: strength persistence audit (section 8) - full persistence.
3. Next candidate: one targeted change in the playoff rounds, e.g. the conference-round home edge (v5's 4.0 already moves No. 1 seeds from 9.5 to 11.6 of 16), or whether the No. 1 seed's rating is under-stated going into the playoffs. No manual bye bonus.
Separate (next season): v5 pre-season expected-win gaps (slope 0.84), without changing per-team uncertainty.

## Second review round (20 Oct 2026)
GPT's points, accepted: the actual-field result is concentrated in 2013-19 (slopes 2.50 / 2.23) and absent or reversed in 2020-25 (1.05 / 0.81), so it is no reason to sharpen current playoff forecasts; "most of the error is in the playoff rounds" is not established without comparable forecast dates and inputs for qualification and seeding; the v4 -> v5like move (9.5 -> 11.6 No. 1-seed titles) is a whole-model comparison, not a home-edge result.

Forecast date of the actual-field check (confirmed in code): ratings are built from every regular-season game and nothing from the playoffs (research/nfl_futures_diagnosis.py, checkpoint "end": plays with week <= last regular-season week, season_type REG, all regular-season results known). No seed adjustment is added; seeds only set the bracket.

### 9. Individual playoff games, 2013-2025 (research/nfl_playoff_games.py; ratings fixed just before each postseason)
155 playoff games. Predicted margin = rating gap + the model's playoff home edge (Super Bowl neutral); win probability as in the simulation.

| | v4 (edge 1.8) | v5like (edge 4.0) | actual |
|---|---|---|---|
| Home wins, all 155 | 92.0 | 100.2 | 98 |
| Mean home margin | +3.3 | +5.3 | +4.9 |
| Home wins 2013-19 (77) | 45.9 | 50.1 | 48 |
| Home wins 2020-25 (78) | 46.1 | 50.1 | 50 |
| Conference finals, home wins (26) | 16.0 | 17.4 | 20 |
| No. 1 seed games 2013-19: wins (28) | 17.5 | 18.9 | 23 |
| No. 1 seed games 2020-25: wins (25) | 15.9 | 17.0 | 16 |
| No. 1 seed mean margin 2013-19 / 2020-25 | +4.5 / +4.9 | +6.4 / +6.6 | +9.5 / +4.8 |

- No. 1 seeds outperform their ratings only in 2013-19 (23 wins vs 17.5 predicted by v4); in 2020-25 they match (16 vs 15.9). In 2013-19 they won 11 of 14 one-score games (7 points or fewer) against 3 losses; in 2020-25 8 wins and 6 losses. A handful of close games (and New England's run) drive the historical finding. This is not consistent evidence that No. 1 seeds are under-rated.
- Margin slopes in playoff games are below 1 overall (v4 0.80, v5like 0.66) and unstable by era (1.33 vs 0.44): in the playoffs the rating gap is, if anything, less decisive than predicted, not more.
- Home teams: with ratings fixed, home sides beat v4's predicted margin by 1.6 points on average (SE about 1.1), implying a playoff home edge around 3.4 rather than 1.8. This is the only isolated (ratings-fixed) evidence for the home-edge change in v5, and it is weak; v5like's 4.0 slightly over-predicts home wins (100 vs 98).

### Verdict after the second review
No demonstrated reason to raise current conference-favourite probabilities. The conference-market "caution" in the 13-season replay is mostly a 2013-19 effect driven by No. 1 seeds winning close playoff games; 2020-25 is calibrated or slightly over-confident. The only adjustment with some isolated support is a playoff home edge between v4's 1.8 and v5's 4.0; if tested, it should be tested alone with ratings and uncertainty fixed.

Decision (TypeSafe 64%): stop here. No change to current conference probabilities; v5 keeps playoff home edge 4.0 in shadow and the 2026 live scoring judges it. An isolated home-edge test (33%) stays on the list.
