# NFLFutures

A private NFL stats and futures site. Every 3 hours a GitHub Actions job downloads fresh public data from
[nflverse](https://github.com/nflverse/nflverse-data), rebuilds the model outputs and pushes a static site to the
`published` branch, which Cloudflare Pages serves behind Cloudflare Access.

## Pages

| Page | What it shows |
|---|---|
| Futures | Division, playoff, No. 1 seed, conference and Super Bowl chances; win-total over/under for any line; QB changes |
| Awards | MVP, OPOY, DPOY, OROY, DROY, Comeback and Coach of the Year probabilities, each with its 2018–2025 track record |
| Matchups | Offense rank vs the defense rank it faces in five categories, with weekly rank trends |
| Offense, Defense | Per-play efficiency, scoring, third down, red zone, turnovers, pressure |
| Schedule | Strength of schedule played, remaining and full season, from the model's team ratings |
| Pace, Pass rate | Seconds per play, plays per game, pass rate over expected |
| Off./Def. tendencies | Shotgun, play-action, motion, screens, RPOs, aDOT, blitz rate, rushers, box counts |
| O-line, D-line | Pressure, sack and hit rates, yards before contact, stuffs |
| Coverage | Targets, completion rate, yards per target and passer rating allowed by CBs, safeties and LBs |
| Box scores | Efficiency box score for every game |
| Injuries | Latest practice report and the model's expected starting quarterbacks |

## Layout

```
pipeline/       Python: run.py orchestrates everything
  common.py     downloads (cached in data/), loaders, constants
  ratings.py    team ratings (frozen v3 weights) + quarterback layer
  simulate.py   Monte Carlo season and playoffs
  awards.py     award choice models
  matchups.py   matchup ranks
  stats.py      stat pages
  build_site.py assembles site/ from site_src/ and build/*.json
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

## Model

Parameters in `model/settings.json` were fitted offline on 2010–2025 seasons and are not re-fitted by the job:
learned weights for team strength (trained 2010–2021, checked on later seasons), a quarterback adjustment worth half the
gap between the expected starter and the season's main quarterback, simulation settings and award model coefficients.
Backtests against 2018–2025 bookmaker futures found the model matched the market only around Weeks 5–8 and did not
produce profitable bets, so the site shows probabilities only.

## Data

All data comes from nflverse releases: play-by-play, schedules, weekly player stats, rosters, injury reports, depth
charts, FTN charting and Pro Football Reference advanced stats.
