# NFL props: independent upload receipts repair

5 November 2026. Research/scoring repair only. No forecasting method, parameters, adoption gates, website output or schedule changes.

## Finding and fix
The previous scorer treated a Git commit's timestamp as an upload receipt. A commit clock does not prove GitHub had the forecast before cutoff. The replacement reads GitHub's server-stamped push activity, checks the exact archive branch and commit ancestry, and uses the earliest qualifying push. Snapshot creation must precede that receipt, which must precede the horizon cutoff. No commit-clock fallback.

It checks the actual forecast content hash (excluding the self-identifying forecast_sha256 field, matching the writer), the embedded/index hashes, game ID and kickoff/generation timestamps. Paths outside snapshots and files with later Git edits are excluded. Server receipts are paginated and cached with repository/branch identity so older proof survives API retention; an API failure may use saved server evidence but never manufacture a receipt. No proof means exclusion.

The workflow supplies its built-in token and saves new score files as scores/server_received_60.json and scores/server_received_360.json. Original score files stay untouched. No new narrow collection-age gate is imposed retroactively: age at cutoff is reported separately. A forecast pushed after cutoff is ineligible even if generated earlier. A freshly generated snapshot is not eligible until an actual push has been observed; the next job can score it.

## Actual archive verification
Using frozen GitHub activity and actual archived snapshot bytes, with the original published outcome labels held fixed, the primary 60-minute correction reproduces the independent audit: v1.1 retains all 19 completed games; v1.2 retains 16 of the previously reported 19. Excluded v1.2 games: 2026_07_DEN_ARI, 2026_07_GB_DET and 2026_07_LA_LV. These lack independently proved pre-cutoff server receipt for a qualifying snapshot. Generation timestamps alone do not rescue them.

This is a receipt-only rescore, not a fresh outcome validation or proof of profitability. Per-player corrected outputs, the frozen-label rescore script and logs stay private/local under outputs/nfl_props_receipt_fix_20261105. Original published results remain preserved.

## Validation and rollout
20 relevant NFL props unit tests pass, covering server rather than commit time, late/missing evidence, wrong branches, modified files, hash and game identity, path containment, timezone-aware times, and existing outcome/matching rules. The branch is for review, unmerged; scheduled production scoring is not yet repaired until this branch is merged. No synthetic/manual forecast is presented as a live qualification.
