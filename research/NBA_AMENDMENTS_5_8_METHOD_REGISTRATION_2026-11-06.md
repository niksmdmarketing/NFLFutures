# Proposed method registration — review dated 6 November 2026

This is a review proposal, not an amendment committed to either repository.

Before applying the proposed corrections and refreezing challenger c, record:

1. **Probability recovery.** The appearing-conditional distribution is defined only for a feasible stored mixture and positive appearance probability. Invalid mixtures must not be clipped/renormalized into apparent certainty. Positive-count tail division avoids cancellation near zero. Exact archive rounding requires the separate decision in item 5.
2. **CDF boundary.** Use a common upper endpoint `g(1)=1` for every bin, including repeated terminal CDF values. The patch appends/replaces that endpoint before interpolation.
3. **Support floor.** Mix `0.999 × calibrated conditional PMF + 0.001 × frozen conditional PMF`, during holdout evaluation and final application. Appearance probability is preserved. Stat-level identity decisions remain identity.
4. **Sparse bands.** The existing implementation fits a stat/band only when it has at least **200 CDF training pairs**; absent maps use identity. This is pairs, not players or games.
5. **Serialization precision — unresolved policy.** The producer rounds appearance probabilities to six decimals and count PMFs to seven. The supplied strict validator permits machine roundoff only. Establish a precision-based tolerance, reconstruction method or common exclusion rule before relaxing it. Validate it synthetically near zero and when zero mass is smaller than `1-p_appear`. Do not tune it from priced results. The review did not inspect real PMFs or estimate affected coverage.
6. **Holdout score.** The supplied patch uses the literal mean log probability of the actual count; probability zero gives negative infinity. The existing code instead clips at `1e-9`, which can change keep/identity. Retaining that cap is an alternative explicit method choice to register before freeze. Resolve this using the intended score and archive precision, without choosing based on which challenger survives.
7. **Freeze handoff.** Recompute the holdout decision from the exact development cohort used for refitting, then freeze and record the new artifact SHA-256. A previously saved check JSON must not choose maps for a different cohort/code version. The review deliberately did not open any actual check or frozen artifact.
8. **Identity I/O.** Supply `has_close_quote` as nonnumeric metadata from the collector, and read only whitelisted identity columns in the fallback. The optional private patch adds the field for newly reduced rows. Existing exports need a separately authorized metadata refresh; the matcher stops on a missing flag instead of reading numeric prices or guessing from timestamps.
9. **Scoring.** Keep b primary and c secondary. Use identical eligible candidate rows, lines, books, cutoffs and gate definitions; stop if c is missing on b's primary candidate rows. Model-specific wager selection remains separate under the same registered thresholds.

No implementation or artifact should be silently replaced after inspecting priced results. No prices or actual outcomes were inspected during this review.
