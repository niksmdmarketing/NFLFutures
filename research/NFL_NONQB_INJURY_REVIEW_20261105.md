# NFL non-QB injury work: independent review, 5 November 2026

Reviewed source included in public f5fcc9c, covering the requested 9a9724a..3cf1bf3 work. Review only; original feature builder, models and results are unmodified.

## Finding 1 — P1: a position fallback can look into later weeks

research/nfl_nonqb_injury_test.py:88-91 falls back from a missing current-week roster position to all roster rows for the player and takes `rows.pos2.iloc[-1]`. It neither restricts week <= w nor sorts those rows by time. A later roster entry can therefore supply a historical predictor.

Offline reproduction, executing the original feature functions: a player has two earlier games at 80% snaps, is listed Out in week 3, is absent from that week's roster rows, and has a week-4 position entry. Changing ONLY week 4 from OL to WR moves week 3's missing share from OL=0.8 to WR=0.8. Earlier-game information is identical. Probe: test_witness_future_position_changes_an_earlier_feature.

This proves the implementation is not invariant to future position records. It does not measure how often the path ran in the published dataset. That incidence requires the original raw inputs. Treat the Stage 1 timing assurance as provisional until that trace/fix is checked; I am not claiming the whole reported gain is caused by this path.

Fix: prefer the current week's historical position, otherwise the latest documented position at/before that week, sorted explicitly. If unavailable, mark/count it as unknown instead of using a future roster row. The current players.csv position fallback also needs a historical-role check: a present-day position is not automatically the position known in the replay week. A static player-ID crosswalk is a different matter and can legitimately resolve identity retrospectively.

Rebuild/version the feature cache when correcting this. build() returns an existing OUT_CSV without a source/input fingerprint, so changing code alone does not regenerate features. Preserve the original result and compare the corrected version under the same gates.

## Finding 2 — the roster-status timing check is not a timestamp audit

The rule infers pre-game availability because non-ACT players almost never played. That is consistent with pre-game statuses, but the same association could hold for a retrospectively coded status. It cannot establish when the information was available.

The upstream [nflreadr weekly-roster documentation](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html) establishes week-level rosters rather than a latest-season roster; it does not establish a historical pre-kickoff publication/capture time for each row. I found no such cutoff timestamp in this feature construction or in the supplied review artifacts.

This is an unresolved provenance qualification, NOT a finding that all roster statuses are post-game. Confirm the upstream status definition/snapshot convention or compare historical official inactive/reserve notices at the declared forecasting cutoff. Do not infer an earlier-hours forecast improvement from information only released nearer kickoff. The final injury-report-only sensitivity is useful but is not a substitute for that audit.

## Finding 3 — the scoring population silently excludes known-zero cases

season_features():77-78 omits a team/week when no player has two previous appearances. Stage 1 then drops games missing either team's row. Week 2 necessarily has at most one earlier regular-season game, so its features are omitted, even though the rule implies a zero adjustment when nobody meets the two-game threshold.

Probe: test_witness_week2_known_zero_is_dropped. Return a zero vector when the necessary input tables exist and no player qualifies; distinguish that from genuinely missing data. Report the exact excluded game IDs/population.

This does not by itself explain away the gain: adding cases with identical baseline/injury predictions contributes zero paired difference. It does mean the headline weeks-2-onward scores are for a narrower population and should be labelled/recomputed accordingly.

## Finding 4 — P2: checked-in Stage 2 loop omits the registered week-17 checkpoint

research/replay_nfl.py:113 uses range(BT_WMIN, min(last_week - 1, 18)). With an 18-week season and BT_WMIN=2 this produces weeks **2..16**, fifteen checkpoints; the rule/result text says **2..17**, sixteen checkpoints. The upper bound is exclusive.

Probe: test_witness_stage2_loop_omits_registered_week17 evaluates the original AST loop expression. Check the actual archived output weeks before claiming the registered window was scored. Both arms sharing the same omission does not fulfill that scope. A corrected historical loop should include the checkpoint before the final regular-season week; preserve the old outputs and report the corrected pair separately. No Stage 2 replay was rerun here because its frozen inputs/output bundle is absent, and its recorded failure must not be turned into an adoption on this review.

## What checks correctly

- The ID fix restores an importance when weekly pfr_id is missing but the player-table crosswalk resolves it. The depth-chart position correctly maps a coarse DB to CB. Direct original-function probe passes.
- Importance uses only played.week < w in Stage 1; changing current-game snap share leaves the earlier forecast feature unchanged. Stage 2 deliberately uses snaps through the completed checkpoint week (<= w), which is appropriate for that after-week definition.
- QBs/K/P/LS are excluded by the resolved position. Team aliases and snap-share unit conversion are consistent with the stated feature.
- The baseline is explicitly the frozen ratings-only copy, without the full live QB/pressure layers. The result is not a demonstrated improvement over the entire live game pipeline.
- Stage 2 correctly excludes INA from the longer-absence carry-forward and applies each team's four-game window to its own remaining games. The four-game duration for every qualifying reserve/released status is a registered simplifying assumption, not an empirically identified return model.
- The stored Stage 1 numbers meet its written gates. The stored Stage 2 numbers fail all relevant adoption requirements (lower bound -0.000194, 2/4 seasons, seed1 mean -0.00138). Keeping it out of shadow/live is correct. No live non-QB injury wiring was found.

## Reproduction limits

The original data/research/nfl_wf_features.npz and both non-QB feature caches are untracked and absent from the available workspace copies. I did not rebuild years of play-by-play or claim to reproduce RMSE 12.9128 -> 12.8288 numerically. Independent evidence here is original-function counterexamples/control checks plus rule/gate/source inspection.

For a full numeric rerun Claude should privately export the frozen NPZ, corrected feature tables, joined game identities, raw-input hashes and settings identity. Also trace how many actual rows used future/current-metadata position fallback. The fitted closing-line blend is descriptive, fitted on the test rows; it is not an out-of-sample proof of a betting edge.

## Reproduce / decision

Run `python research/review_20261105/test_later_work_review.py` (pandas/numpy/scipy available). The feature probes AST-load the ORIGINAL functions to avoid the module's import-time downloads; they inject controlled input frames, not rewritten feature logic. Some tests deliberately witness current defects.

Recommendation: fix the bounded-position lookup and confirm source timing before strengthening the Stage 1 claim. Preserve its promising historical result as provisional development evidence. Do not resurrect the failed futures layer or change anything live on this review.
