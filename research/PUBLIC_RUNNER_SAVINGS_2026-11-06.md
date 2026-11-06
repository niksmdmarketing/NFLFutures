# Public runner migrations — 6 November 2026

All three workflows use standard public runners and keep outputs in the private data repository. They are gated off until the owner-authorized cutover. The existing scoped archive token is reused; AU collection additionally requires ODDS_API_KEY configured directly in public repo secrets. No credential transfer workflow was executed.

NBA: identical collector/model revisions, original schedule and cutoff checks. Receipt verification explicitly targets the private repository, not the public runner repository. Private input cache is retained in the private archive branch; no public caches or artifacts. Failed bundles go to a separate unqualified private diagnostic branch and never replace qualified runs.

AU: same three schedule expressions, market selection, API quota and scheduled-only decision behavior. Source revision metadata refers to checked-out private code. No extra paid API call is required for preflight.

Publisher: a daily public preparation job at 20:27 UTC runs the existing open-data merge/ESPN repair, optional public-market collection and publishing tests, saving results only privately. The private publisher at 20:47 UTC skips these stages only if the marker is younger than 90 minutes, all tracked source/input blob IDs match (excluding only automation ledgers), working tracked files are unchanged, and GitHub confirms the exact public preparation workflow succeeded. Changes/missing markers/API outages retain the original private checks. Restricted football collection, private-page generation, deployment credentials, protected deployment and private artifacts remain in the private workflow. Package installation remains private because page generators need it.

Cutover: run each preflight first, ensure old collectors idle, disable their old private workflow, then set NBA_FORWARD_PUBLIC_ENABLED / AU_ODDS_PUBLIC_ENABLED true. Enable PUBLISHER_PREP_PUBLIC_ENABLED after the private helper is merged. Never run old and new collectors simultaneously. Rollback: set public gate false and wait for active jobs, then re-enable the old private collector. Publisher fallback is automatic; its private workflow stays enabled.

Public job logs suppress private command output and raw failures. No public data artifacts or caches are created. Secret presence/read-write access is tested without collection; a controlled NBA check verifies receipt/cutoff operations. AU's next existing scheduled run provides the first live-collection check, avoiding an extra paid request.
