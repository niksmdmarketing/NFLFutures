# NBA advanced stats handoff

The local checkout contains an NBA advanced-stats addition that has not been committed, pushed, or published. The scheduled GitHub Actions refresh (`.github/workflows/refresh.yml`) is the intended data ingestion and publish path.

## What changed

- `pipeline/nba.py` imports NBA Stats-derived team/player season tables and shot event files from SportsDataverse releases, caches annual CSVs in `data/nba`, and creates compact aggregates only.
- The pipeline writes `nba_advanced_team_stats.json`, `nba_advanced_player_stats.json`, `nba_shot_zones.json`, and `nba_advanced_meta.json` and includes advanced/shot season coverage in the NBA stats index.
- `site_src/nba/advanced.html` and `site_src/nba/js/advanced.js` provide sortable, searchable team efficiency, player efficiency, and team shot-zone tables with season, season-type, and team filters.
- The existing NBA stats explorer links to the advanced page. NBL pages are not changed.
- `.github/workflows/collect-nba-research.yml` and `pipeline/nba_research_collect.py` add a separate daily/manual collector for additional 12-season NBA Stats sources (advanced league-dash tables, hustle, matchup, synergy, lineup, possession, player game-log, and player-impact files). It keeps a bounded cached copy under ignored `data/nba/research/` and uploads only the inventory JSON as a 30-day Actions artifact. These datasets remain hidden from the site until schema/coverage checks pass.

## Data fields

Team: games/wins/win percentage, offensive/defensive/net rating, pace, eFG%, TS%, turnover/rebound/assist rates, assist-to-turnover, assist ratio, PIE, and points-profile fields.

Player: minutes/games, usage, offensive/defensive/net rating, TS%, eFG%, assist/rebound/turnover rates, pace, PIE, and possessions.

Shots: team shot-attempt counts, makes, and field-goal percentage for at-rim, paint, mid-range, corner-three, and above-break-three categories derived from the source coordinates/distance. Raw shots are not copied to the site.

## Before publishing

1. Push the pending changes to `main` after reviewing them. This enables the separate scheduled collector. To start immediately, manually run `Collect NBA research data` (`workflow_dispatch`) and inspect the inventory artifact plus collection logs.
2. Review the schema/coverage of collected feeds. The local sandbox has no GitHub/source network access, so no new source files could be downloaded here and the full NBA pipeline could not be run. Do not assume a feed refreshes just because the collector runs; check each release timestamp and compare future inventories.
3. In GitHub Actions, manually run `Refresh site` (`workflow_dispatch`) and inspect logs for non-zero `team_advanced_rows`, `player_advanced_rows`, and `shot_zone_rows` plus sensible season lists in `nba_advanced_meta.json`.
4. Confirm `site/nba/advanced.html` and its JSON payloads are present on the generated `published` branch, then check the NBA section only. The site job already runs every three hours and republishes the static site.
5. Confirm the intended privacy setting before enabling any public deployment. The existing workflow pushes the generated site to `published`; `noindex` is not access control.

## Local checks completed

- After rebasing on the latest `origin/main`, a compatible Python 3.12 runtime and matching data-library binaries were used.
- The NBA importer was run against cached real NBA Stats releases and produced 210 team rows and 3,031 player rows for 2017–2023, plus 1,008 team shot-zone rows for 2017–2022. Coverage is partial: newer years were not fully downloaded in this environment.
- The NBA-specific `build_data()` and `build_site()` completed locally, writing the advanced page and its JSON payloads.
- Source inspection found and fixed the source's `regular-season` label, multiple measure/per-mode duplicate rows, full-name team mapping, and coordinate-based corner-three classification.
- The full multi-sport `pipeline/run.py` was attempted but not completed; optional NBA downloads were slow/unavailable. The NBA optional downloader now uses a short timeout and a per-run circuit breaker while preserving cached files.
- Node syntax checks passed for the NBA page scripts; Python syntax and cached-asset selection checks passed. `git diff --check` passed apart from Windows line-ending notices.

## Source documentation

- SportsDataverse NBA Stats release catalog and refresh details: https://github.com/sportsdataverse/hoopR-nba-stats-data
- Team season schema: https://github.com/sportsdataverse/hoopR-nba-stats-data/blob/main/docs/datasets/team_season_stats.md
- Player season schema: https://github.com/sportsdataverse/hoopR-nba-stats-data/blob/main/docs/datasets/player_season_stats.md
- Shot event schema: https://github.com/sportsdataverse/hoopR-nba-stats-data/blob/main/docs/datasets/shots.md
