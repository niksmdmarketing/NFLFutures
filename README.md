# Sports Futures — NFL and NBA

A private NFL and NBA stats and futures site. Every 3 hours a GitHub Actions job downloads fresh public data from
[nflverse](https://github.com/nflverse/nflverse-data) and SportsDataverse's ESPN-derived basketball releases,
rebuilds both models and pushes a static site to the `published` branch, which Cloudflare Pages serves behind
Cloudflare Access. The existing NFL pages remain at the root; NBA lives under `/nba/` and a sport switcher joins them.

## Pages

### NFL

| Page | What it shows |
|---|---|
| Futures | Division, playoff, No. 1 seed, conference and Super Bowl chances; win-total over/under for any line; QB changes |
| Awards | MVP, OPOY, DPOY, OROY, DROY, Comeback and Coach of the Year probabilities, each with its 2018–2025 track record |
| Matchups | Offense rank vs the defense rank it faces in five categories, with weekly rank trends |
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
| Box scores | Efficiency box score for every game |
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
  nba.py        NBA downloads, ten-season box-score stats, ratings, roster adjustment, simulation and `/nba/` site output
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
