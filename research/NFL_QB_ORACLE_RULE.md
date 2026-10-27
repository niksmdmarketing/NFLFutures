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

## Amendment (27 Oct 2026, 14:23 Sydney), after GPT's review and before any gains: all of GPT's changes accepted
The first full run was stopped during 2015, before any gain was computed; its partial rows were discarded. Nothing below was chosen with sight of a QB-adjusted score.

**1. Starter identity: official first-play lineup, not the first dropback.**
- Labels are in research/nfl_qb_starter_labels.csv, built by research/nfl_qb_starters.py.
- **2016-2025:** the QB (players.csv position QB) on the field for the team's first offensive scrimmage play, from nflverse play-by-play participation. This is the gamebook definition of a starter. If two QBs are listed on that play, the one who took the first dropback is used.
- **2013-2015** (no participation data): the majority of three labels:
  - first dropback;
  - games.csv QB;
  - the QB with most offensive snaps (PFR snap counts).
  The first dropback breaks a three-way split.
- **Audit:** 6,814 team-games; the chosen label is missing for none.
  - The chosen label differs from the first dropback in 11 games: wildcat or trick plays (Cribbs, Beckham, Wilson, Taysom Hill), and Josh Allen's one-snap starts in week 18 of 2024 and 2025.
  - It differs from games.csv in 67 games, 38 of them in 2024. The first-play lineup matches the official facts GPT cited: Tua back in week 8 of 2024; Mariota started week 4 of 2025 and Daniels returned in week 5; Newton did not return in 2019.
  - One known residual: 2014 week 17 NE is labelled Garoppolo by majority, although Brady started and played the first half. It is left as the fixed rule produced it.

**2. Interpretation.** pergame is an **oracle starter-information benchmark under this fixed QB adjustment**, not a guaranteed ceiling on news-based QB modelling.
- It uses future injuries, rest, rookies and benchings.
- QB values are still imperfect, λ is fixed, and the rating anchor may be imperfect.
- A badly specified adjustment can make even perfectly observed starters hurt.
- A negative or null result rejects this implementation, not the relevance of QB availability.

**3. Frozen reference and values.**
- The reference QB (most dropbacks through week w) and all QB values are fixed once per checkpoint, using only pre-cutoff play-by-play.
- QBs without enough pre-cutoff data (rookies, unused backups) get the frozen low-sample value; later careers are never used.
- The same reference and values are used in next and pergame. Future starter identities are the only oracle input.

**4. Embedded QB performance.** The team rating already reflects the mixture of QBs who played before the checkpoint, so "starter minus reference" may double-count or use the wrong anchor. This approximation is common to both arms.

**5. Playoffs.**
- Division and make-playoffs are settled before the simulated playoffs.
- The regular-season draws are identical across arms: same seed, shapes and order; the QB shift changes values, not draws.
- Conference, Super Bowl and No. 1 seed comparisons are omitted, because the arms treat playoff ratings differently.

**6. Scoring.**
- As written: mean team-level binary log loss within each of the six cells, cells equal per season, seasons equal, whole paired seasons resampled.
- **v5-core at λ = 0.5 is the sole primary decision.** v4-core and λ = 1.0 are diagnostics and cannot rescue a failed primary.
- Probabilities are clipped to [0.001, 0.999].
- **Monte Carlo noise** is reported as the A-minus-B difference in G1, to compare with 0.001. Seed-set agreement checks Monte Carlo stability, not independent replication.
- One-sided 90% upper bounds are added.
- Each gain is reported for division and make-playoffs separately.

**7. Materiality.** 0.001 is a prespecified minimum for allocating more research effort, not a profitability threshold. It is comparable with v5's +0.0029 because the scoring, checkpoints and weighting match the v5-promotion primary.

**8. Revised decision** (v5-core, λ = 0.5, average of A and B; replaces the earlier decision section):
- **Build and separately test the news-based per-game input** if G1's lower bound > 0, G1 ≥ 0.001, G2's lower bound > 0, and neither market's G1 is negative.
- **The simpler next-start approach remains a candidate** if G1 passes those tests but G2's lower bound ≤ 0.
  - This does not validate today's live starter selection, because next was given oracle information. G3 is examined with it.
- **Stop this specified adjustment as a research priority** if G1's one-sided 90% upper bound is < 0.001. This is not a claim that all QB work for futures is disproved.
- **Inconclusive / insufficient for this development step** otherwise, including any lower bound crossing zero. Not proof of no effect.
- **Inconclusive** if seed sets A and B disagree on any gate. No favourable seed or sensitivity is picked, and there is no rerunning under this rule.
- Nothing here authorises a live model change.

## Outcome (27 Oct 2026, Sydney): build and separately test the news-based per-game input
Run: research/nfl_qb_oracle_test.py; results in research/nfl_qb_oracle_results.json; rows in research/nfl_qb_oracle_rows.csv.gz; labels in research/nfl_qb_starter_labels.csv.

- **Identity check:** the none arm reproduced all 4,992 stored rows exactly.
- **Seed sets:** A and B agree on every gate. Monte Carlo noise in G1 (A minus B) was 0.00007, far below 0.001.

**Primary result** (v5-core, λ = 0.5, average of A and B; mean log-loss gain, one-sided 90% bounds):

| Gain | Mean | Bounds | Seasons better | Division | Make-playoffs | 2020-25 |
|---|---|---|---|---|---|---|
| G1 (none - pergame, the oracle benchmark) | +0.0063 | +0.0035 to +0.0092 | 11/13 | +0.0055 | +0.0071 | +0.0128 |
| G2 (next - pergame) | +0.0058 | +0.0037 to +0.0081 | 10/13 | +0.0046 | +0.0071 | +0.0114 |
| G3 (none - next, the live whole-season logic with oracle next-start knowledge) | +0.0005 | -0.0016 to +0.0025 | 8/13 | | | |

- **G1 by cell:** division wk4 +0.0078, wk9 +0.0052, wk13 +0.0037; make-playoffs wk4 +0.0104, wk9 +0.0079, wk13 +0.0032.
- **G1 by season:** 2013 -0.011, 2014 +0.005, 2015 +0.006, 2016 +0.000, 2017 +0.001, 2018 -0.004, 2019 +0.008, 2020 +0.012, 2021 +0.021, 2022 +0.013, 2023 +0.006, 2024 +0.011, 2025 +0.015.
- **Diagnostics** (cannot change the decision):
  - λ = 1.0: G1 +0.0103 (lower bound +0.0047), G2 +0.0106.
  - v4-core, λ = 0.5: G1 +0.0059 (lower bound +0.0033), G2 +0.0051.
  - v4-core, λ = 1.0: G1 +0.0099.

**Reading:**
- Knowing each game's starter and applying the gap only to those games improves in-season division and make-playoffs forecasts by about twice v5's whole-model gain over v4 (+0.0029).
- The gain is largest after week 4 and in recent seasons, 2025 included.
- The live whole-season shortcut captures almost none of it (G3 ≈ 0), so per-game handling is where the value is.
- **Caveat** (from the rule): the oracle includes planned changes (rookies taking over, benchings) and returns from injury, not just injuries. News on expected absences will capture only part of G1. The news-based input therefore needs its own rule and test (GPT's 2018-2025 reported-absence list is the planned input).
- Nothing live changes from this result.
