# Test power: inputs list (fixed 5 Nov 2026, before any SD is computed)
Under research/TEST_POWER_RULE.md, Amendment 1 item 5. Every committed results file in research/ and model/replay/ was scanned (research/*results*.json, model/replay/*score*.json), plus the NFL state-space results on branch claude/nfl-state-space-test. Gain = baseline log loss - challenger log loss, futures markets, per season.

## Included (one entry per comparison)
| Sport | Comparison | File and field | Seasons | Per-market by season |
|---|---|---|---|---|
| NFL | Efficiency weight E vs v4 | research/nfl_efficiency_weight_results.json stage2.per_season | 2022-2025 | no |
| NFL | Non-QB injuries vs v4 (futures stage) | research/nfl_nonqb_injury_results.json stage2.per_season | 2022-2025 | no |
| NFL | Recalibration layer vs v4 | research/nfl_recalibration_results.json primary.by_season | 2016-2025 | no |
| NFL | Tau fade vs live | research/nfl_tau_fade_results.json results.average.by_season | 2013-2025 | no |
| NFL | v5 promotion vs v4 | research/nfl_v5_promotion_results.json results.average.by_season | 2013-2025 | no |
| NFL | State-space (SS) vs v4 | branch claude/nfl-state-space-test research/nfl_state_space_results.json stage2.arms.SS.gain_by_season | 2022-2025 | no |
| NHL | Goalie roster (pre-season prior) vs live | research/nhl_goalie_roster_results.json per_season_gain | 9 seasons | yes |
| NHL | Goalie canonical vs live | research/nhl_goalie_canonical_results.json per_season_gain | 9 seasons | yes |
| NBA | Player term, corrected (in season only) vs live | research/nba_player_first_futures2_results.json by_season | 2015-2026 ex 2020 | no |
| NBA | Joint A2 vs A1 | model/replay/nba_joint (arm CSVs) | 2016-2026 ex 2020 | yes |
| NBA | Joint A2 vs A0 | same | same | yes |
| NBA | Rosters A1 vs A0 | same | same | yes |
| NBA | Joint without scalar vs A1 | same | same | yes |
| NBA | Joint vs A1, absence sensitivity rosters | same | same | yes |

## Excluded, with reason
- research/nba_player_first_futures_results.json: superseded by the corrected version (futures2).
- research/nfl_extra_stats_results.json: game win log loss, not futures.
- research/nfl_nonqb_injury_results_reportonly.json: report-only duplicate of the included file.
- research/nfl_week18_rest_results.json: game-level effect estimate, no per-season futures gain.
- research/nfl_qb_news, nfl_qb_oracle, nfl_synthetic_market, nfl_props_receipt_fix results: no per-season futures gain.
- research/nba_game_env*, nba_games_pt, nba_minutes*, nba_props*, nba_points_dispersion, nba_player_first_avail, nba_player_first_results: games, props or weights, not futures; *_firstrun and *_before_teamfix are superseded versions.
- research/afl_* results: game (match) scores, not futures.
- model/replay/<sport>_score.json: single-model scores against a base rate, not paired comparisons.
- Labels: NBA player term (futures2) was scored on replays whose 2016-2019 and 2021 format setting was not recorded (likely BT_ERA=0; see research/NBA_REPLAY_STANDING_RULE.md, Amendment 1). The NBA joint arms are era-correct. The five NBA joint pairs share seasons, baselines and outcomes, so they are not independent comparisons.
