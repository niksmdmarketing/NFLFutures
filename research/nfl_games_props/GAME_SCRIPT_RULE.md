# NFL props: non-linear game script in team pass-attempt volume. Rule written BEFORE code or results (27 Oct 2026, Sydney)

Status: **draft for GPT review.**
- Asked by the user (improve NFL models; props game-script). TypeSafe: draft this refinement (58%; park props until props prices exist 36%).
- One candidate; no tuning after results.

## What exists
- **Team pass attempts** (the volume behind QB pass-attempt and receptions props) come from a negative-binomial model on seven features (research/nfl_games_props/core.py VOLUME_FEATURES). One of them, elo_gap (pre-game Elo difference / 400, home edge included), already carries game script, but only linearly.
- **Why non-linear:** big favourites run late and big underdogs throw late, and the relationship is plausibly curved, with close games near the league norm.

## Candidate (one form)
- VOLUME_FEATURES plus elo_gap², with everything else unchanged: the same ridge/Poisson volume model and negative-binomial dispersion fit, the same player allocation, and the matchup factor where v1.2 applies it.
- **Not in this rule:** replacing Elo with our own v4/v5 projected margin needs weekly point-in-time ratings for every past week. It is noted as possible later work.

## Test
- **Data:** research tables from research/nfl_games_props/build.py (teams.parquet, players.parquet), as in the receiver-allocation and matchup tests. These are revised nflverse vintages, a lagged retrospective test.
- **Folds:** walk-forward. Test seasons 2021-2025; for each, models are fitted on 2018 to the previous season (receiver_allocation_test's folds).
- **Baseline:** must reproduce receiver_allocation_test's challenger volume and reception scores on the same rows (identity check before any candidate score).
- **Scores:**
  1. **Team pass attempts:** RPS of the negative-binomial pmf (normalised at 100 attempts), log score, randomised-PIT deciles, mean error, and these split by |elo_gap| tercile.
  2. **Receptions:** the receiver test's conditional RPS, log score, PIT and the fixed groups.

## Gates (all must hold)
1. **Team-attempt RPS:** better than the baseline, with a positive paired season-block lower bound (C.season_bound) and better in at least 4 of 5 seasons.
2. **Team-attempt log score:** not worse.
3. **Every team-attempt PIT decile** within 0.07-0.13.
4. **Receptions:** RPS not worse than the baseline by more than 0.1%; log score not worse.
5. **Largest |elo_gap| tercile:** team-attempt RPS not worse.

## Decision
- **Pass:** a v1.3 shadow candidate (v1.2 + elo_gap²), archived forward under its own identifier by a separate decision, not displayed.
- **Fail:** recorded; stop this branch. No other forms (cubic, splines, interactions) are tried in response.
- No betting edge is claimed either way. There are no props prices to test profit.
