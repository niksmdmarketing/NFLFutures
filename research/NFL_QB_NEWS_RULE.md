# NFL futures: does reported QB absence (news only) improve the forecast? Rule fixed before any code results (27 Oct 2026, Sydney)

Status: **draft.** The injured-reserve and PUP minimums are awaiting GPT's season-by-season table, and GPT's review is pending. Nothing has been run.

## Why
- **The perfect-starter benchmark** (research/NFL_QB_ORACLE_RULE.md) gave v5-core +0.0063 log loss (lower bound +0.0035) when each remaining game used its actual starter.
- **The live whole-season shortcut** captured almost nothing (+0.0005).
- **This test** asks how much is reachable using only what was reported at the time: the expected length of a starter's absence.

## Input: what was reported, and when
- **Source:** GPT's list of 2018-2025 starter absences (research/qb_news/gpt_qb_reports_2018_2025.csv, 120 cases). It covers injuries and suspensions where the regular starter missed, or was first reported as likely to miss, two or more consecutive starts. Each case has its first report and later revisions, with publication dates and exact wording.
- **Coding:** every report is coded from its wording alone by research/qb_news/code_reports.py, a fixed mapping applied mechanically (outcome columns are never read), into research/qb_news/qb_reports_coded.csv.
- **The mapping:**

| Wording | Code | Expected further absence, counted from the report date |
|---|---|---|
| Season-ending, rest or remainder of the season, out for the year, won't return this season, return next season | S | All remaining games |
| "N to M weeks" (or "N-M weeks is the minimum": +2 weeks on top) | W | Games within N to M weeks |
| "At least" or "a minimum of" N weeks | W | N to N+2 weeks |
| Months | M | Weeks = months × 4.35 |
| Suspended N games; "sit for the remaining N games" | G | N games |
| "At least N games" | G | N to N+2 games |
| "Out until at least week K" | UNTILWEEK | All games before week K to week K+2 |
| Placed on injured reserve | IR | Season's IR minimum to minimum + 2 games. Where the season's rules give no return path without a designation, rest of season (values from GPT's table) |
| Start of season on PUP | PUP | The season's PUP minimum to minimum + 2 games |
| Week to week, multiple or several weeks or games, multi-game absence, "miss some time", "isn't season-ending" | G | 2 to 4 games ("isn't season-ending": 1 to 4) |
| Cleared to practice, play or for contact | C | 0 to 1 games |
| Explicit short-term wording: day to day, questionable, doubtful, ruled out, concussion protocol, status in doubt… | D | 1 to 2 games |
| No usable duration: no timeline, no timetable, indefinitely, no update… | U | 1 to 2 games as a first report; ignored as a revision |

- **Same-day reports:** when several reports share a date, the last listed applies.

## Arms
Built as in the oracle replay: v5-core (primary) and v4-core, the same seeds and the same simulator option (per-game margin adjustment).
- **none:** no QB adjustment. It must reproduce the oracle replay's stored none rows for 2018-2025 exactly (identity check).
- **news_explicit (primary):** uses only reports coded S, W, M, G, UNTILWEEK, IR, PUP or C. A case whose only reports are D or U gets no adjustment.
  - **Why primary:** the list was assembled knowing which absences reached two games. Cases whose reports said nothing about length are in the list partly because of their outcome. Explicit-duration reports would be in it whatever happened.
- **news_all (secondary):** all reports, with D and U as above.
- **The oracle per-game gain** for 2018-2025, already computed, is the reference. Capture share = arm gain / oracle gain on the same seasons.

## How a report becomes a per-game adjustment at checkpoint w (after weeks 4, 9, 13)
- **Information cutoff:** the day after the team's last week-w game (ET date). Only reports published on or before the cutoff are used.
- **Active case:** a case is active if all of these hold:
  - its absence began on or before the cutoff;
  - at least one usable report is published by then;
  - the starter has not started a game after the absence began and up to week w (observed from the starter labels).

  Under the season-ending code, a starter who has returned ends the case.
- **Report used:** the latest usable report on or before the cutoff. It gives a range [lo, hi] of further absence, counted from its publication date:
  - weeks and months: the team's games dated within report date + 7·lo days and report date + 7·hi days;
  - games: lo to hi.
- **Remaining absence:** subtract the team's games already played between the report date and the cutoff. This gives the remaining range [a, b] in future games, floored at 0.
  - If the starter is still out with a = b = 0 (overdue), the range is [0, 1].
  - The remaining absence R is uniform on the integers a..b; season-ending means all remaining games.
  - P(starter out in the team's j-th remaining game) = P(R ≥ j).
- **QB values and reference:** the frozen pre-cutoff values and reference QB (most dropbacks through week w), exactly as in the oracle.
- **Replacement QB (point in time):** in order of preference:
  1. the non-starter QB with most dropbacks in the team's games after the absence began, up to the cutoff;
  2. otherwise, the non-starter QB with most dropbacks in the game where it began;
  3. otherwise, the team's non-starter QB with most dropbacks this season;
  4. otherwise, the low-sample value.
- **Shift for team t in its j-th remaining game:** scale × λ × (expected starter value - reference value), where expected starter value = P(out) × backup value + (1 - P(out)) × starter value.
  - Teams with no active case get 0.
  - The margin adjustment is home shift minus away shift. Playoffs get no QB adjustment, as in the oracle.
- **Mapping GPT's names to player IDs:** by name, among QBs with dropbacks for that team in that season or the previous one. Unmatched cases are listed and dropped, never guessed.

## Seasons, simulation and scoring
- Seasons 2018-2025; checkpoints after weeks 4, 9, 13; λ = 0.5 primary, 1.0 as a sensitivity.
- The same seeds as the oracle replay (A 1000·Y + w, B 7000·Y + w; 5,000 simulations each). Probabilities are averaged and clipped to [0.001, 0.999].
- **Primary score:** mean team-level binary log loss over division and make-playoffs at the three checkpoints. Cells are equal within a season; seasons are equal.
- **Gain:** N = none - news_explicit (positive = news better).
- **Bootstrap:** whole seasons, 10,000 draws, seed 20261028, one-sided 90% bounds.
- **Also reported:**
  - news_all;
  - by market, checkpoint and season;
  - capture share against the oracle;
  - the number of active team-checkpoints and cases used, and why cases were excluded;
  - Monte Carlo noise (A - B).

## Decision (v5-core, λ = 0.5, A and B must agree)
- **Build a live news input into v5** if N's lower bound > 0, N ≥ 0.001, and neither market's N is negative. The QB layer would apply reported absence per game, replacing the whole-season QB layer in v5's in-season number. It would be labelled, with the input's update process documented, and v4 stays frozen. The live build is a separate dated change, with its forward record kept separately.
- **Stop:** if N's one-sided 90% upper bound < 0.001, the news-based input is not built.
- **Otherwise inconclusive.** No retuning and rerunning under this rule.
- news_all and λ = 1.0 cannot rescue a failed primary.

## Disclosed limits
- **Sample:** eight seasons and about 120 cases. Only absences of two or more starts are listed, so one-game absences get no adjustment.
- **Coding:** the wording-to-games mapping is a fixed judgement, not fitted. It was written after seeing the list's report wordings, but no outcome was used.
- **Report dates:** GPT's "first report" is the earliest located, not proven earliest. Publication dates are US dates.
- **Exposure:** the oracle result and its per-season pattern were seen before this rule.
