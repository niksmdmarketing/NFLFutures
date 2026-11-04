# NFL QB ESPN dated shadow review

5 November 2026, Sydney. Reviewed main implementation 6dabc41 (checkout afe9d2f). Live v4 unchanged.

## Requested checks
- ESPN/GSIS matching: captured the current ESPN feed and latest NFLverse depth chart (latest depth timestamp 4 November 2026 07:01:51Z). All 62 QB feed rows matched one valid GSIS ID within their team; no unmatched QB rows in this capture. This checks this snapshot, not all possible future names. Hardened initial spacing, accents/suffixes, numeric depth ranks, invalid IDs, and ambiguous matches; keyed official/ESPN status by team plus ID. No fuzzy matching. Raw source bytes and name audit remain private.
- Already-missed games: the no-date pool uses L >= m+1, and residual L-m, so it conditions correctly and subtracts once. Reserve-status restriction means total absence length at least four, not four extra games or verified IR-placement eligibility. Tests cover a bye, return/reset, IR/PUP and exhausted pools. Future ESPN dates are remaining calendar times; m is not subtracted a second time.
- No episode: exact v4 ratings vector and no adjustments. A 64-draw paired simulation using all 272 scheduled 2026 regular-season games matched all eight returned outputs bit for bit. Added a guard for episodes with no remaining regular-season games. When another team does have an episode, opponents' futures can legitimately change; no-episode identity is not a promise that all such teams' futures are unchanged.

## Material review finding
The shadow removes v4's whole-season QB adjustment and applies replacements via regular-season adj_sims only. Playoff games use the restored reference-QB rating, with no dated adjustment. Season-ending injuries therefore do not cover every remaining playoff game. The dated amendment and output flag playoff_injury_adjustments=false disclose this. This is NOT fixed by guessing playoff return dates in the review. Conference/Super Bowl forecasts remain incomplete for that use; live adoption is not supported.

Other cautions: the lognormal allows earlier-than-median returns, contrary to the original disclosure; the reference QB may cease to be the intended starter after a long absence; the backup selected by the rule may himself be unavailable; incomplete PBP can corrupt absence counts. Checkpoint bootstraps reuse season outcomes and are not independent season-level evidence.

## Changes and verification
Original rule preserved above its amendment section; appended 5 November review amendment. Shadow version 1-review-20261105 is identifiable; historical snapshots stay unchanged. No changes to the live rating calculation or simulator. Twelve QB-shadow unit tests and six simulator logic tests pass; the paired no-episode simulation passes.

Private evidence: outputs/shadow_review_20261105/nfl_matching_audit.json, espn_nfl_injuries.json, depth_charts_2026.csv, nfl_no_episode_simulation.json. These raw files are not committed. Review fixes are on a branch, not merged or deployed.
