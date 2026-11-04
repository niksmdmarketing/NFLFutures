# NFL QB shadow v2 review — 5 November 2026

Reviewed d5496ff. Architecture: playoff-only rating shifts are wired through every playoff round and Super Bowl, with no random draws added to live v4. Kaplan-Meier is the intended censored-duration estimator; tail and whole-playoff assumptions are explicit in the dated amendment. Matching safeguards are retained.

## Two defects found and corrected on this branch
1. **Excess unresolved-tail probability.** km_pmf returns conditional finite masses whose sum is 1-tail. draw_absence multiplied their cumulative sum by 1-tail again, inflating the out-for-rest-of-season/playoffs draw. A 50% unresolved tail became 75%; conditional on already missing one game in the regression example, 2/3 became 8/9. Removed the duplicate multiplication. New frequency tests cover finite masses and conditional/unconditional tails.
2. **Postseason-only episodes skipped.** An episode with no remaining regular-season games was ignored. Such an ESPN-only season-ending injury could still leave the reference QB healthy in playoff forecasts. Episodes now produce playoff shifts even when all regular-season games are played. No-episode identity is preserved.

Version 2.1-review-20261105 separates corrected forecasts. Existing snapshots and original amendment remain unchanged. Earlier v2 tail/median examples are affected by the defect and should not be used as calibration evidence. No partial playoff returns added, no fitted parameters or live v4 changes. An unresolved Kaplan-Meier tail is not an identified permanent absence; treating it as out for the remainder remains the registered conservative approximation.

## Verification
- 16 QB-shadow tests pass, with an offline 2024 public-schedule fixture so integration cannot silently skip on network failure.
- 6 simulator logic tests pass.
- Parent pre-v2 simulator versus v2 simulator with playoff shifts omitted: bit-identical for all eight outputs on a 128-draw full schedule, both rest_pen=0 and rest_pen=17.891.
- Playoff-only shifts leave playoff qualification unchanged while changing championship probabilities.

Review corrections are ready on codex/qb-v2-review-20261105, not merged by this review. This is code validation, not evidence of improved predictive accuracy or live adoption readiness.
