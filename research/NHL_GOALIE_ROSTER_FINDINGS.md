# NHL starting-goalie roster component: findings

5 November 2026, Sydney. **PASS under the written research gates. Report only: no live change.**

## Result
Live replay first, then exactly the same RAPM-skater replay plus NHL_LINEUP_GS=0.438. No in-season goalie-rating updates. 2,000 simulations per checkpoint. Nine seasons: 2015–2018 and 2021–2025, 7,494 matched team/checkpoint rows in each arm.

Combined log-loss gain: **+0.0003169013**, 90% season-bootstrap interval **[+0.0001355132, +0.0005010444]**. Better in 7/9 seasons (diagnostic, not an added gate).

| Market | Mean gain (positive is better) |
| --- | ---: |
| playoff | +0.0003363 |
| div | +0.0003497 |
| pres | +0.0001775 |
| r2 | +0.0002790 |
| r3 | +0.0005910 |
| final | +0.0003374 |
| title | +0.0001473 |

- Combined 90% lower bound > 0: **pass**.
- No market mean below -0.0005: **pass** (all seven mean gains are positive).

Scored with research/nhl_holdout.py via the paired validation/scoring wrapper, baseline first, unchanged clipping and 4,000 season-bootstrap draws, seed 1. Per-season/market scores and output hashes are in nhl_goalie_roster_results.json.

## Protocol and reproducibility
Original rule committed locally as 8ccc7da; data-coverage amendment 1c8d305, both before any replay. The separate NHL review branch preserves those changes as def2e6c and 077e9f4. The archive starts in 2014, so no prior RAPM data exists for a 2014 RAPM replay. Excluded 2014 before scores rather than silently compare an old-model fallback. No replacement season chosen.

The first baseline used newly fitted skater floats and the first variant read those values from CSV cache. Strict byte identities caught the parse/serialization difference before scoring. Both initial arms are preserved, unscored. Reran baseline then variant using the same frozen cache; final skater AND goalie rating identities match in every season. This is an input-pairing repair, not a parameter/gate change. All team/checkpoint keys and outcomes match, no duplicate keys or missing market values, and all probabilities are valid.

Replay wrapper fails if RAPM skater/goalie ratings are absent. All nine seasons have 100% team-game MoneyPuck xG coverage. Frozen public source trees, actual file hashes, package versions, command environments, input cache inventory and logs are private in outputs/shadow_review_20261105/. The cache inventory also preserves available unused years; only the registered seasons are scored.

Reproduce after materializing the same archived inputs and shot xG: use the exact environment in NHL_GOALIE_ROSTER_RULE.md, set BT_OUTDIR separately, run research/nhl_goalie_roster_replay.py NHL_DATA_DIR 2015 2025 with NHL_LINEUP_GS=0 then 0.438, and score with research/nhl_goalie_roster_score.py BASELINE VARIANT --out RESULTS_JSON. Use a fully materialized, identical RAPM cache for both arms.

## Meaning and limits
This supports restoring the missing recent-starter goalie component in the tested roster term. It does not authorize a deployment, and does not repeat the failed older NHL_GOALIE_INSEASON_RULE.md experiment.

The term compares recent lineups with the current season's average, with NHL_LINEUP_PRE=0. It is not a projection of tomorrow's confirmed starter. A preseason trade already reflected in every game this season can still produce no recent-versus-season roster adjustment; this test does not fix that separate prior/roster issue. Injury costs and their roster add-back interaction are not historically replayed here.

The fixed 0.438 scale was fitted on overlapping historical seasons. The unchanged shot-quality builder uses leave-one-season-out calibration including other, later seasons; player-rating aggregation itself uses earlier seasons. This is development evidence, not fully untouched validation or proof of a market edge. Do not treat the ancillary leave-one-season-out selector as an independent confirmation. No further scales or models tested.
