# NFL futures: QB-enabled replay and game-by-game QB availability. DRAFT rule for review before any code or results (26 Oct 2026, Sydney)

Status: **draft, sent to GPT for review.** Nothing has been run. Research only; live v4 stays frozen through 2026.

## Why
- Every historical futures replay so far turned v4's QB layer off, so it tested a QB-free core, not the live model.
- **The live QB layer** (pipeline/ratings.py):
  - QB values come from a ridge regression of EPA per dropback (QB, offence and defence effects; current season plus two previous seasons, weights 1 / 0.2 / 0.3), in points per game (× 36 dropbacks). Low-sample QBs get a pooled value.
  - When the expected starter differs from the team's most-used QB this season, the team rating moves by 0.5 × (expected value - usual value).
  - That shift applies to every remaining game and the playoffs, so a one-week absence moves the whole season, and the starter's return is never modelled.
- TypeSafe chose to keep the existing QB values and apply them game by game with an expected absence length (98%), over building new QB ratings (0%).

## Data and timing (checked 26 Oct 2026)
- **nflverse weekly rosters** (weekly_rosters/roster_weekly_YYYY.csv): every team's roster each week with a status (ACT, RES = reserve list such as injured reserve, INA, etc.), available for every season tested. The detailed reserve codes (e.g. R01, R48) exist only in recent seasons, so only the status is used.
- **nflverse play-by-play:** who actually took each team's dropbacks in each game.
- **Information at checkpoint w** (after all week-w games, the paper-bet checkpoint): play-by-play through week w and the week-w weekly roster. The week w+1 injury report is not yet published, so it is not used.

## Arms (identical except the QB treatment)
All arms use:
- v4 walk-forward ratings as in research/nfl_futures_diagnosis.py (v4wf, scale 0.89);
- the frozen simulator: tau 5.0, sigma 11.37, home edge 1.8, neutral sites no edge, correct playoff format, sweep off;
- 10,000 simulations with the same seeds;
- no pressure layer (it needs weekly pressure data this replay doesn't have).

1. **Base:** no QB layer (the existing replay).
2. **A, the live logic:**
   - Usual QB = the most dropbacks for the team in season Y through week w.
   - Expected starter = the QB with the most dropbacks in the team's week-w game. If the usual QB played week w, he is the expected starter.
   - If the expected starter differs from the usual QB, add 0.5 × (value(expected) - value(usual)) to the team's rating for the whole remaining season and playoffs.
   - QB values come from qb_values on play-by-play through week w and the two previous seasons.
3. **B, the candidate, game by game:**
   - If the usual QB played in week w: no adjustment.
   - If he did not, his return is drawn independently in each simulation from an empirical absence distribution.
     - The distribution is set by his status at week w (RES or not) and the consecutive games already missed (1, 2, 3, 4+).
     - It is fitted walk-forward only on seasons 2006 to Y-1: usual starters, defined the same way, after week 4 of each season.
   - For each remaining game the starter is out in that simulation, the team's margin in that game moves by 0.5 × (value(replacement) - value(usual)). Replacement = the expected starter as in A.
   - Playoffs use the starter if he has returned by the end of the regular season in that simulation; otherwise the replacement.
   - λ = 0.5 is kept, so A and B differ only in timing.

## Markets, checkpoints, seasons
- Division winner and make-playoffs after weeks 4, 9 and 13: six cells, as in the paper-bet rule. Conference and Super Bowl are reported secondarily.
- Seasons 2013-2025.
- Also reported: the number of team-checkpoints where the usual QB missed week w, and the results on that subset.

## Scores
- Per season, the six cells averaged equally; seasons averaged equally.
- Division: multi-class log loss of the winner. Make-playoffs: binary log loss. Probabilities are clipped to [0.001, 0.999].
- Season bootstrap, 10,000 draws, seed 20261026; one-sided 90% lower bound.
- **Comparisons:**
  - B vs A (primary: does modelling absence length help?);
  - A vs Base (does the live QB layer help at all? diagnostic);
  - B vs Base (reported).

## Gates (B vs A; all must hold)
1. Primary gain positive with one-sided 90% lower bound > 0.
2. Positive gain in at least 60% of the seasons in which any usual QB missed a checkpoint week.
3. No cell worse than A by more than 0.002.
4. Primary gain positive in 2020-25.

## Decision
- **Pass:** a shadow version of v4 with game-by-game QB availability, archived live beside v4. Promotion only by a later decision with forward evidence.
- **Fail:** recorded; v4's QB logic stays.
- The A vs Base result is reported either way: if the live QB layer hurts, that is a finding in itself, and any change needs its own rule.

## Disclosed exposure
- The 2013-2025 QB-free replay and its calibration were inspected this week.
- v4's simulation settings were tuned on 2022-2025.
- λ = 0.5 was set in the live model without a historical test.

## Questions for review
1. Is the empirical absence distribution (by RES status and games missed, walk-forward) right, or should a simpler fixed rule be used (e.g. not RES: 1 more game; RES: rest of season)?
2. Is "most dropbacks in the week-w game" a reasonable stand-in for the expected next starter, given the week w+1 injury report is unknown at the checkpoint?
3. Should λ stay 0.5, or should the full value difference (1.0) be used in B, since B already handles duration?
4. QB changes are rare, so most team-checkpoints are unaffected. Are the gates (all-team scores plus seasons-with-changes) appropriate?
5. Benchings, trades and rookies taking over are mixed in with injuries. Is that acceptable for a first test?
