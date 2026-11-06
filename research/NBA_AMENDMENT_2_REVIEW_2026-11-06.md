# NBA Amendment 2 independent review — 6 November 2026

Reviewed public branch `claude/nba-props-price-test`, commit `f9bb0026160ad6cfee5a33cc4dd6be331af57731`. Files: rule, scoring pieces, assembly runner; name helper read to check identity behavior. No repository branch edited. Proposed changes are attached as a unified patch. No real price CSVs, forecasts, box scores, research results or profits opened; no real mechanics or scoring run executed.

## Findings, ordered by impact

1. **[P1] Pair timestamp validation admits future quotes.** `research/nba_props_price_test.py:83`, applied at lines 98 and 113. `_times` returns the minimum of the two side timestamps. Entry over at 20:00 and under at 23:30 passes a 23:00 cutoff because only 20:00 is checked. Likewise one pre-tip side can conceal a post-tip closing side. Both violate Amendment 2 items 3–4 and can contaminate entry or CLV. Synthetic reproductions confirmed both. Missing one side's timestamp can also be hidden, or an entirely missing side column can cause a join exception. Proposed patch retains oldest AND newest timestamps, requires both, and validates the whole interval.

2. **[P1] Live forecasts without completion evidence are assumed timely.** `research/nba_props_price_run.py:64`. The fallback is `generated_utc`, then the cutoff itself, even though the rule requires when the live forecast finished. A forecast missing completion evidence can therefore pass timing. Proposed patch requires `forecast_finished_utc` for live forecasts and `run_utc` for replays, with explicit timezone; missing evidence stops the run. Confirm the archive producer's timestamp contract before accepting any alternate completion field.

3. **[P1] The 95% matching requirement cannot stop scoring, and the reported rate has the wrong denominator.** `research/nba_props_price_run.py:171` and `:204`. Unmatched counts sum player-games, but the denominator counts unique player names across all games. The result can even be negative. Unmapped fixtures disappear from that denominator. `score` then proceeds without checking the required match rate. Proposed patch measures matched versus all priced fixture/name pairs and stops scoring below 95%.

4. **[P1] One observation per actual player/game/stat is not enforced after identity resolution.** `research/nba_props_price_run.py:148` and `:155`; upstream aggregation is by raw player name at `research/nba_props_price_test.py:126`. Different bookmaker name strings can map to the same ESPN athlete, and merges accept duplicate forecast/outcome keys. These cases create multiple regression observations or bets for one athlete. Proposed patch rejects post-match duplicate game/athlete/stat groups and uses validated many-to-one merges. Reconcile aliases before choosing the common line; do not arbitrarily drop one duplicate after looking at prices. This is a missing invariant found by static review, not evidence of a duplicate in actual data.

5. **[P1] Missing played-player statistics silently become under outcomes.** `research/nba_props_price_run.py:158`. After the minutes filter, a missing `actual` value satisfies neither `actual > line` nor any explicit missing-data check; the Boolean comparison becomes false and is cast to zero. Proposed patch stops on missing played-player statistics. No real missing outcomes were inspected.

6. **[P2] Bootstrap clusters use decision date rather than game date.** `research/nba_props_price_run.py:152`. A tip at 00:30 US Eastern has a cutoff on the previous date. Clustering on cutoff date can split games from the same game date or merge different game dates. Amendment 2 item 6 specifies game-date resampling. Proposed patch derives the Eastern date from the fixture's scheduled tip.

7. **[P2] G1 has an additional undocumented 50-observation minimum per window.** `research/nba_props_price_run.py:210` and `:216`. The amendment's 50-bet requirement belongs to G3; G1 requires identifiable fits and positive window estimates, not 50 observations per window. Existing code can declare G1 insufficient even when its stated fit checks pass. Proposed patch removes this extra count threshold and lets the registered rank/spread/condition/convergence checks determine fit validity. G2/G3 count thresholds remain unchanged.

## Requested checks that are implemented correctly, subject to findings above

| Requirement | Review conclusion |
|---|---|
| Entry and close on same numeric line | Close merges on fixture/name/stat/book/line, never substitutes the closing main line. |
| Same entry book set at close | `devig` requires one valid close per entry book; incomplete closes become missing CLV. |
| Missing close retained in profit | Bet rows retain profit; `clv_summary` excludes missing CLV only and counts missing closes. |
| 24-hour entry / 60-minute close ages | Oldest-side age comparison is correct; newest-side timing was missing (finding 1). Exact age limits are accepted; close exactly at tip is rejected by the proposed patch. |
| Two-book minimum | `primary = books >= 2`, and scoring gates use primary rows. |
| Unpenalized logistic fit | Newton likelihood steps, intercept, train-standardized predictors, clipping at 1e-4. No penalty term. |
| Rank/spread/condition | Full rank, spread >1e-8, condition <1e8 checked. Failed fits are excluded and reported. |
| Bootstrap refit | Calls the entire standardization and fit again for each date draw; 2,000 draws, seed 1. |
| >5% failed draws | `assessable = failure_fraction <= .05`; exactly 5% remains assessable. |
| Gate logic | G2 requires 200 complete-CLV bets and 20 distinct dates; G3 requires 50 complete-CLV bets per window and positive means. Insufficient blocks pass. Any assessed failure produces fail. |
| Window-1 blend applied to window 2 | Coefficients and window-1 scaling retained unchanged. |

The solver's separation detector is a coefficient-size/singular-Hessian heuristic, not an exact separation proof. It rejects nonconvergence and large coefficients rather than silently penalizing the fit. Exhaustive solver validation was outside these synthetic checks; no new solver or tuning is proposed here.

## Validation and limits

Synthetic checks reproduced late-entry and post-tip-close acceptance in the original. The timestamp patch passed asymmetric-side, missing-timestamp, exact-age-boundary and strict-tip-boundary cases. The existing synthetic self-test passed with the patch, including 2,000-draw bootstrap checks and market-copy insufficiency. All three proposed Python files compile. NFL synthetic checks passed name-map resolution, Last/First ordering, missing names, opaque keys, rejection of mismatched/Boolean lines and ignoring contradictory raw ESPN/GSIS fields.

The broader assembly fixes are static proposals; no end-to-end run on historical inputs was performed. The proposed match gate and invariant failures intentionally stop scoring so mechanics can be repaired first. The numerical checks used an isolated environment with NumPy 2.5.4 and pandas 3.1.1.

Published settlement rules also need a dated resolution before scoring: DraftKings early-exit rules can be asymmetric across over/under, Pinnacle passing stats require an attempt, and missing ESPN minutes are not proof of nonparticipation. See the separate settlement memo. Those policy changes are not silently included in this implementation patch.
