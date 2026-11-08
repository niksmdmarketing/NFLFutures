# OddsPapi public runner with private storage

This moves execution minutes to the public NFLFutures repository. The collector code and downloaded data stay in nflfutures-private-data. No data, diagnostic logs, artifacts or caches are uploaded to the public repository. The collector itself is unchanged, and no OddsPapi requests were made to prepare this change.

## One-time setup

In public NFLFutures â†’ Settings â†’ Secrets and variables â†’ Actions, add two repository secrets:

1. `ODDSPAPI_KEY`: the existing OddsPapi key. GitHub cannot copy an encrypted secret from the private repository; retrieve the key from the OddsPapi dashboard. Never paste it into an issue, chat, workflow input or code.
2. `ODDSPAPI_PRIVATE_ARCHIVE_TOKEN`: a fine-grained personal access token owned by niksmdmarketing, restricted to **only** niksmdmarketing/nflfutures-private-data, with repository **Contents: read and write** (Metadata read is automatic). Choose a short expiry and renew when required. Do not grant all-repository access, workflow editing, administration or billing permissions.

Merge the PR after review. Select Actions â†’ OddsPapi collector (private archive) â†’ Run workflow â†’ main â†’ mode `preflight`. This checks secret presence and private checkout without any OddsPapi request, price-row inspection or write. It proves read access only; verify the token's Contents read/write setting explicitly.

Before the first real public run, let any active private collector finish and disable the old private `oddspapi-nba-history.yml` workflow. Then add the public Actions repository variable `ODDSPAPI_PUBLIC_ENABLED` with value `true`. Before this variable is enabled, only manual preflight can run; scheduled and real collection jobs are skipped. The two repositories' concurrency groups cannot coordinate with each other. Do not operate both collectors at once: it could duplicate API calls and cause archive conflicts.

Then dispatch the public workflow with the desired mode/sport. For a first controlled backfill run, use `max_fixtures=1`. Do not run discover/probe merely as an access test; preflight is the access-only test. Names makes up to 15 quota-counted requests. Backfill/discover/probe retain the unchanged collector behavior.

## Schedule and rollback

The new workflow preserves the existing NBA names schedule at 21:47 UTC through 20 November 2026, but it cannot run until `ODDSPAPI_PUBLIC_ENABLED=true`. No new schedule or quota allowance is introduced. After 20 November, scheduled runs make no API requests; remove the expired cron trigger when convenient. Preparation itself makes no API requests.

For rollback, set `ODDSPAPI_PUBLIC_ENABLED=false` (or disable the public workflow), wait for any running public collector to finish, then re-enable the private workflow. No data relocation is needed: both use private main.

## Boundaries

Public workflows expose step text and run status. Collector stdout/stderr and git diagnostics are suppressed because discovery output can include response samples and errors can include request URLs. Secrets remain GitHub repository secrets and are never logged deliberately. No pull-request trigger or user-provided shell command is permitted. Private credentials are scoped to the private checkout, cleaned up by checkout's post-step, and no caches/artifacts are used.

This is a prepared migration, not proof of successful public collection. Preparation did not read price/results rows, disable the existing collector, modify secrets, or start either collector. Successful private saves depend on the configured token and branch permissions. Expired tokens and rebase conflicts stop the run; no public fallback upload is attempted.
