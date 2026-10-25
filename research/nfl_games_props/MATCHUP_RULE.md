# NFL receptions: opponent position-matchup target shares. Rule written BEFORE code or results (26 Oct 2026, Sydney)

Asked by the user (improve the NFL player-prop model). TypeSafe ranked this the addition most worth testing (63%). TypeSafe also chose the fixed settings below. One candidate; no tuning after results.

## Baseline (unchanged)
The live reception model as in research/nfl_games_props/receiver_allocation_test.py ("challenger" there, live since v1):
- target share shrunk to the position prior with 20 pseudo-plays;
- catch rate shrunk with 8 pseudo-targets;
- participation-weighted conditional target budget (appearance model refitted on earlier seasons);
- beta-binomial allocation of the team pass-attempt distribution. The volume model is the research ridge/Poisson on the seven tested features, refitted on earlier seasons.

The baseline's scores must reproduce receiver_allocation_test's challenger construction on the same rows: same code path, same inputs.

## Candidate (one form)
Each receiver's raw target share is multiplied by an opponent matchup factor for his position group (WR; TE; RB including FB), before the participation-weighted budget scaling. Everything else is identical.

- **Defence history** (weekly nflverse player stats, all players, regular season): for each game and defending team, the targets allowed to each group and in total.
  - A game counts only once kickoff + 6 hours is before the target game's cutoff (kickoff - 1 hour).
  - Window: the current and previous season, the defence's last 20 games, exponential weights with a 5-game half-life (the team-state window).
- **League share** L_P: share of all targets to group P over the training seasons.
- **Shrunk ratio:** r_DP = ((weighted targets to P allowed by D) + 100 x L_P) / ((weighted total targets allowed by D) + 100) / L_P. That is 100 pseudo-targets at the league share (TypeSafe 57%).
- **Factor:** f = clip(r^beta, 0.65, 1.5) (cap: TypeSafe 40%; [0.8, 1.25] was 39%).
- **beta** is fitted on seasons 2018..s-1 (walk-forward) by maximising the beta-binomial likelihood of receptions given actual team attempts, as the concentration is fitted, with a Normal(0, 0.5^2) prior (TypeSafe 48%). The baseline concentration is kept.
- A defence with no history gets factor 1.

## Data and scores
- Research tables from research/nfl_games_props/build.py: players.parquet and teams.parquet. These are revised current nflverse vintages, not original publication snapshots.
- Test seasons 2021-2025. Rows: receivers who appeared and have a known team attempt count, as in the receiver test.
- Scores as in the receiver test (conditional_audit.score_pmf and metrics):
  - conditional RPS normalised at 40 receptions;
  - log score;
  - randomised PIT;
  - means;
  - 95th-percentile exceedance;
  - the fixed groups (established: season-control mean >= 2; low volume: < 2; candidate mean below one).

## Gates (all must hold)
1. RPS better than the baseline, with a positive paired season-block lower bound (C.season_bound) and better in at least 4 of 5 seasons.
2. Every overall PIT decile within 0.07-0.13.
3. Overall log score not worse.
4. Low-volume and candidate-mean-below-one RPS no more than 0.5% worse.
5. Absolute 95th-percentile exceedance gap no more than 0.002 worse.

## Decision
- **Pass:** v1.2 candidate, archived forward beside v1.1 under its own identifier by a separate decision. It is not displayed until forward review.
- **Fail:** recorded; stop this branch. No further forms, windows, shrinkage or caps tried in response to the result.
- No betting edge is claimed either way.
