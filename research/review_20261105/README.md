# Reproduction notes: later-work independent review

Public source pinned at f5fcc9c (includes requested injury, award and NBA-diagnostic commits). Source fingerprints are in review_source_manifest.json. No original production/research source or model result was changed.

From repo root with numpy/pandas/scipy available:
- python research/review_20261105/test_later_work_review.py
- python research/review_20261105/reproduce_diagnostics.py <private-output-dir>
- python research/review_20261105/nhl_pool_probe.py <frozen-published-nhl-data-dir> <private-output-dir>

The eight tests include witnesses of existing defects; passing is not a repair. AST extraction runs the original injury feature functions without their import-time downloads and injects synthetic input frames. The diagnostic script reproduces all NBA early cohort figures/ordinary errors, adds season-clustered errors, and selects Vezina's existing replay rows at production's max-team-games temperature trigger. The pool script inspects all 432 voted-award pools using original pool formation (no award-weight fitting). Derived evidence is included.

All ten award JSON entries were independently reproduced by calling nba_nhl_award_eval.evaluate() and writing its returned object outside model/. award_eval_reproduced.json equals the committed publication semantically, including intervals and gates.

The original NFL NPZ/feature caches are missing/untracked. See the NFL review's exact input request: these source probes do not reproduce RMSE. The Stage 2 failure remains a rejection; its checked-in loop omits the registered week-17 checkpoint. No corrected futures replay was run.

CBB collector review is separate in private branch codex/cbb-collector-review-20261105, finding commit da931787. None of these artifacts changes a model, price input, adoption rule, website or workflow.
