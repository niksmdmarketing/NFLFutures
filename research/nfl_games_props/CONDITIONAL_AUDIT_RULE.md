# Audit conditional NFL projections — 24 October 2026 Sydney

Written before running this audit. No tuning, replacement, publication, live-model or source-input changes. Save outputs separately and create-only. This audit evaluates conditional production, not automatic availability/starter selection or profitability.

## Chronology and role assumptions

Evaluate 2021–2025, fitting team volume, priors and dispersion on preceding seasons only. Do not apply the frozen-2026 parameters to historical test seasons. The QB starting-role allocation is fitted from first-identifiable-QB-dropback samples in 2020 through year-1, retaining early exits. On each evaluation team-game, select the actual first identifiable QB as the supplied role scenario for ALL models. This hindsight role selection is explicit: it evaluates 'given this QB had the starting-role proxy', not whether we knew the starter pregame. Report excluded unseen players and first-dropback label gaps. Use full held first-role history, plus 2018–2019 samples for fair control history.

Receivers: original strictly lagged candidate list, with all candidate receivers assumed participating for the target budget. Budget correction must use this whole pregame cohort, never only eventual active players. Score on those who actually participate, so availability is conditioned away. Earlier seasons lack dated depth charts: this is a candidate-cohort proxy for the current tool's roster construction, not an exact replay of its 2026 depth-roster filter. Do not reconstruct final rosters.

Prior-game inputs need kickoff plus six hours strictly before kickoff minus one hour. Modern revised files remain a historical-vintage limitation. Raw offensive appearances include zero-stat games; do not select history only from players recording receptions. No injury, market or actual future snap inputs.

## Comparisons

1. Audited candidate: conditional tool equations with prior-only refits, default target budget normalisation and unchanged smoothed catch probability.
2. True current-season per-appearance average, fallback previous season then prior-season position average. For QBs use starting-role-proxy appearances only, NOT low backup averages. All controls receive the same supplied role cohort.
3. Last ten available appearances (starting-role appearances for QB), unweighted, with the same fallback. Give each baseline a fitted negative-binomial full distribution using prior seasons only.
4. Earlier prototype's conditional distribution scores on exact shared game/team/player rows. This is descriptive because the QB workload assumption differs; do not present that contrast as a fair same-role baseline.

## Scores and fixed diagnostics

Whole-distribution conditional RPS (normalisation 60 attempts/20 receptions), log score, randomised PIT, mean error, scoreless frequency, 95th/99th percentile exceedances compared with the model's actual discrete exceedance probabilities. Formula lines = floor(season control mean)+0.5; report aggregate predicted/actual overs and >=80% confident overs. No real prop prices are held and none of these lines are bookmaker quotes.

Report all five seasons, paired season bootstrap lower gains (4000 draws, seed 20261023; few seasons limited), and fixed groups: QBs with >=5 earlier starting-role appearances vs fewer; QBs with <3 earlier starts; receivers with prior season-control mean >=2 vs lower; receivers predicted below one reception; rookie receivers from metadata as a diagnostic only. 'Replacement' cannot be inferred merely from a low career count; true starter-selection performance remains in the separate dated-depth pilot.

Verdict by stat: historical score advantage supported only if it beats both fair controls with positive paired season lower bounds and >=4/5 seasons, and overall PIT bins within 0.07–0.13. Otherwise label mixed/failing, not adopted. Even a screen pass is not a market edge or permission to ignore group/tail problems. Name the largest repeatable weaknesses; do not fit a fix in this same audit.

Tests: target/future outcomes cannot change control means; exactly ten appearances; buffer/cold-start fallback; DNPs do not become zero-stat appearances; budget uses all prior candidates; fold parameters use earlier seasons only. Preserve the built model, outputs, forecasts and earlier evidence byte-for-byte.
