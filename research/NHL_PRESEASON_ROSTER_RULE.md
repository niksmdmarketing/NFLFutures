# NHL preseason roster component: registered early-season replay

Written 5 November 2026 (Sydney), before any candidate replay. Research only; no live change. Append dated amendments/results below this rule.

## Question and previous decision

Does a fading correction for roster change since last season improve the canonical live model, which already includes RAPM skaters and starting goalies (scale 0.438)? WORKLOG, 15 October, records the older points/GSAx preseason component: small uncertain gains overall and worse opening forecasts, with opening-night absences mistaken for roster changes. This explains PRE=0, but does not test this RAPM configuration.

## Frozen baseline

Public main f3b299a; the canonical **goalie arm**, not the former scale-zero baseline. Settings:

```
BT_SIMS=2000 NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_RS_SHOT_W=0.2
NHL_RS_XG=raw NHL_PO_FADE=3 NHL_OT_FIX=1 NHL_OT_EDGE=0.5
NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0
NHL_LINEUP_VAL=rapm NHL_LINEUP_GS=0.438
RAPM_LAM=300000 RAPM_KBOX=1
```

NHL_XG and other experimental switches unset; TAU_PRE=1.5, simulation seed 3. Dated injuries and live injured-player add-back are unavailable historically and absent in both arms.

## One candidate; no fitting or sensitivity search

Enable only the preseason roster component, coefficient 1. With earlier current-season games:

`extra = k/(games_played+k) * (mean lineup value over last 5 earlier games - mean lineup value last season)`

Keep the current-season recent-versus-average component unchanged and apply the usual league centering. k is the baseline's fitted prior weight; no new fade. Value BOTH seasons' lineups with the SAME frozen start-of-season-y RAPM skater/goalie ratings and goalie scale 0.438. The old knob mixes RAPM current values with points/GSAx previous values; correct this in the research candidate only.

Never use the actual future opening lineup. Until a team has played, extra=0. Missing previous-season lineups also mean no preseason component. No invented expansion roster, traded-player assignments or future minutes. Current lineup dates must be strictly before cutoff.

**Scope:** this tests the preseason-prior component once an early-season lineup is observed. The supplied history does not establish which roster/starter was known before opening night. It cannot validate a genuine before-opening-night roster forecast. A pass cannot establish that missing evidence.

## Frozen inputs and reproduction

Supplied canonical bundle: private main 5ac409f6, archive SHA-256 `193df0de5a97c34af5c6ade705137b178509c426797bcfea136935cfbbb4cc2c`. Reproduce its existing paired score first. Both new arms read its exact RAPM skater cache.

The bundle contains paired outputs, skater caches and rating identities, but not raw shots or goalie rating tables. Freeze available inputs from `outputs/shadow_review_20261105`: published tree `18fac281801dd08b28bd03d269aef01d9bcdc8b3`, shifts tree `95ee088f317c1ee79248cb8fa93f596e890d5d42`, reconstructed LOSO shot-xG, and tracked MoneyPuck/lineup files. Save every input hash before either arm runs. Rebuild goalie ratings from the same frozen earlier seasons; require identical identities across arms. Baseline first. Compare it with the supplied goalie arm and disclose discrepancies; do not claim byte-for-byte input reproduction if they differ. Do not choose reconstructions according to scores.

No network data updates during the pair. Fail on unavailable required ratings, changed inputs/cache, duplicate keys, mismatched outcomes or invalid probabilities. Preserve original bundle and both new output directories.

## Seasons, scores and gates

Exactly 2015-2018 and 2021-2025. Same weekly checkpoints and seven markets as `nhl_goalie_roster_score.py` / `nhl_holdout.py`. Retain initial checkpoints where extra=0; no post-result window selection. Strict paired keys/outcomes and identical ratings. Mean market log-loss gain; 4,000 season bootstrap draws, seed 1, 90% interval.

Pass only if combined 90% lower bound >0 AND every market mean gain >=-0.0005. Otherwise fail and stop this candidate. Report season and market scores. Early-season effects are descriptive only. No sensitivity variants or new gates after results.

## Limits and decision

Development evidence: overlapping research seasons, previously fitted scales, LOSO xG calibration includes later seasons, and roster minutes come from earlier realized games rather than advance availability. The historical team prior uses more than last season, so this is an approximate correction, not an exact decomposition. No claim of a betting edge. No promotion, merge or website change in this task; report provenance, gates and commits.
