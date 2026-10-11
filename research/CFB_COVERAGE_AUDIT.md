# College football coverage audit — 12 October 2026

No odds, paid sources or fitted forecasts added. Other sports unchanged.

The prior **Advanced GP** label was ambiguous. `playsgame_off_n` is the denominator of the provider's FBS-vs-FBS season summary, not the number of available game logs. It is now **Summary GP (FBS)**. Records GP includes FCS opponents and postseason; the summary also includes covered postseason FBS-vs-FBS games, but excludes FCS. Source summaries remove garbage time. Player summaries and game logs are different aggregation products; do not assume identical coverage.

Read-only audit: `research/audit_cfb_coverage.py`, using the cached nine-family collection and season-specific FBS reference classification. Completed schedule rows joined to advanced game logs on normalized `(game_id, team_id)`, one-to-one; no guessed identities or repaired source values.

| Season | Teams | Record-vs-summary GP mismatches | Record team-games | Advanced covered team-games | Covered non-FBS-opponent team-games | Summary team-games | Matched FBS scope mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 136 | 126 | 1,742 | 1,739 | 125 | 1,614 | 0 |
| 2026 | 138 | 117 | 777 | 777 | 119 | 658 | 0 |

These are **team-games**, so a game between two FBS teams contributes two rows. For every team in both seasons, summary GP equals the count of covered FBS-vs-FBS games. The numerical identity `plays_off / playsgame_off_n == playsgame_off` holds to floating-point precision (maximum error 7.1e-15).

Actual missing 2025 advanced game logs:

- `401754622`: Georgia Tech vs Gardner-Webb (one FBS team row), regular season.
- `401778314`: Minnesota vs New Mexico (two FBS team rows), postseason.

No completed 2026 FBS team-game lacked an advanced row in the audited snapshot, through 11 October. This does not guarantee the provider's internal play completeness or immediate future publication.

**Safe use:** per-game advanced numbers are usable descriptively for their defined covered FBS-vs-FBS, garbage-time-filtered sample. Do not divide source totals by record GP, treat the averages as official all-opponent box averages, or infer that summary GP is the denominator of per-play/drive/opportunity statistics. Missing logs remain null. EPA has provider-model and play-quality limitations; this audit does not validate predictive accuracy.

Formatting changes: explicit count-field metadata for player/game counts and final scores; rates including embedded `_rate` names such as `EPA_success_rate_rz` use percentages; EPA/means/weighted line yards retain decimals. Team per-game counts remain fractional averages. Pass/rush labels are now distinct in the all-stat and historical selector views.

CI now has a dedicated **blocking** four-test CFB step; the existing optional all-sport test step is not evidence of CFB success on its own. Four local tests passed, including formatting and label uniqueness regressions. CI and final rendered checks must be confirmed from the ensuing run before declaring the fixes live.

Definitions: https://github.com/sportsdataverse/cfbfastR-cfb-data/blob/main/DATASETS.md (season-level summaries, game logs and known ceilings).
