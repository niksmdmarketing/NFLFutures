# NFL futures: does knowing each game's starting QB improve the forecast? A perfect-knowledge replay. Rule fixed before any code or results (27 Oct 2026, Sydney)

Status: **final (27 Oct 2026, 14:06 Sydney).** The user asked to run it now ("Let's do it"), before GPT's review arrived. Any point GPT raises afterwards is reported beside the result; a change would need a new dated rule, with no rerunning under this one. Nothing had been run beyond the identity check (no gains computed) when this was committed. Asked by the user ("Start your task", 27 Oct 2026). TypeSafe chose this as the next logic improvement (75%, against props game-script 11% and game models 12%).

## Why
- **The live QB layer** (pipeline/ratings.py, team_ratings):
  - the reference QB is the team's main QB so far, i.e. the one with most dropbacks this season;
  - the expected starter is QB1 on the latest depth chart, or QB2 if QB1 is listed Out or Doubtful;
  - if they differ, the team's rating moves by 0.5 × (expected starter value - reference value) for **every remaining game**, however long the absence is.
- **The replay cores** tested this week (research/NFL_V5_PROMOTION_RULE.md) have no QB layer at all, so they don't test it.
- This test measures the **ceiling**: how much a perfect answer to "who starts each remaining game" would improve division and make-playoffs forecasts. It also measures whether the live whole-season logic captures much of that ceiling.
  - If even perfect knowledge adds little, the news-based per-game input is not built.
  - The news-based version would get its own rule later.

## Definitions
- **Starter of a game:** the QB who took the team's first dropback in that game. This is pipeline/nfl_qb_backtest.py's starters(), and it is known before kickoff in nearly every case. Mid-game injuries are not anticipated: the game counts as the starter's.
- **QB values:** ratings.qb_values on play-by-play known at the checkpoint, i.e.
  - this season through week w;
  - the previous two seasons, with the frozen weights;
  - QBs below the low-sample threshold get the low-sample value.
- **Reference QB:** the team's QB with most dropbacks this season through week w, as in the live layer.
- **Gap for team t in game g:** value(starter of g) - value(reference of t). It is 0 when the starter is the reference, or when either is missing.

## Arms
Each arm is applied to both replay cores, built exactly as in research/nfl_v5_promotion_test.py:
- **v5-core** (primary: the in-season betting number);
- **v4-core** (secondary).

The three arms:
1. **none:** no QB adjustment. This must reproduce the stored v5-promotion rows exactly (identity check), using the same seeds and shapes.
2. **next (live logic, perfect knowledge of the next start):** the gap for the team's first unplayed regular-season game after week w, applied to all its remaining regular-season games and to its playoff rating.
   - This is the live whole-season rule, given the right answer for the next game. It removes depth-chart and report errors, so it isolates the "whole season" assumption.
3. **pergame (oracle):** each remaining regular-season game uses that game's own gap. The playoff rating uses no QB adjustment, because the starter of a simulated playoff game is not observable.

Mechanics:
- **Scale.** Ratings are R = scale × (base - mean); the QB shift is scale × λ × gap, as in live.
- **next:** the shift is added to the team's rating before simulating.
- **pergame:** home shift minus away shift is added to that game's simulated margin, through a new research-only simulator option, a per-game margin adjustment column. When the column is absent the simulator is unchanged, so frozen v4 is untouched.
- **λ = 0.5** (the live value) is primary.
- **λ = 1.0** is a sensitivity only. Disclosed exposure: the existing game-level QB test (model/qb_backtest.json, 2019-2025) gave a free slope of 0.93 (se reported there).
- Re-centring of ratings to mean zero happens before the QB shift, as in live.

## Seasons, checkpoints and simulation
- Seasons 2013-2025; checkpoints after weeks 4, 9 and 13; results after week w masked.
- Each team's remaining starters come from actual 2013-2025 play-by-play. Games are not yet played at the checkpoint, so this is deliberately future information: the test is a ceiling, not a deployable forecast.
- The correct playoff format (6 seeds to 2019, 7 from 2020); no home edge at neutral sites; sweep option off.
- **Monte Carlo:** two seed sets, A (1000·Y + w) and B (7000·Y + w), 5,000 simulations each. Every arm uses the same seed and array shapes, so the draws are paired by construction.
  - Probabilities are averaged over A and B, then clipped to [0.001, 0.999].
  - Every gate is computed on A and B separately; if they disagree on any gate, the result is inconclusive.

## Scores
- **Primary:** mean team-level binary log loss over six cells: division winner and make-playoffs after weeks 4, 9 and 13. Cells are equally weighted within a season; seasons equally weighted.
- **Gains** (positive = the second arm better):
  - G1 = none - pergame (the ceiling);
  - G2 = next - pergame (per-game over whole-season logic);
  - G3 = none - next (what the live logic adds with perfect next-start knowledge).
- **Bootstrap:** whole seasons, 10,000 draws, seed 20261027, one-sided 90% lower bound.
- **Also reported:**
  - gains by market and checkpoint;
  - by season;
  - leave-one-season-out;
  - 2020-25 subgroup;
  - the number of team-checkpoints with any non-zero gap and their share of the gain;
  - calibration slopes;
  - No. 1 seed, conference and Super Bowl at the same checkpoints (descriptive; the pergame arm has no playoff QB adjustment).
- **Identity check:** the none arm against nfl_v5_promotion_rows.csv.gz, all 13 × 3 × 32 × 2 seed sets. Any mismatch stops the run before gains are computed.

## Decision (v5-core, λ = 0.5; A and B must agree)
- **Build the news-based per-game input** if G1's lower bound > 0, G1 ≥ 0.001, and G2's lower bound > 0. The per-game logic is then both valuable and better than the whole-season shortcut.
- **Keep the live whole-season logic; no per-game build** if G1's lower bound > 0 and G1 ≥ 0.001, but G2's lower bound ≤ 0. Most of the ceiling is captured already; the per-game build isn't worth it.
- **Stop QB work for futures** if G1's lower bound ≤ 0 or G1 < 0.001. Even perfect knowledge adds little at this checkpoint spacing.
- **Inconclusive** if A and B disagree. No retuning and rerunning under this rule.
- v4-core results and λ = 1.0 are reported but do not change the decision.
- Nothing here changes the frozen v4 display or the live v5 shadow. Any live change needs its own rule, tested on its own evidence: the news-based input carries uncertainty about absence length that the oracle doesn't.

## Disclosed exposure
- **Frozen QB-value settings:** w1, w2, alpha and the low-sample threshold were set on overlapping seasons.
- **λ = 0.5:** chosen in the earlier game-level test on 2019-2025.
- **Cores:** the v5 core's hyperparameters were selected on 2013-2025 replays.
- **This week:**
  - the v5-promotion rows (the none arm) and their results were seen;
  - no QB-adjusted futures replay has been computed;
  - the failed QB availability episode work (research/NFL_QB_AVAILABILITY_RULE.md) inspected 2013-2025 injury episodes but computed no forecast scores.

## Note before the full run (27 Oct 2026)
- **Identity check passed:** the none arm reproduced all 4,992 stored v5-promotion rows exactly (research/nfl_qb_oracle_identity.json).
- **Gap audit** (research/nfl_qb_oracle_audit.csv): about 25% of remaining team-games have a starter other than the reference QB, at every checkpoint. A by-name check of 2025 week 4 showed genuine changes:
  - injuries and returns;
  - rookies taking over;
  - benchings.
- The oracle therefore includes planned changes (rookies, benchings), not just injuries. That may overstate what injury news alone can deliver, and is to be noted in the reading.
