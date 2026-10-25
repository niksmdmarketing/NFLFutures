# Dated QB depth and new-player coverage — 24 October 2026 Sydney

Written before fitting/scoring this extension. Research only; no publication, live-model changes or new schedules. Preserve all prior outputs.

## What can honestly be tested

The held local depth file has dated snapshots beginning August 2025. Earlier weekly charts have no one-hour publication evidence. Therefore evaluate only 2025 regular-season weeks 5–18; weeks 1–4 are a pre-specified calibration warm-up. This is a one-season revised-data experiment, not an untouched holdout or evidence across 13 seasons. Do not silently apply today's rankings to old games. Source update timestamps are not independently archived retrieval times.

For each team/game choose the latest source snapshot strictly before kickoff minus one hour, at most 72 hours old. Use QB rows with GSIS IDs, or a unique ESPN-to-GSIS ID crosswalk; no names-only matches. Equal rank-one ties mean ambiguous order, never confirmed starter. Depth order is expectation, not confirmation.

## Candidate coverage and labels

Both versions receive the same expanded cohort: existing historical candidates plus dated snapshot QBs, never candidates selected from the target box. New QBs get lagged career/current-prior-season history if available, otherwise explicit neutral fallback; primary-role workload is pooled, not their tiny backup workload. Target boxes and complete mapped snap files supply outcomes only. Missing rows mean DNP only when the snap file meets existing completeness/identity checks, otherwise unknown. Report coverage on all team-games, including those with no candidates, plus coverage of actual primary passers as an outcome diagnostic.

## One targeted adjustment

Fit the existing QB primary/relief model and injury-aware involvement model on 2020–2024 only. Set 2025 injury statuses unknown: its local injury file has no timestamps. Both versions use identical involvement probabilities, conditional primary/relief distributions and team volume (prior-2018–2024 team volume fit). No new QB ability or game-volume adjustment.

Baseline: frozen prior role probability. Challenger: sigmoid(logit(baseline)+beta*depth_signal), signal +1 for unique rank one, -1 for ranks 2+, zero if missing/stale/ambiguous. Fit one beta in [0,4] with N(0,0.5²) penalty, using only earlier 2025 involved QB outcomes available before each forecast cutoff. Need at least four earlier distinct weeks before scoring; do not batch same-week games using future results. No alternate forms or coefficient search after results.

Primary: conditional-on-involvement count RPS on identical candidates. Secondary: DNP-zero RPS, PIT, fixed-formula-line overs, and cases that became the actual primary after not being the previous primary (outcome diagnostic only). Report legacy and added-candidate subgroups, per week, and coefficients. With one season, no adoption or season-bootstrap significance claim; a candidate is promising only if overall conditional RPS improves, improves in >=8 evaluated weeks, overall PIT deciles within 0.07–0.13, and no old/new subgroup loses >2%. Otherwise stop and retain baseline. Starter-change results must be reported even if overall improves.

## Current source adapter

Use the previously captured 2026 depth and official report bytes to demonstrate identity-complete coverage. Preserve update, observation and forecast-cutoff times independently. Report snapshots' ages, don't call the output independently forward-archived. An explicit dated confirmed-starter record may override depth order only if game/team/player match, source URL and version observation exist before cutoff, and it is not contradicted by an eligible Out report; otherwise retain unresolved conflict. No automatic promotion from 'expected to play' to 'starting'. Do not pretend historical confirmed-starter news exists where it does not.

Tests: future/at-cutoff/stale/ambiguous snapshots; exact ID mapping; new fallback independent of target results; confirmed-starter provenance/conflict checks; PMF validity and unchanged team volume. Freeze hashes and paired output locally; nothing reaches site or live model.
