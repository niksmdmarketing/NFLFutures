# Private paired futures collector — 29 October 2026

Installed with explicit user approval of a collector-only private-main workflow.
No site build/deployment or model/research-branch merge. No paid data or trades.

Private repo `NFLFutures-private-data`, workflow `nba-futures-forward.yml`,
operational commit f55f6f04. Data branch `nba-forward-archive`; built-in
GITHUB_TOKEN, contents:write. No new secret required. Retry/watchdog schedule,
fixed cutoff dates and exact source pins are in NBA_DATED_ABSENCE_FORWARD_RULE.md.
No GitHub switch remains for the user to enable.

Verified genuine GitHub smoke run 40823071291, completed successfully:

- Complete unchanged production model 5708ccf7, including roster, RAPM and playoff
  rotation, with availability weight 4. No fallback to team-only allowed.
- Three fixed seeds, 20,000 simulations per seed, base/injury variants: 180
  team forecasts. Full future-market outputs, settings and dependency versions.
- 108 actual input/output files verified from raw Git object bytes.
- Bundle commit 06876c40; separate receipt commit bd468bdb.
- Independent GitHub push received 2026-10-29T05:25:47Z; exact commit linkage
  and manifest SHA verified. Smoke explicitly excluded from adoption.
- All saved object hashes, paired team sets and title probability sums pass.

An initial local smoke had PDF bytes but no installed parser. It was excluded;
added a regression gate requiring successful parsing. The genuine GitHub run
has the PDF parser installed. During verification, Windows git archive converted
line endings; raw cat-file bytes and a no-conversion export confirmed the remote
archive was correct. No stored inputs were overwritten to hide either check.

First real cutoff: 30 October 2026 12:00 UTC (23:00 Sydney/Melbourne).
There is no eligible primary forecast yet. Scheduling is enabled; automatic
operation at that future cutoff is not yet verified. Failed/missed cutoffs turn
the watchdog red, never count as success or get reconstructed later.

The job consumes private Actions minutes and stores raw inputs privately. It
caches historical downloads, skips expensive generation after the day's bundle
exists, and has a 40-minute cap. Three retry opportunities do not imply three
new forecast bundles. Existing unrelated workflows remain unchanged.

Private independent evidence:
`outputs/nba_futures_forward_local/end_to_end_verification.json` and
`raw_git_verified/`. Nothing raw was uploaded to the public research repo.
