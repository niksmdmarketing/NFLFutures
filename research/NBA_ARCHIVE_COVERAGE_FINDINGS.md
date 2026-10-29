# Forward-test coverage audit — 29 October 2026

Updated the dated-absence rule with exact sources, first/last cutoff dates and
the requirement that actual linked inputs and independent archive receipt precede
the cutoff. Prospectively: 30 October 2026 through 15 April 2027 at 12:00 UTC,
168 daily dates. Missed cutoffs remain missing; existing jobs are not changed.

The read-only checker resolved current remote refs explicitly, avoiding stale
local Git refs. Sources: injury-monitor 0165a1e; forecast-archive 36b22dd.
It audited all 19 retrospective daily cutoffs, 10–28 October inclusive:

- 9 have a paired injury/base futures row in the 45-minute window.
- 0 have the published NBA futures archive snapshot in that same window.
- 0 are eligible: actual input linkage, frozen settings identity, seed-specific
  outputs are not saved by the current NBA futures archive schema; independent
  pre-cutoff push receipt links are not verified. Earlier report capture is not proof of use.

The archives are updating. This result does not mean that collection stopped.
It means those existing collectors do not satisfy this new prospective rule.
The props collector has branch-level receipts. These are not automatically
valid futures proofs: exact commit-tree/file linkage must be verified. This
legacy-schema checker does not perform that additional receipt-tree audit.
Old data will not be backfilled or retrospectively called prospective evidence.

Four tests pass: empty coverage, late forecasts, future injury inputs, and files
present without provenance. The script fails closed; script correctness is not
a claim that archive coverage passed. Private result:
`outputs/nba_all_team_ledger_20261029/cutoff_coverage_v2.json`.

The paired collection/provenance additions still need implementation and live
verification before claiming an operating test. No schedule, workflow, model,
website or archive was changed. Hold merge if working prospective collection
is the merge condition; this branch has not made that condition true.

## User-supplied news accounts

Recorded candidates: x.com/nbapresserwire, x.com/nblpresserwire,
x.com/eplpresserwire and x.com/aflpresserwire. Direct web access on 29 October
returned 403 for NBA/NBL/AFL and a cache miss for EPL. No automated reader or
daily collector is connected. The user's confidence in the sources is useful,
but does not validate name matching, post timestamps or model adjustments.
Future integration must distinguish confirmed availability, minutes limits,
expected return dates and speculation, retaining publication and capture times.
