# Claude handoff: AFL addition and NBL stats repair

This checkout contains local, uncommitted AFL work plus NBL collection/display fixes. Nothing has been pushed or published. Please review the diff, run the refresh workflow, and publish only after the checks below pass.

## AFL addition

- Adds `pipeline/afl.py`, `site_src/afl/`, and the `pyarrow` dependency.
- Imports the fitzRoy public archive, which combines AFL Tables historical player/game data and Footywire advanced player stats. The collector checks archive release metadata on each refresh and retains the last downloaded archive if the source is temporarily unavailable.
- Publishes seasons from 2012 onward (the current archive runs through 2026; older source history is excluded). It includes team and player summaries, results, quarter scores, finals/premiership indicators, award indicators, and advanced team/player game and season tables.
- Season data is gzip-compressed for static hosting. The browser page decompresses it on demand. No odds or bookmaker data are collected.
- Adds AFL to the sports navigation and includes the build in `pipeline/run.py`.

## NBL repairs

- Keeps the existing 15-season window but includes official season phases, not only regular-season rows.
- Pages schedule and leader endpoints instead of assuming the first response contains every record.
- Retains regular-season team/player season stats and leaders for the full window; keeps detailed match box-score logs for the latest five seasons to avoid repeatedly downloading multi-megabyte game-centre payloads for every historic match.
- The page now keeps useful numeric fields that were previously dropped by its hard-coded `leaders` and `teams` normalization, and adds source-provided fields to the relevant stat groups/views. Season phase is visible, percent-like fields are formatted as percentages, and identity/odds/media fields remain hidden.
- The browser/network in this work session could not resolve `prod.rosetta.nbl.com.au`; the live NBL response shape still needs to be checked on the first GitHub Actions run. The code retains cached payloads on request failures.

## Validation before publishing

1. Inspect `git diff` and confirm it contains the expected AFL and NBL changes only (there may be earlier local NBA/NHL edits in the same checkout; preserve those rather than overwriting them).
2. Run `python pipeline/run.py` in the repo environment. Confirm the AFL output index has seasons and advanced-field coverage; confirm NBL season records include regular and finals phases and that recent `boxscores` are non-empty for completed games.
3. Check the generated AFL gzip files and NBL JSON, and inspect the built `/afl/` and `/nbl/` pages. On NBL, verify the live field names render with useful labels and no empty/duplicate-only table.
4. Run the GitHub Actions “Refresh site” workflow and check the published branch/site. The repository's existing workflow publishes from `main`; commit and push using the repository’s normal process. Do not force-push or overwrite concurrent work.

## Source notes

- AFL public archive: https://github.com/jimmyday12/fitzroy_data
- NBL official stats page/API: https://www.nbl.com.au/stats/statistics and `https://prod.rosetta.nbl.com.au/get/`
- The archive/site should be used as research/statistical analysis, not as betting advice.
