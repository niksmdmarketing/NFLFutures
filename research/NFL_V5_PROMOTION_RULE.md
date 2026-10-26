# NFL futures: v4-core vs v5-core, and a conditional 2027 decision. Rule fixed before any code or results (27 Oct 2026, Sydney)

Status: **final.** GPT reviewed the draft; all its revisions were accepted (TypeSafe 93%). Nothing had been run when this was committed. A pass permits a documented 2027 promotion decision for the configuration the evidence supports. It is not automatic.

## Why
- v5 has run as an archived live shadow since October 2026.
- Its adoption evidence (+0.0032 log loss, 11 of 13 seasons) came from replays that simulated 2013-2019 with the wrong playoff format, so it is redone here.
- In the corrected replay, v5like is closer to calibrated in season (e.g. division at week 4: slope 1.18 vs 1.31).

## What is tested: the cores
Both arms are built as in research/nfl_futures_diagnosis.py (code as of commit ea878fc4 plus the test script committed with this rule).

| | v4-core (v4wf) | v5-core (v5like) |
|---|---|---|
| Ratings | v4 components (ratings.base_ratings), coefficients walk-forward per season (model/replay/nfl_wf_coef.json) | engine ratings (nfl_engine.team_features, recency half-life 4, team-effect shrinkage 60), ridge weights refitted each season on seasons before Y (eng_weights) |
| Scale | 0.89 | 0.89 |
| tau / sigma | 5.0 / 11.37 | 4.0 / 12.0 |
| Home edge, regular season | 1.8 | 1.8 |
| Home edge, playoffs | 1.8 | 4.0 |

Both arms share:
- the correct playoff format (6 seeds to 2019, 7 from 2020);
- no home edge at neutral sites;
- the sweep option off;
- simulate.simulate.

Not included in either arm: the QB layer, the pressure layer and v5's QB-prior correction.

**Walk-forward:** all regression weights are refitted on seasons before Y. The fixed hyperparameters (recency, shrinkage, tau, sigma, scale, home edges, rating constants) were chosen on overlapping historical seasons. Walk-forward fitting does not remove that exposure.

**Production configurations (not validated here):**
- **Live v4:** v4 ratings, plus the QB layer (expected starter from depth chart and injury report; 0.5 × value gap for the whole remaining season), plus the pressure layer.
- **Live v5:** engine ratings, plus the same QB layer and pressure layer, plus the QB-prior correction.
- The simpler news-based QB-absence input agreed on 26 Oct is not yet implemented in either.

## Historical test
- Seasons 2013-2025. Checkpoints: pre-season (0) and after weeks 4, 9, 13 and 16 (results after week w masked).
- **Monte Carlo:** two seed sets (A: seed 1000·Y + w; B: seed 7000·Y + w), 5,000 simulations each, the same seed for both arms. Both arms call the same simulator with the same array shapes, so the underlying draws are paired by construction; only tau, sigma and the playoff home edge scale them differently.
  - Probabilities are averaged over A and B (10,000 simulations), then clipped to [0.001, 0.999].
  - Every gate is also computed on A and on B separately. If A and B disagree on any gate, the result is inconclusive.
- **Primary score:** mean team-level binary log loss.
  - Cells: division winner and make-playoffs after weeks 4, 9 and 13 (six cells).
  - Per season the six cells are averaged equally; seasons averaged equally.
  - Gain = v4 loss - v5 loss.
- **Secondary cells**, mean team-level binary log loss, fixed now:
  - division and make-playoffs at pre-season and week 16;
  - No. 1 seed, conference winner and Super Bowl at pre-season and weeks 4, 9, 13 and 16.
- **Diagnostic only:** division categorical log loss (-log probability of the actual winner), reported separately and not interchangeable in scale.
- **Bootstrap:** whole paired seasons (all teams, markets and checkpoints together), 10,000 draws, seed 20261026; one-sided 90% lower bound.
- **Also reported:** leave-one-season-out primary gains (including without 2025; sensitivity only), and calibration slopes and intercepts per primary cell.
- The existing 3,000-simulation corrected rows are used only to reconcile (same direction), never as an alternative dataset.

## Historical gates (all must hold)
1. Primary gain: one-sided 90% lower bound > 0, and positive in at least 8 of 13 seasons.
2. Positive gain separately for division (three cells) and make-playoffs (three cells).
3. Positive primary gain in 2020-25 (an exposed subgroup).
4. No secondary cell worse than v4 by more than 0.003 mean binary log loss.
5. Seed sets A and B agree on gates 1-4.

## Forward check (2026)
- Both models' archived live forecasts (forecast-archive), using the first archive file whose timestamp falls after the last game of week 9, and of week 13, of 2026.
- Score division and make-playoffs (team-level binary log loss) once the regular season ends.
- Four cells, equally weighted; each market also reported.
- **Also recorded:** archive completeness, configuration versions, and any QB or news treatment differences between the models.
- **Veto:** if v5's four-cell loss exceeds v4's by more than 0.01, there is no promotion. Passing the veto is not evidence of equivalence or improvement, and does not validate the layers omitted from the replay.
- Any material model change after this rule is committed is disclosed and does not silently inherit this forward test.

## Decision
- **Historical pass and forward veto passed:** a documented 2027 decision may promote the configuration the evidence supports.
  - **v5-core:** supported.
  - **v5's live layers:** only if separately validated. Otherwise the full live v5 continues as a shadow, and a v5-core display version can be considered.
- **Historical fail or inconclusive:** v4 stays displayed; v5 stays a shadow. No retuning and rerunning under this rule.
- Promotion concerns forecast quality only. Profitable betting with Australian bookmakers still needs separate evidence with real prices, fees and settlement rules.

## Disclosed exposure
- v5's hyperparameters were selected on replays covering 2013-2025, partly with the format bug.
- The corrected v5like calibration slopes (weeks 0/4/8/12/16) were inspected this week; no log-loss comparison had been computed.
