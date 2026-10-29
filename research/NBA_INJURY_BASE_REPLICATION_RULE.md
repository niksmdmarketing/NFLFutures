# Original injury-versus-base replay: ID-corrected replication

Registered 29 October 2026, before this replication's outcomes are scored.
No model/site changes or further candidate tests are authorised.

Use the original publication's code, commit a35e92878f45f25e9b18f29d3222754cfb3d205f.
Change only synthetic player-ID normalization: numeric `1234.0` becomes `1234`,
matching player_values. Use freshly hashed cached raw releases, acknowledging
that these are NOT proven to be the exact input bytes used on 10 October.
The original inputs were not archived with immutable hashes.

Replicate its 2013–2026 seasons, 20/40/60/80% checkpoints, 3,000 simulations,
fixed simulator seed 20261009, team-only rating engine and original weight 4,
original undated 14/90-day absence defaults, with versus without availability.
Keep all original simulator settings, including its inaccurate historical
play-in/82-game assumptions and bubble season. Those limitations are deliberate
for this replication, NOT endorsed as a valid current futures evaluation.
No roster/RAPM terms, owner overrides, historical return estimates or market
prices are introduced. Parallel seasons only change runtime.

Primary: equal-season/checkpoint/market binary log loss for title, conference,
playoffs, clipping .002/.998 as the published test. Report each market, season
and checkpoint, matched episode counts, expected-win changes and seed identity.
Resample whole seasons 10,000 times, bootstrap seed 20261029, 95% interval.
Descriptive research success requires positive combined lower bound, no market
worse, and improvement in at least 10/14 seasons. Otherwise no clear gain.
Even a pass cannot promote the live injury layer: the full live model, correct
eras and real dated reports are absent from this experiment.

Audit lineage before interpreting the published result:
`research/nba_avail_futures_test.py` generated
`model/availability_nba_futures.json`, first committed at a35e928. List direct
published references to that file and mark the old neutral conclusion as needing
review. Do not claim a specific original season was affected without the
original input version. Distinguish that unknown from the demonstrated six
zero-join seasons in today's first invalid weight test.

Do not replace the historical result file. Save a new results file, source/input
hashes, and row-level predictions privately. Publish only aggregate findings.
