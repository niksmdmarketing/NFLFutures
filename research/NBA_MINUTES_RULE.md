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

## Outcome (20 Oct 2026) - passes all gates
Run: research/nba_minutes_test.py build / score (rows data/research/nba_minutes_rows.csv.gz, results research/nba_minutes_results.json). 219,508 candidate player-games, 2022-2026. Mechanics fixes before scoring: tip times with mixed UTC offsets were not parsed for 2021+ (fixed with ISO8601 parsing; first build discarded before any score was computed).

| Forecast | Model | Unconditional minutes RPS | Appearance log loss |
|---|---|---|---|
| 1 h before | M | 0.0598 | 0.311 |
| 1 h before | B2r (last 10, report-aware) | 0.0670 | 0.374 |
| 1 h before | B1 (season average) | 0.0902 | 0.522 |
| 6 h before | M | 0.0709 | 0.404 |
| 6 h before | B2r | 0.0761 | 0.457 |

1 hour before: M 10.7% better than B2r (90% lower bound above zero), better in all 5 seasons (gains 0.0060-0.0079); returning players +0.0012, teammate (25+ mpg) unavailable +0.0085, starters +0.0125, bench +0.0047, team games 1-10 +0.0026, later +0.0077. All four gates pass. 6 hours before: 6.9% better, also all gates.
Calibration of minutes given appearing (randomised PIT deciles, 0.10 = calibrated): M 0.132, 0.101, 0.096, 0.093, 0.095, 0.099, 0.100, 0.100, 0.092, 0.093. The lowest decile is too full: short-minute nights (in-game injuries, blowout cameos, foul trouble) happen more often than the normal shape allows. Known refinement for later, under its own rule.
Not scored: about 450-560 appearances a season by players who were not candidates (mostly season debuts before a player's first game for the team).
Decision (TypeSafe 97%): pass; stage one becomes the minutes input for stage two; the short-minutes tail is a known refinement; stage two (game environment) next.
