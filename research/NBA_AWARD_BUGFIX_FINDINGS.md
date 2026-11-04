# NBA award corrections and paired replay — 4 November 2026

## Applied correction, separate from evaluation

The two corrections are on public main in merge
`3c264b45bf2dd3af121b9f4d199bdbdf28182d50`, containing only correction commit
`0c6862f` and its regression tests:
- filter the box-score loader by the canonical 30 NBA teams, not 40 games;
- exempt ROY and Sixth Man (`6MOY`) from the 65-game gate.

No rate, shrinkage, temperature, uncertainty, team rating, owner override or
injury-layer parameter changed. Award Value remains subject to its existing
20-team-game restriction and other validation guards. No extra site refresh or
private build was dispatched for these code changes; normal updates pick them up.

Official eligibility reference:
https://cms.nba.com/wp-content/uploads/sites/4/2024/11/2024-25-CBA-101.pdf
MVP/DPOY still use the existing approximate qualifying-minutes count; these two
fixes are not a complete CBA eligibility rewrite.

## Did the original replay contain the bugs?

Yes. Original forward-simulator commit `f22e66f` contained both the 40-game loader
filter and the global 65-game gate. `nba_awards_replay.py` imports that simulator.
Consequently its ROY/Sixth Man forecasts in the 2024-onward era used the wrong
eligibility rule. The 40-game error is masked by replaying completed-season files
before applying forecast cutoffs, whereas a live early-season file loses NBA teams.
The dedicated first-three-games regression fails on the old code and passes now.

## Paired 2010–2026 replay

Both versions use the same 24 frozen/hashes-checked 2003–2026 input files,
300 simulations, original per-call seeds, candidate pools and leave-one-season-out
training. Each version produced 1,630 rows across 17 seasons. Original site CSV
is preserved. Corrected winner/favourite aggregate rows are saved separately as
`research/nba_awards_replay_corrected_20261104.csv`; candidate-level records and raw
ESPN inputs remain private. This is retrospective development evidence, not a new
chronological holdout or a profitability test.

| In-season metric, all 17 seasons | Before | Corrected |
| --- | ---: | ---: |
| ROY winner log loss (lower better) | 0.9500 | 0.9694 |
| Sixth Man winner log loss | 1.6411 | 1.6722 |
| ROY field Brier score (lower better) | 0.4519 | 0.4600 |
| Sixth Man field Brier score | 0.6609 | 0.6658 |

The correction does **not** improve these historical scores. The effect is confined
to ROY/Sixth Man in 2024–2026; MVP and DPOY are unchanged. Equal-season log-loss
gain is −0.01983 for ROY and −0.03177 for Sixth Man across all seasons. No alternative
settings were tried in response. Incorrect eligibility is not restored just because
it accidentally helped past scores.

### Calibration, especially the affected three seasons

| Favourite diagnostic, 2024–2026 | Before | Corrected |
| --- | ---: | ---: |
| ROY mean favourite chance | 54.1% | 54.0% |
| ROY favourite actually won | 42.4% | 27.3% |
| Sixth Man mean favourite chance | 36.7% | 32.5% |
| Sixth Man favourite actually won | 27.3% | 24.2% |

ROY favourite overconfidence gets worse. Sixth Man's gap narrows slightly (about
9.4 to 8.2 percentage points), but its log loss and field Brier get worse, so it is
not an overall calibration improvement. Favourites can change between versions;
these are each version's own favourites, not one fixed event. The affected sample
contains only **three seasons**, with 33 correlated in-season checkpoints per award.
Do not treat those checkpoints as 33 independent completed award races.

Probability mass sums to one in all in-season replay races for both versions.
Reliability bins on paired candidate unions are descriptive and include the
existing preseason forecasts; primary scores above exclude preseason.

The fresh unchanged replay does not exactly reproduce the older published CSV
(maximum checkpoint NLL difference 0.6364). Source/data versions have changed since
that publication. Therefore the table compares a freshly regenerated baseline and
fix using identical current frozen inputs; it does not attribute every difference
from the old published file to these two bugs. The old file is not silently replaced.

## Validation

Two regression tests fail on unchanged code and pass on the fix; the MVP/DPOY and
pre-2024 behavior test also passes. The full public Linux suite passed:
https://github.com/niksmdmarketing/NFLFutures/actions/runs/41819127999

Locally the broader Windows run retains one existing SQLite cleanup failure,
reproduced on unchanged main as well. It is unrelated to awards; missing local
parquet dependencies were installed only in a workspace test directory before
the comparison. No production requirements were changed.

No tuning or live team-futures/availability adoption follows from these results.
