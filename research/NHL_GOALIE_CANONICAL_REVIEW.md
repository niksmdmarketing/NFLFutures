# Independent review of the NHL goalie deployment

5 November 2026. Scope: canonical rule/result e9b0490 and deployment f566e38. Review only; no production change.

## Findings
1. The new NHL_RS_XG switch resolves the previous baseline mismatch: RS_XG=raw selects all-situation MoneyPuck raw game xG only for the 20% regular-season source. With NHL_XG unset, the playoff source remains shot differential times league shooting percentage. Fade 3, OT_FIX with edge 0.5, TAU_PRE 1.5, last-five RAPM roster and PRE=0 are consistent with the inspected production components. Injuries and their roster add-back are explicitly excluded from both historical arms, so this is production-equivalent only for the replayable components.
2. Independently recomputing from the published nine-season score tables reproduces combined gain +0.000209335549, 90% season-bootstrap [0.000064557881, 0.000369279510]. The worst market mean is division -0.000169209940, above -0.0005. Both registered gates pass. The ancillary leave-one-out choice is not independent evidence.
3. The cache manifest lists nine SHA256 entries. The strict scorer demands matching row keys, outcomes and player-rating identities. Original paired replay CSVs and Claude's actual cache directory were not available in the inspected checkout; published output hashes cannot themselves verify those bytes. The aggregate arithmetic is reproduced, not a full independent nine-season replay. Preserve/export the exact baseline/variant CSVs, rating identities, cache and raw-input manifests for independent reconstruction.
4. Live goalie construction uses the same game_values_ratings and roster_term logic, 0.438 scale and frozen goalie table. The no-goalie counterfactual subtracts the complete new roster term and adds the old term, retaining other settings and injury adjustments. It is archived as ng_* alongside the live version. The existing g_* history is not rewritten. No additional simulation or re-tuning was performed for this review.
5. Minor diagnostic defect reproduced: when best_season returns no skater data, live_term(..., goalie=True) returns a zero Series instead of None. nhl_model consequently marks roster_diag.goalie=true despite missing lineup input. This does not by itself alter forecasts when both terms are zero, but the availability indicator is misleading. If the skater RAPM file itself is missing, the older fallback can include points/GSAx goalies; describing every fallback as strictly no-goalie is too broad.

## Proposed fixes / evidence to retain
- Add missing-input tests and make goalie-enabled status reflect actual valid skater, goalie and starter coverage, not merely a non-None return. This is an operational diagnostic repair, not permission to alter rating coefficients.
- Keep raw paired replay artifacts and cache/input identities privately. Record actual fallback method/version in each forecast.
- Continue the registered ng_* forward comparison. Do not claim profitability or that the historical replay validates injury add-back interactions, preseason trades or the next confirmed starter. The canonical rule already discloses its overlapping fitted scale and leave-one-season-out shot-quality limitations.

Private evidence and executable reproductions: outputs/live_changes_review_20261105/. No demonstrated live forecast calculation regression was found in the inspected goalie component.
