# NBA stage one: availability and minutes model. Rule written BEFORE any result (20 Oct 2026)

Stage one of research/NBA_LINES_PROPS_DESIGN.md (TypeSafe 100%; GPT agreed). Predicts, for every candidate player in every team-game, whether he appears and how many minutes he plays, at a fixed time before tip-off.

## Data
- Player box scores data/nba/player_box_<y>.csv (minutes, did-not-play reason, starter, position, game date-time).
- Official pre-game injury reports, parsed (market-data branch research/nba_official_reports_*.csv.gz): one report per game day, about 5 pm ET, seasons 2020-2026.
- Seasons are end years. Fitting uses 2020-2021 and box scores from 2016 for structure; test seasons 2022-2026 (five), walk-forward: test season s uses only seasons before s, plus earlier games of season s.

## Forecast times and information
- Main: 1 hour before tip-off. Information = box scores of all earlier games plus the same-day report if it was published at least 1 hour before tip-off; otherwise the latest earlier report.
- Reported: 6 hours before tip-off (usually no same-day report yet).
- Who plays in the predicted game is never an input.

## Candidates
For each team-game: every player who has appeared for that team earlier in the season and whose latest team is that team, plus anyone listed for that team on the report in use. Players who appear without being candidates (debuts, signings not on a report) are counted and reported, not scored.

## Model M
1. Available = not ruled out by the report: probability of missing from report status (Out, Doubtful, Questionable, Probable, Available), calibrated on earlier seasons; unlisted players count as available.
2. Appears given available: logistic model on earlier seasons, inputs: share of the team's last 10 games with minutes, minutes per game when playing (last 10 played), starter share, games missed in a row, minutes of rotation teammates unavailable, early season flag.
3. Minutes given appearing: expected minutes = recency-weighted minutes when playing (half-life 10 team games, shrunk to his season level) + share of vacated teammate minutes (vacated = expected minutes of unavailable rotation teammates; share by position group and his baseline minutes, coefficient fitted on earlier seasons) + a return-from-absence term (first game back after missing 2 or more, fitted). Distribution: discretised normal on 1-53 with standard deviation a function of expected minutes and starter status, fitted on earlier seasons.
The unconditional minutes distribution has mass 1 - P(appear) at zero.

## Baselines (each with a fitted distribution)
- B1: season-to-date minutes when playing; appearance = season-to-date appearance rate.
- B2r: last-10-games minutes when playing; appearance = last-10 appearance rate, except players listed Out or Doubtful get P(appear) = 0.03 (a strong, report-aware baseline).
Both use the same discretised-normal form with standard deviation fitted on earlier seasons.

## Scores
- Unconditional minutes: ranked probability score over integer minutes 0-53 (primary).
- Appearance: log loss.
- Minutes given appearing: ranked probability score and randomised PIT (calibration, reported).
- Splits: returning players (first game after missing 2 or more), games with a rotation teammate (25+ minutes per game) unavailable, starters vs bench, team games 1-10 vs later, forecast time.

## Gates (M vs B2r at the 1-hour forecast; all must pass)
1. Lower pooled unconditional-minutes RPS, with a week-block bootstrap (2,000 draws) 90% one-sided lower bound on the gain above zero.
2. Better in at least 4 of the 5 test seasons.
3. Lower appearance log loss.
4. Not worse than B2r for returning players and for games with a rotation teammate unavailable.
## Decision
TypeSafe decides. Pass: stage one becomes the minutes input for stage two (game environment). Fail: recorded; stage one is revised under a new rule before anything is built on it.
