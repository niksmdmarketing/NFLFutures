# Sports Futures — NFL, NBA, NBL, NHL and AFL

A private NFL, NBA, NBL, NHL and AFL stats and futures site. Every 3 hours a GitHub Actions job downloads public data from
[nflverse](https://github.com/nflverse/nflverse-data), SportsDataverse's ESPN-derived NBA releases, the NBL's public statistics feed,
the NHL's public statistics API and the fitzRoy AFL data archive, rebuilds the site, and pushes a static site to the `published`
branch, which Cloudflare Pages serves behind Cloudflare Access. NFL remains at the root, with separate `/nba/`, `/nbl/`, `/nhl/`
and `/afl/` sections.

## Pages

### NFL

| Page | What it shows |
|---|---|
| Futures | Division, playoff, No. 1 seed, conference and Super Bowl chances; win-total over/under for any line; QB changes |
| Awards | MVP, OPOY, DPOY, OROY, DROY, Comeback and Coach of the Year probabilities, each with its 2018–2025 track record |
| Matchups | Offense rank vs the defense rank it faces in five categories, with weekly rank trends |
| Standings | Records (home/away/division/conference/one-score), points, Pythagorean and EPA-expected wins, luck, turnover margin, fumble recovery share, opponents' FG % |
| Offense, Defense | Per-play efficiency, scoring, third down, red zone, turnovers, pressure |
| Passing | EPA, ANY/A, CPOE, TD/INT rates, 20+ yd passes, air yards, aggressiveness, separation, cushion, YAC over expected (NGS), time to throw, bad throws, drops — offense and defense |
| Rushing | EPA, success, YPC, rush yards over expected, yards before/after contact, broken tackles, 10+ yd runs, stuffs, 8+ box, NGS efficiency — offense and defense |
| Drives | Points, TDs, three-and-outs, punts, turnovers, starting field position, yards/plays/time per drive — offense and defense |
| Situational | 3rd down by distance, 4th-down conversion, 4th-and-short go rate, red-zone and goal-to-go TD %, turnover margin |
| Special teams | ST EPA, FG % by distance, XP %, net punt, punts inside 20, touchbacks, return averages |
| Discipline | Penalties and yards per game, offense/defense split, pre-snap, DPI, drawn, missed tackles |
| Schedule | Strength of schedule played, remaining and full season, from the model's team ratings |
| Pace | Play clock used before the snap (2022+), neutral pass rate, no-huddle, plays per game; filters for week, quarter, down, venue, huddle |
| Pass rate | Pass rate over expected |
| Off./Def. tendencies | Shotgun, play-action, motion, screens, RPOs, aDOT, blitz rate, rushers, box counts |
| O-line, D-line | Pressure rate, no-blitz pressure rate, time to throw, sack and hit rates, yards before contact per RB rush, stuffs |
| Coverage | Targets, completion rate, yards per target and passer rating allowed by CBs, safeties and LBs |
| Award race | Each award's contenders (stats to date, 17-game pace, team record, model chance) vs every winner since 2018 at the same week and at season end |
| QBs, Rushing, Receiving, Defense, Kicking | Player stats since 2018 (official, NGS, PFR, snaps) with filters, career by season and weekly game logs |
| Box scores | Every game since 2018, best/worst-since notes, team game log |
| Injuries | Latest practice report and the model's expected starting quarterbacks |

### NBA

| Page | What it shows |
|---|---|
| Futures | Projected wins, division, top-six, playoff, No. 1 seed, conference and championship probabilities; any win-total line |
| Stats | Ten seasons of team profiles, player production, shooting/usage rates and team game logs; regular season and playoffs are separate |
| Team ratings | Opponent-adjusted offense and defense, pace, roster adjustment and simulation rating |
| Players | Prior-season production and the conservative player impact used for roster movement |
| Games | Upcoming game win probabilities and recent results |
| Methodology | Inputs, simulation rules and limitations |

### NBL

| Page | What it shows |
|---|---|
| Stats | Up to 15 available seasons of NBL team stats, player leaders, rosters, standings and game results; the active season refreshes every three hours |

### NHL

NHL pages cover standings, futures, team and player statistics, awards and game logs.

### AFL

| Page | What it shows |
|---|---|
| Stats & history | AFL Tables match results, quarter scoring, team season profiles and player season totals from 2012 onward; Brownlow vote and goal leader indicators; Footywire player/team match statistics including contested/uncontested possessions, disposal efficiency, clearances, score involvements, metres gained, intercepts, turnovers and pressure/stoppage measures. The current archive runs through 2026, and the public archive is checked every three hours. |

## Layout

```
pipeline/       Python: run.py orchestrates everything
  common.py     downloads (cached in data/), loaders, constants
  ratings.py    team ratings (frozen v3 weights) + quarterback layer
  simulate.py   Monte Carlo season and playoffs
  awards.py     award choice models
  matchups.py   matchup ranks
  team_season.py  per-season team tables and the clock-used cube
  team_extra.py passing, rushing, drives, situational, special teams, discipline, Next Gen Stats
  history.py    builds completed seasons into history/ (committed)
  stats.py      stat pages (history + current season)
  build_site.py assembles site/ from site_src/ and build/*.json
  players.py    player season tables, career and weekly logs (past seasons cached in data/)
  award_race.py award contenders vs past winners at the same week
  nba.py        NBA downloads, ten-season box-score stats, ratings, roster adjustment, simulation and `/nba/` site output
  nbl.py        NBL public feed, cached historical seasons and `/nbl/` stats explorer
  nhl.py        NHL public stats API, team/player reports and `/nhl/` pages
  afl.py        AFL history, player/team advanced stats and `/afl/` explorer
model/settings.json   frozen model parameters (fitted offline, see below)
site_src/       HTML fragments, CSS and JavaScript for the pages
.github/workflows/refresh.yml   the scheduled job
```

Run locally:

```
pip install -r requirements.txt
python pipeline/run.py          # writes build/*.json and site/
cd site && python -m http.server 8000
```

`N_SIMS=2000 python pipeline/run.py` gives a faster, noisier test run.

## Year by year

Every ranked stat page has a season picker (2018 onward) and a Year by year view: one stat, every season side by
side, and the change between any two seasons. Completed seasons live in `history/`; the job builds a season there
automatically once it finishes. FTN charting starts in 2022, Next Gen Stats per-play pressure covers 2018–2025
(weekly Next Gen Stats such as time to throw, CPOE and rush yards over expected include the current season), and
play-clock timing starts in 2022.

## Model

Parameters in `model/settings.json` were fitted offline and are not re-fitted by the job.

- Team ratings (v3): opponent-adjusted passing, rushing, special-teams and margin components with weights learned on
  2010–2021, plus a quarterback adjustment worth half the gap between the expected starter and the season's main QB.
- v4 (October 2026): ratings scaled to 0.89 (they were overconfident out of sample), a pressure-allowed adjustment
  (−19.15 points per unit of pressure rate, blended with last season at 2 games; the only one of twelve candidate stats
  that improved 2023–2025 predictions), team uncertainty tau 5.0 and game noise 11.37 tuned jointly on 2022–2025 win
  totals, home field 1.8, exact NFL tiebreakers, 100,000 simulations with a fixed seed.
- v4 is frozen (frozen copy on the `model-v4` branch) for a prospective test on the 2026 season. Every refresh's forecasts are saved,
  compressed, on the append-only `forecast-archive` branch (`<season>/<timestamp>.json.gz` plus `index.csv`), skipping
  runs whose probabilities did not change.
- Backtests against 2018–2025 bookmaker futures (v3) found the model matched the market only around Weeks 5–8 and did
  not produce profitable bets, so the site shows probabilities only.

## Research snapshots (private)
`python pipeline/snapshots.py` builds point-in-time team snapshots (20/40/60/80% of the league schedule and season end,
each using only games on or before its as-of date) joined to final labels (playoffs, rounds won, finalist, champion,
division winner, top seed). Output stays in git-ignored `data/research/` with a `COVERAGE.json` validation report
(leakage re-check, monotone dates, end snapshot equals the full-season table, one champion per finished season).
It runs at the end of each refresh and is never published.

## Schedule outlook
`pipeline/sos.py` builds `<sport>/outlook.html` (data in `data/schedule.json`): how hard each team's next 5 / next 10 /
rest-of-season games are, a fixture ticker, rolling 5-game difficulty and a schedule-based win projection. Ratings are the
ones the Futures simulations use; home advantage and short/long rest are tuned in `pipeline/sos_tune.py` (stored in
`sos_params.json`; term choice made with TypeSafe on held-out seasons; travel distance was tested and dropped). When the
next fixture is not out (AFL off-season) the page shows the completed season's draw as a recap.

## NFL quarterback-layer test
`pipeline/nfl_qb_backtest.py` (offline) rebuilds ratings and QB values before every 2019-2025 game and scores the QB layer on the
582 games with a starting-QB change (results in `model/qb_backtest.json`). The layer helps (RMSE 13.48 -> 13.16 at the live
lambda 0.5); lambda 0.75 was better out of sample (13.09). v4 stays frozen; lambda 0.75 is noted for v5 (TypeSafe 61%).

## Calibration and roster tests (Oct 2026)
- Shrinking futures probabilities toward the field: NFL no (point-in-time 2022-25, slightly sharper was better); NHL preseason
  yes: extra preseason rating uncertainty `TAU_PRE = 1.5` in `nhl_model.py`, fading out by game 20 (playoff log-loss 0.572 -> 0.560,
  better in 4 of 5 seasons). NBA needs a title-probability back-test first.
- Roster continuity for NBL/AFL (`pipeline/roster_continuity_test.py`): no improvement, not adopted.

## Market scorecard (Polymarket)
`.github/workflows/market-data.yml` runs daily: `research/polymarket_collect.py` saves public Polymarket prices and full daily
price histories for US-sports futures, and `research/market_report.py` writes a private model-vs-market gap report
(`reports/latest.md`), both on the `market-data` branch. `research/market_benchmark.py` scores the point-in-time back-tests
against the market on past seasons (`model/market_benchmark.json`). Prices never feed a projection and are not shown on the site.

## Shiv Value Models (`/shiv/`)
Three separate approaches for US futures, on their own page so the sport pages stay model-only: our independent model,
Polymarket (bid/ask midpoint, margin removed), and Shiv, an experimental 50/50 combination (geometric mean; log-odds
average for yes/no markets). `pipeline/shiv.py` runs every refresh; markets are listed in `pipeline/shiv_markets.json`
(update the slugs each season). Each refresh's model numbers and raw quotes (bid, ask, last, spread, liquidity, fee
schedule, time) are appended to the `shiv-archive` branch; settled markets are scored from that archive (forward test).
The back-test table comes from `model/market_benchmark.json`. No value/edge labels; gaps of 5+ points are flagged "check".

## Long match-level test vs closing odds (Oct 2026)
`research/match_vs_market.py` + per-sport drivers (`nfl_match_market.py`, `us_match_market.py` with `us_match_ratings.py`,
`au_match_market.py`) compare our point-in-time pre-game probabilities with closing odds: NFL nflverse lines 2006-2025,
NBA/NHL Sportsbook Reviews Online archive (via the Internet Archive; on the market-data branch), AFL/NBL AusSportsBetting.
Results in `model/match_vs_market_*.json`: the market is sharper everywhere; best weight on our ratings ~0-25%, so Shiv is
displayed at 20% model / 80% market (50/50 scored alongside). The same test re-tuned AFL and NBL rating settings on outcomes.
