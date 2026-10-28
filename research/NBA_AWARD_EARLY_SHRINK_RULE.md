# NBA awards: early-season shrink toward the pre-season view. Rule written before any result (28 Oct 2026, Sydney)

## Why
- **The live award chances overreact in the first weeks.** After 1-4 games, the Sixth Man leader went from Allen 41% to Dosunmu 33-42% to Mitchell 79%; the Rookie and MVP leaders are also far from the market.
- **Untested window:** the adopted forward simulation (research/nba_awards_replay.py, adopted 14 Oct 2026) was only ever tested from day 21. Before that, it has no evidence.
- **Decision:** TypeSafe 99%: fix awards now; keep the team model's reaction speed, which was already tested.

## Candidate, one only and fixed now
- **w** = min(1, team games so far / 20), where team games = the most games any team has played at the checkpoint.
- **MVP, DPOY, Sixth Man:** p = w x p_sim + (1 - w) x p_pre.
  - **p_sim:** the live forward simulation.
  - **p_pre:** the existing pre-season probabilities (`nba_award_sim.preseason_probs`, last season's leaders).
  - A player in only one of the two gets 0 in the other.
- **Rookie of the Year** (no pre-season model), and any award whose pre-season pool is empty that season: p proportional to p_sim^w, normalised (flattened toward equal chances early).
- **From 20 team games:** w = 1, identical to the live method.

## Test
- **Replay:** research/nba_awards_replay.py with early checkpoints at days 3, 7, 14, 21 and 28 after the season's first game. This is the point-in-time method already used: box scores on or before the checkpoint only, logit weights leave-one-season-out.
- **Seasons:** 2010-2026 end years (2020 and 2021 included as they are in the existing replay).
- **Score:** -log(probability of the eventual winner), floored at 0.002 as in the existing replay.
- **Rows scored:** checkpoints with fewer than 20 team games.

- **Baseline:** the adopted live-site method, the forward simulation (`sim` in the replay). Both are scored on the same rows.

## Gates (all must hold)
1. Mean score over all awards and early checkpoints: the candidate is lower than live, and the 90% season-bootstrap interval of the gain is above zero.
2. No award's mean score worse than live by more than 0.05.
3. The candidate is better or equal in at least 60% of seasons.

## Decision
- **Pass:** TypeSafe decides on adopting it on the live site.
- **Fail:** the live method stays, and award value remains hidden on the Value page until 20 team games (display rule, already planned).
- **No re-runs:** no other weights or shapes are tried on these results without a new dated rule.


## Review (2026-10-28)

**Status: STOP before the replay; no historical gains or gates have been computed.** Reviewed public commit `3c37de5551e3a420f1c626916004ff5e56707878`. The user requires issues to be reported before running and permits rule-text edits, not an unregistered repair of the candidate. This section records the findings; the candidate, checkpoint dates, probability floor and all three gates above are unchanged. There is no pass/fail results file because the run has not started.

### Checks that match the specification

- `season_lines(b, cut)` and `team_table(b, cut)` restrict totals to `date <= cut`. Team games, wins, production and starts at a checkpoint come from that subset.
- `w = min(1, Lc / 20)` uses the largest observed team-game count. This is the stated league-progress clock, not a player-specific evidence weight.
- The linear blend takes the union of player names and gives a missing side probability zero, as specified.
- Rookie flattening is `p_sim ** w`, normalised over positive-probability candidates only. It preserves their ranking and cannot restore a candidate with zero probability or one outside the pool.
- An actually empty preseason dictionary triggers flattening for Sixth Man or another award. A non-empty all-zero dictionary does not; see the blocking findings.
- The registered comparison is **shrink versus sim**, not versus the replay's stats-to-date `live` arm. The exact same simulation map is used in the baseline row and the shrink expression. Freeze `AW_TEMPS=1`; otherwise `sims[0]` may be a different temperature.

### Blocking implementation/interpretation findings

1. **Probability mass and 20-game identity.** In `pipeline/nba_award_sim.py`, a draw with no valid/eligible candidate is skipped, but the accumulator is divided by all draws. Output maps may therefore total less than one, including a non-empty all-zero map. The mixture inherits that missing mass. The flattening branch renormalises it, so even at `w=1` it is not necessarily identical to sim. Synthetic example: sim `{A: 0.2, B: 0.3}` becomes `{A: 0.4, B: 0.6}`. The rule's unconditional identity claim is false for this implementation.

2. **All-zero preseason fallback.** `if not pp` checks dictionary emptiness, not probability mass. Synthetic example: sim `{A: 1}`, preseason `{B: 0}` and `w=0.25` take the linear-mixture branch, yielding total probability 0.25. The intended no-preseason-information fallback is not triggered. Empty and all-zero pools must be distinguished in a preregistered repair; do not silently normalise only the candidate after scoring.

3. **Inherited award-eligibility defect.** `if RULE65 and y >= 2024` applies the 65-game constraint to every award, including Rookie and Sixth Man. The official NBA CBA summary lists MVP, DPOY, Most Improved, All-NBA and All-Defense as the covered honors, not Rookie or Sixth Man. This can create artificial exclusions/missing mass in the primary test. The separate use of all 15+ minute games rather than allowing at most two below 20 minutes is an existing disclosed approximation. Source: [NBA CBA 101, printed page 26](https://cms.nba.com/wp-content/uploads/sites/4/2024/11/2024-25-CBA-101.pdf#page=29).

4. **Replay versus actual early live path.** `boxes()` removes teams with fewer than 40 games in its full input. A three-game current-season input becomes empty, whereas the same first three games survive when loaded from a completed 40-game season and then cut off. `nba_site.awards()` can consequently use preseason or stats-to-date fallbacks early on. The replay's sim arm remains the registered mathematical baseline, but calling it an exact reproduction of the early live display is unverified and presently contradicted by this loader behavior.

5. **The point-in-time claim is too broad.** The logit is correctly leave-one-season-out, but its training set includes seasons later than the held-out season. This is retrospective cross-validation, not a walk-forward estimate available then. In addition, `L` is the eventual maximum team-game count, not necessarily the season length known at the checkpoint, and the 40-game input filter above uses full-season coverage. Prior player-production inputs use last season by default (`AW_RETURN=0`); enabling `AW_RETURN=1` allows older lines. The candidate passes `prev2`, although it is unused with that default. These qualifications must be settled in the rule before any strict historical point-in-time or live-adoption claim.

6. **Exact scoring eligibility cannot come from the current CSV.** It records only rounded `frac`, not `L` or raw `Lc`. Multiplying rounded frac by L is not a safe `<20` test: raw `Lc=20`, `L=66` gives rounded frac 0.303, then 19.998, wrongly including a 20-game row. Preserve raw team games/cutoff/season length or specify an independently validated exact reconstruction before running. The script's printed method means also include preseason `ck=-1` rows and are not the registered paired gate statistic.

### Required next decision, before results

Do not execute the hour-long replay on this specification. First settle and register the exact structural repairs (both baseline and candidate where applicable), raw checkpoint-count provenance, and whether the experiment is explicitly retrospective LOSO or a separate walk-forward test. Unit-mass, empty/all-zero-pool, award-eligibility, source-cutoff and 20-game identity checks should pass before any gains are computed. A repair is not permission to alter the 20-game schedule, blend shape, thresholds or gates after results.

Once these prerequisites are resolved, apply the existing three gates exactly as written: paired shrink/sim rows only, preseason excluded, a fixed seed and 10,000 whole-season bootstrap draws, award-level differences, and seasons better **or equal** (ties count under this registered rule). Define central 90% bootstrap endpoints and missing-cell handling before running. No extra strict-positive-season gate or new 5% probability floor is introduced into this test by this review.

Structural checks used temporary synthetic data only. No historical award replay, candidate scoring or live adoption occurred. Later tasks in the user's ordered list remain pending until this stop is resolved.


## Pre-run structural amendment (2026-10-28)

The user has now asked GPT to solve the pre-run blockers and complete Task 1. This amendment is written **before any historical probabilities, gains or gates are inspected**. It supersedes the earlier stop status only once the validation checks below pass. The candidate formula, 20-game denominator, five checkpoint days, 0.002 scoring floor, seasons, 0.05 award tolerance, 60% better-or-equal requirement, and three original gates are unchanged. No 5% candidate/betting floor is added here.

- Repairs are behind an explicit `replay=True` argument, enabled by `AW_EARLY=1`. Existing live/default behavior is unchanged. There is no live adoption or merge in this task.
- Both research sim and shrink use probabilities averaged over **valid simulated award outcomes**, rather than counting no-winner draws as missing probability. Invalid-draw counts are saved. An entirely empty baseline is a validation failure, not a row silently dropped or assigned a new distribution. Duplicate normalised names have their probability mass combined.
- In the repaired research simulation, the 65-game condition applies only to MVP and DPOY. Counting uses 20+ minute games plus at most two 15-20 minute games. The existing season-total simulation and half-game rounding tolerance remain; injury/grievance exceptions are not inferred from hindsight. ROY and Sixth Man retain their existing candidate-pool share/bench restrictions, without an invented 65-game requirement.
- An empty or all-zero preseason map means missing preseason information and invokes the registered flattening branch. A nonzero invalid-mass map fails validation. At 20+ team games, return the exact sim dictionary, so identity is literal. Every non-empty scored research distribution must be finite, nonnegative and sum to one.
- The research loader uses the explicit canonical NBA franchise list to exclude exhibitions, rather than filtering teams using their eventual number of games. Completed prior/training season lines exclude the NBA Cup final using the existing final-identification function; raw current-season checkpoint prefixes are not selected using later games. All registered opening checkpoints precede the Cup final. Rookie status for checkpoint players uses appearances in earlier seasons only. Current checkpoint totals still use `date <= cutoff`.
- The opening schedule horizon is 66 games for end-year 2012, 72 for 2021, and 82 for the other test seasons, including the opening weeks of 2020. These were the schedules known then; no eventual shortened-season count enters an opening forecast. Sources: [2011-12 official schedule](https://pr.nba.com/nba-2011-12-game-broadcast-schedules/), [2020-21 official format](https://official.nba.com/nba-announces-structure-and-format-for-2020-21-season/).
- Leave-one-season-out fitting is retained exactly as requested. It excludes the held-out season but includes later seasons. Results are therefore described as a **retrospective LOSO comparison**, not a historical walk-forward claim. The baseline is the **repaired research sim**, not a claim that the existing early live fallback path has been reproduced. The raw `live` arm is diagnostic and excluded from all three gates.
- Freeze one fresh process with `AW_EARLY=1`, `AW_TEMPS=1`, `AW_RETURN=0`, `AW_CURTEAM=0`, `AW_LATE_ONLY=0`, `AW_PRE_ONLY=0`, `AW_RULE65=1`, `AW_SIMS=300`, and the existing deterministic simulation seed. All other simulator/logit parameters stay at their defaults. Input-file hashes and configuration are saved before the run.
- Save raw `team_games`, `L`, unrounded `frac`, cutoff date and checkpoint day. Score exactly paired sim/shrink rows with `ck >= 0` and raw `team_games < 20`; verify `frac * L` agrees with the raw count. No rounded reconstruction is used.
- Gate 1 uses the original overall mean across eligible award/checkpoint rows. Resample whole seasons, preserving all their rows; when cell counts differ, recompute the row-weighted mean within each resample. Use 10,000 bootstrap draws, seed **20261028**, and the central 90% interval (5th/95th percentiles). Gate 2 and Gate 3 remain exactly as originally written; ties count for Gate 3. All 17 seasons, four awards and five checkpoint cells must be present before eligibility filtering; missing/duplicate/unpaired cells fail validation.
- Report per-award and per-season scores/gains; favourite said/won by award/checkpoint; floor hits; support and probability-mass diagnostics. No thresholds or candidate changes after results. Pass/fail is reported for the user's adoption decision, without deploying anything.

Synthetic validation covers future-box invariance, legacy/default identity, award eligibility, unit mass, empty/all-zero preseason fallback, missing-side-zero union, exact 20-game identity, exact scoring boundaries, pairing, ties and deterministic bootstrap behavior. The eight new tests pass before the run; the full suite is also run before committing the experiment specification. Any substantive new validation defect stops scoring and is reported, rather than tuned against results.

Pre-run verification: `python -m unittest discover` ran 93 tests successfully (one existing skip). The test directory is now discoverable with that exact command; a test-only SQLite handle is closed before Windows cleanup. All 24 raw input files are hashed in `nba_award_early_shrink_inputs.json`. No historical result file exists at this freeze.


## Results (2026-10-28)

**FAIL — all three registered gates fail. No adoption and no parameter/shape changes.** Run from pre-result specification commit `904b13e`; scored by the scorer frozen in that commit. This compares shrink with the repaired research sim, not the unchanged live display.

- Sample: 340 paired award/checkpoint cells, 17 seasons. Mean NLL: sim 2.603239; shrink 2.545207. Gain (sim minus shrink) +0.058033.
- **Gate 1: FAIL.** Mean gain +0.058033, but central 90% whole-season bootstrap interval is [-0.066546, +0.191866], so its lower endpoint is not above zero. Seed 20261028; 10,000 draws.
- **Gate 2: FAIL.** Sixth Man gain is -0.381157 (a loss of 0.381157), exceeding the allowed 0.05 loss.
- **Gate 3: FAIL.** 7 of 17 seasons are better or equal (41.18%), below 60%.

| Award | Sim NLL | Shrink NLL | Gain |
|---|---:|---:|---:|
| 6MOY | 2.955224 | 3.336381 | -0.381157 |
| DPOY | 3.378274 | 2.969280 | +0.408994 |
| MVP | 2.018474 | 2.005373 | +0.013100 |
| ROY | 2.060986 | 1.869794 | +0.191193 |

Full per-season gains, favourite said/won at every award/checkpoint, floor-hit counts and diagnostics: `research/nba_award_early_shrink_results.json`. Paired rows: `model/replay/nba_awards_early_shrink.csv`. These are the only registered run and settings; no exploratory alternative was tried after inspecting the result. The user decides any live changes separately.
