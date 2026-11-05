# NBA/NHL award evaluation: independent review, 5 November 2026

Reviewed public 5782875 as included in f5fcc9c. Original models/evaluation JSON untouched. Findings first; reproductions below.

## P2 — fixed pool sizes are not consistently the forecast's candidate pool

research/nba_nhl_award_eval.py:10,37-38 uses fixed n and treats p_winner > 0 as pool membership. NBA simulate() first takes up to 3*n candidates and averages probabilities over changing top-n simulated finishes. Its returned probability dictionary can have more than n positively weighted players.

Original-function witness: a ROY simulation with 30 candidate players produces positive probabilities across the larger set, summing to 1, while the evaluation baseline uses n=15. Assigning 1/15 uniformly to 30 possible winners would sum to 2. That is not a coherent uniform forecast over this returned pool. A valid per-simulation uniform baseline would instead retain each candidate's selection/eligibility frequency; a uniform baseline over the initial pool would use its actual size. State which is intended.

The fixed n can make the NBA comparator harder inside the selected support, so this does NOT establish that NBA skill disappears. But zero simulated probability is not the same information as explicit candidate exclusion, and the direction is not a substitute for a correctly defined baseline. Save n_pool and winner membership independently of p_winner; do not infer both from the eventual winner's probability.

For NHL voted awards I inspected all 432 relevant pool formations using the frozen historical tables and original pool code (no fitting): Hart 26, Norris 12 and Vezina 10 match throughout. Calder has 14 or 15 candidates in 7/108 checkpoints, rather than 16. The winner-in-pool flag agrees with positive probability across those 432 checks. So the NHL objection is specific, not a blanket claim about every pool.

Correcting those Calder pool sizes moves its baseline loss from reported 2.836 to **2.83147**, against model **1.67470**. Its overall/third loss gates still pass. Art Ross/Richard's 15 refers to a truncated published list, whereas the underlying simulation runs the full field; describe that scope and retain explicit membership, particularly for zero-probability/zero-count cases. The summary replay CSVs alone do not retain every candidate list needed to audit all such cases.

## P2 — NHL Vezina T1.0 is not production-equivalent late in the season

pipeline/nhl_awards.py:439 applies temperature 0.6 when the live builder's MAX team games reaches 2/3 of 82. The new evaluation selects T1.0 for every checkpoint. current_chances() does not apply that temperature internally; it is applied by its caller, so the replay's T1.0 row cannot stand in for the late live version.

Reproduction: select existing T0.6 rows at the SAME max-team-games trigger recovered from saved team snapshots, and T1.0 otherwise. This changes 34/108 Vezina rows; no probability model is rerun. Loss becomes **1.71437** rather than reported 1.734, baseline **2.55614**; favourite said 0.51084 versus won 0.43519, gap 90% [-0.01716, 0.18007]. It still passes the original proxy gates. Correct the method/figures; do not claim this correction proves a new model gain.

Use the actual production trigger, not simply median frac >= 2/3: replay frac uses median team games, while production uses the maximum. NBA sim matches the selected production simulation family by source inspection; its leave-one-season-out fitting remains historical development validation, not a strict forward-trained replay.

## P2 — the attachment layer rewrites measured evidence on a failure

pipeline/award_eval.py:23-24 replaces a failing award's measured log_loss with max(model loss, baseline loss). A synthetic evaluation with true model loss 0.2, baseline 1.0 and pass=False is attached as log_loss=1.0. Probabilities are unchanged, but the published statistic is no longer the measured one.

All ten current entries pass, so this does not alter their present published figures. It is a latent reporting defect. Preserve the true loss and failure reason; have the consumer explicitly honor pass=False. The reviewed private Value policy checks ll < baseline but not pass, explaining the workaround. Update consumer and attachment together: removing only the clamp could let a calibration-failing model through. Keep compatibility with NFL evaluations that do not have a pass field (deny an explicit false, then apply the existing loss comparison).

## What reproduces / what I agree with

- Running evaluate() independently reproduces ALL TEN committed JSON entries exactly, including season bootstrap intervals, third-of-season gates and pass flags. There is no arithmetic discrepancy against the written implementation.
- The model and baseline use the same clipped penalty for purported out-of-pool winners, as specified; they are not silently dropping those misses. The issue is how membership/pool size is established, not a mismatch with that declared penalty.
- The favourite uncertainty code resamples whole seasons, appropriately preserving repeated checkpoints within a season. It tests whether overconfidence was demonstrated, not whether calibration has been proven. Wide intervals such as DPOY's remain weak evidence.
- Uniform is a weak benchmark. No Australian prices were added by this evaluation; beating this comparator is not a market-edge or profitability result.
- The corrected Calder and production-method Vezina checks still pass. These findings do not establish that all ten awards should fail; they establish that the blanket production-equivalent evaluation claim needs corrections and better metadata.

## Reproduce

Original figures: import research/nba_nhl_award_eval.py and call evaluate(), writing to a separate output path. Captured result is research/review_20261105/award_eval_reproduced.json; original JSON was not overwritten.

- `python research/review_20261105/test_later_work_review.py`: original NBA pool, NHL variable-pool and attachment witnesses.
- `python research/review_20261105/reproduce_diagnostics.py <output-directory>`: production-trigger Vezina selection from existing rows and saved snapshots; also NBA diagnostic review.
- `python research/review_20261105/nhl_pool_probe.py <frozen-published-nhl-data-dir> <output-directory>`: all 432 voted-award pool checks, without fitting award weights. Local published inputs were frozen public tree 18fac281801dd08b28bd03d269aef01d9bcdc8b3 from the earlier NHL review, with hashes already archived privately/local. Source/replay fingerprints accompany this review.

Recommendation: correct the evaluator and evidence handling on a review branch; keep actual probabilities/live models unchanged. Publish explicit method and pool metadata and retain the development/weak-baseline qualification before treating these as ten fully production-equivalent validations.
