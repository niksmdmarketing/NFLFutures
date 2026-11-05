# NFL props price-test preparation

Research branch `codex/nfl-props-price-test`. The model choice and rule were committed at `9434ed1` before any NFL price access. Model: frozen v1.1 at public revision `370ceb4`. No NFL or NBA model changes, collector changes, NBA branch edits, paid requests or price-based model inputs.

## Files

- `NFL_PROPS_PRICE_TEST_RULE.md`: frozen model choice, provenance cohorts, common main line, de-vig, 5% edge, exact-entry-line CLV, date-cluster bootstrap and gates.
- `NBA_PROPS_PRICE_TEST_PROPOSED_AMENDMENTS.md`: dated proposals, not changes to the NBA rule.
- `nfl_props_price_export.py`: exports receipt-proved distributions and supplementary historical reconstructions.
- `nfl_prop_identity.py`: deterministic player/fixture matching and querying a count PMF at an arbitrary supported line.
- `nfl_props_price_match.py`: future reference-row join using a required, frozen metadata market crosswalk. No actual odds need to be read to run the tests.
- `nfl_props_price_audit.py`: no-price export audit, including exact equality with archived PMFs and cutoff checks.

## Reproduce the export

Use the existing project's Python requirements. Put free nflverse releases in a local input directory: schedules `games.csv`, `players.csv`, `depth_charts_2026.csv`, `stats_player_week_2025.csv`, `stats_player_week_2026.csv`, `snap_counts_2025.csv`, `snap_counts_2026.csv`, `play_by_play_2025.csv.gz` and `play_by_play_2026.csv.gz`. Source: `https://github.com/nflverse/nflverse-data/releases/download/`. The exporter reads only forecast-relevant schedule and PBP columns, not market fields in those general-purpose files.

Use a full-history `nfl-props-v11-archive` checkout including `scores/github_push_activity.json`. The existing receipt selector verifies the server evidence, creation ancestry and content hashes. Historical input publication dates are not inferred from today's files.

```text
python research/nfl_props_price_export.py --data <nflverse-dir> --archive <v11-archive> --output <new-export-dir> --as-of 2026-11-05T14:56:17Z
python research/nfl_props_price_audit.py --export <export-dir> --archive <v11-archive>
python -m unittest discover -s tests -p test_nfl_props_price_preparation.py
```

The manifest hashes the frozen code/parameters and all inputs before generating distributions. Existing output directories are refused. No downloads or fitting are performed by the exporter; previewing odds is not part of it. New runs need a new output directory.

## Export schema

`probabilities.csv.gz` and `probabilities.jsonl.gz` contain one row per game, horizon, GSIS id and stat. `pmf` is the full discrete distribution conditional on appearing; it is not tied to a bookmaker line. `appearance_probability` is separate. A bookmaker's DNP settlement must be checked before any return calculation. The final cell pools the upper tail, so a query at/above 70 attempts or 30 receptions is rejected.

Important join/audit columns: `game_id`, `kickoff_utc`, `horizon_minutes`, `cutoff_utc`, `team`, `opponent`, `gsis_id`, `espn_id`, `name`, `position`, `name_aliases`, `stat`, `source_tier`, `primary_eligible`, `generated_utc`, `receipt_utc`, `snapshot`, `snapshot_sha256` and `params_sha256`. Aliases use full names. nflverse's `football_name` is a preferred first name and is combined with the surname; it is never accepted alone.

`fixtures.json` provides canonical home/away/kickoff keys for OddsPapi fixture joins. `player_index.json` supplies the game/horizon player universe. `coverage.csv` accounts for every requested game/horizon and explicitly excludes unsupported January playoffs. `manifest.json` records hashes and source counts; `audit.json` records checks.

## Future OddsPapi join

```text
python research/nfl_props_price_match.py --export <export-dir> --odds <reference.csv.gz> --market-map <frozen-market-map.json> --horizon 60 --output <new-matches.jsonl>
```

The required market map uses verified provider ids from discovery metadata, for example a **synthetic** entry `{"example-id":{"stat":"receptions","scope":"full_game","line_field":"t60_line"}}`. This is documentation, not a real provider-id crosswalk. Supported stats are `pass_attempts` and `receptions`. The actual line field must retain the entry line for this horizon; the collector's metadata handicap flag cannot substitute for it.

Identity matching still reports a checked name/id result when the line schema is unusable, but no line probability is calculated. Proprietary `player_key` values are kept as provider references and are never assumed to be ESPN ids. Unmatched/ambiguous fixtures, names, position scopes and conflicting supplied ids remain explicit. Source-name self-checks do not establish a real bookmaker match rate.

## Interpretation

Receipt-proved rows use the original frozen PMFs and information actually archived before the cutoff. Reconstructed rows use strictly earlier game data and dated depth snapshots but revised source vintages and **no invented historical injury/news feed**. They are supplementary and never silently promoted into the primary price-test cohort. Original historical availability cannot be recreated merely by supplying a past timestamp to today's live forecaster.

The first reconstruction pass exposed an identity-metadata issue: `football_name` means preferred first name. It was corrected before the final export; distributions and parameters were not adjusted. The initial export is not the deliverable. All final files are regenerated using the corrected full-name alias builder.

The January 2026 playoffs are unsupported by both the frozen model and receipt scorer. Both horizons are audited separately; they are correlated views of the same games, not independent samples. Gaps in historical receipts, especially the early chronological window, can leave the primary price test insufficient. That is not a negative profitability result. No profitability or CLV result has been calculated in this preparation.
