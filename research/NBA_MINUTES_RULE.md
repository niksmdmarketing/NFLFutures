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

## Clarifications and unseen-player fallback (20 Oct 2026, after GPT's review; TypeSafe 100%)
- Score: ranked probability score over integer minutes 0-53 (mean squared gap between forecast and actual cumulative probabilities, divided by 53; unitless, 0 = perfect). "10.7% better" is a 10.7% lower RPS, not 10.7% more accurate minutes.
- Report timing: each report's time is its own published label (5:00 or 5:30 pm ET); a report is used only if that time is at or before the forecast cutoff (tip-off minus 1 or 6 hours), otherwise the latest earlier report (within 3 days). The archive holds one report per day, so no later revision can leak in. Caveat: the label is the scheduled publication time; an actual delay of a few minutes is not visible.
- Player pool: candidates come only from earlier games (appeared for the team earlier this season and still on it) plus players on the report in use. The predicted game's box score supplies only the outcome. Healthy bench players who appeared earlier and injured players who appeared earlier or are listed are included. Known gap: a traded player stays a candidate for his old team (and is scored as not appearing) until he first appears for his new team, because historical transactions are not in the data.
- Exclusions: 460-556 appearances a season (2020-2026) by non-candidates (season debuts, opening-night players without an earlier game, new arrivals not on a report).
- Fallback for unseen players (reported only, not a gate): players listed in the game's box who were not candidates (box listing used as a proxy for the public roster, which is known before tip-off; their minutes are not inputs). Model: appearance and minutes from last season's minutes and games played (rookie/newcomer prior when none), fitted on earlier seasons. 3,372 such player-games 2022-2026: RPS 0.0964 vs 0.1414 for a plain average baseline, better in 5 of 5 seasons; appearance log loss 0.465 vs 0.562. Much less accurate than for known players (0.0598), as expected. Players hurt all season and never listed in a box remain unseen.
- Stage one's candidate results are unchanged by this addition (re-run identical) and stage one is frozen for stage two. The short-minutes tail (PIT lowest decile 13%) is carried into stage two and tested there for its effect on prop over-probabilities.
