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
