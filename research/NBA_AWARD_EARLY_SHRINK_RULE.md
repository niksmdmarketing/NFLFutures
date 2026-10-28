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
