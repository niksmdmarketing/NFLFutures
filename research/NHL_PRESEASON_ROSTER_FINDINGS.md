# NHL preseason roster component: findings

5 November 2026. Rule aee80a1 and implementation 0cd8f65 were committed and published before the candidate replay. Separate research branch; no live change.

## Finding: FAIL; stop this candidate

Combined log-loss gain **-0.0031968**, 90% season-bootstrap interval **-0.0100341 to +0.0041192**. Positive means better. Better in 4/9 seasons. Both registered gates fail: the lower bound is not above zero, and six markets are worse than the -0.0005 mean tolerance.

| Market | Mean gain | 90% interval |
|---|---:|---:|
| playoff | -0.0000006 | -0.0100615 to +0.0105747 |
| div | -0.0045639 | -0.0128087 to +0.0033843 |
| pres | -0.0026357 | -0.0068457 to +0.0011207 |
| r2 | -0.0023852 | -0.0125466 to +0.0099664 |
| r3 | -0.0026761 | -0.0144509 to +0.0099194 |
| final | -0.0062499 | -0.0149761 to +0.0043944 |
| title | -0.0038660 | -0.0145936 to +0.0086520 |

This rejects this coefficient-1 fading roster correction on this rebuilt, internally paired baseline. It does not establish that roster information is useless. No additional forms, fades or windows were tried. Live remains the current goalie-inclusive model.

## What was actually tested

Canonical production settings, including 20% raw MoneyPuck regular-season xG, shot-based playoff ratings, fade 3, OT fix, frozen RAPM skaters and goalie scale 0.438. Candidate only: add k/(gp+k) times recent lineup value minus last-season average, with common start-of-season ratings for both seasons. Existing current-season lineup term unchanged.

The old preseason term was disabled after uncertain gains and worse opening forecasts in the older points/GSAx test (WORKLOG, 15 October). Simply re-enabling it under RAPM would also mix valuation scales. The candidate fixes that research-only mismatch and disallows actual future opening lineups.

No extra before-opening-night forecast is tested: before a team has played, its uncentered extra is zero. Nine initial league checkpoints have identical probabilities across arms. Historical roster observations do not prove a roster was known before opening night. This scope was written before results.

## Reproducibility: important qualification

The supplied private bundle hash was verified. Independently rescoring its original paired CSVs reproduces the original +0.000209335549 gain and interval. All nine supplied skater caches reproduce the original normalized rating hashes exactly.

However, the supplied bundle does not contain raw shots or the nine goalie rating tables. The new pair uses the registered local frozen shot-xG reconstruction. Its rebuilt goalie hashes differ from the supplied identities in all nine seasons even after normalizing line endings. Thus the new baseline is production-equivalent in settings, but is NOT an exact reconstruction of the supplied canonical replay inputs. This limitation was registered before either new arm ran. Do not call it a byte-for-byte canonical rerun or replace the original goalie result with it.

Compared with the supplied goalie outputs, all keys and outcomes match, but individual probabilities differ by up to 0.039. The paired new arms use identical skater AND goalie ratings; the result is valid for that rebuilt frozen pair. Exact reproduction of the older run would additionally require its goalie tables or original shot-xG inputs.

## Checks and evidence

7,494 team-checkpoint rows per arm; nine seasons, seven markets. Strict key/outcome pairing, valid probabilities and identical rating identities pass. All 244 input/cache file hashes remain unchanged after both runs. Eight NHL unit tests pass (four new tests cover common-scale history, unavailable ratings, no future opening lineup and the registered fade).

All computations ran locally: baseline 543.9 seconds, candidate 510.9 seconds. No GitHub replay minutes, website deployment, workflow activation or live setting changes.

Public aggregate results: research/nhl_preseason_roster_results.json. Private evidence bundle: research/nhl_preseason_roster_bundle, containing both replay outputs, exact used rating tables as lossless JSON, input manifest, reproduction checks, commands/scripts, logs and runtimes. Recreated exported tables are hash-checked against the ratings actually used. The original supplied bundle is untouched.

Decision: FAIL / research only / no merge or model adoption requested.
