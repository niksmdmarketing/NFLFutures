# Availability baseline 4→8 — corrected result, 29 October 2026

**Does not pass; retain 4.** No live/model/site change or merge.
Rule committed first at ad53037. Original team-weight deployment had no
preregistered adoption gate; new explicit gates were used for this test.

Rebuilt synthetic availability at four cutoffs in 13 seasons, two fixed seeds
and 2,000 simulations per seed. Primary excludes 2020 bubble and shortened
2021 (12 seasons); 2021 is a sensitivity. Era-correct formats/season length.
Team fit stays 8; only the availability baseline weight changes 4→8.
6,240 paired team/variant/seed/checkpoint rows; matched episodes in every season.

| Primary log-loss gain (4 minus 8, positive is better) | Result |
| --- | ---: |
| Combined, equal markets/seasons/checkpoints | +0.0003854 |
| 95% whole-season bootstrap interval | −0.0000820 to +0.0008350 |
| Seasons better | 9 of 12 |
| Conference | +0.0013973 |
| Playoffs | −0.0000718 |
| Title | −0.0001694 |

Both simulation seeds have positive combined gain. Including 2021 gives
+0.0003905. Fails the positive-interval and no-market-worse gates. The aggregate
results file also reports Brier changes, cutoff scores and descriptive calibration.
No additional seeds, variants, thresholds or tuning were tried after this result.

## Implementation defect discovered and corrected

The first execution had zero matched injuries in six seasons because the
synthetic report kept float-form IDs (`1234.0`) while player_values normalized
them to `1234`. Its apparently favourable interval is invalid. Retained that
run privately; corrected the shared synthetic-report function, added an ID
regression test and reran every season with unchanged gates/settings/seeds.
The correction was committed as 504e9eb before the rerun. It affects research
matching, not production nba_avail.py. The old published synthetic replay uses
that same code and warrants rechecking against its actual historical input
versions; today's defect does not prove which old snapshots were affected.

## Limits and next decision

This remains a synthetic, undated, team-engine comparison. It omits the live
roster/RAPM mix and cannot validate the complete dated-injury futures pipeline.
Numerically aligning weights does not make the baseline account for all those
layers. Known parameter choices used these seasons, so call this development
evidence rather than a pristine independent test.

The separate review of the already-deployed team weight 8 is preregistered in
the rule but not run here. The dated forward-test collection gap is separately
documented in NBA_ARCHIVE_COVERAGE_FINDINGS.md.

Private raw inputs, first invalid run, corrected rows, hashes and integrity
checks: outputs/nba_availability_weight_20261029{,_corrected}/ in the shared
workspace. Public results: research/nba_availability_weight_results.json.

Tests: 94 total, 91 pass, 2 skipped, same 1 pre-existing Windows SQLite cleanup
error reproduced on the unchanged baseline. ID matching and coverage tests pass.
