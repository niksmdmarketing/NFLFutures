# Dated long-absence comparison — prospective rule, 29 October 2026

Status: protocol only. No collector or schedule is installed by this branch.
No model promotion, website change, merge, or deployment is authorised here.

## Scope and frozen alternatives

Historical ESPN dated estimates begin 10 October 2026. Drop the proposed
multi-season dated-absence replay. The older synthetic replay is development
evidence about inferred, undated absences, not validation of dated estimates.

Compare A, the complete production futures model without injury adjustments,
with B, exactly the same model and the existing frozen nba_avail.py adjustment.
Include all 30 teams, all six divisions, both conferences. No owner edits,
return-distribution tuning, roster changes, parameter changes or injury-specific
exceptions may differ between A and B. Inputs naturally update identically.
Record the exact code/settings hashes of both variants when collection starts.
Any later correction creates a new version and a separate prospective cohort.

The availability baseline currently uses current-season weight 4 while the
team fit uses 8. This is an audit warning, not evidence that changing it improves
the complete blended rating. Do not silently change B to repair that mismatch.

## Cutoffs and evidence

First prospective cutoff: **2026-10-30T12:00:00Z**. Last regular-season
cutoff: **2027-04-15T12:00:00Z**, daily inclusive (168 UTC dates).
No date before 30 October counts toward adoption. If collection is not ready,
record the cutoff as missing; do not silently move the start or backfill it.

Exact existing sources, repository `niksmdmarketing/NFLFutures`:

- Branch `injury-monitor`, `nba/history.jsonl`: captured ESPN reports, with
  `collected_utc`, source update time, player ID, status and return estimate.
- Same branch, `availability/nba/changes.jsonl` and `availability/nba/latest.json`:
  the separate availability collector's dated updates/current view. Preserve
  its schema/source identity; do not interchange it with nba/history.jsonl.
- Same branch, `nba/futures_shadow.jsonl`: paired `without`/`with` futures,
  currently only mean wins, playoffs, conference and title.
- Same branch, `nba/official.jsonl`: official report context. This alone is
  not a saved PDF, proof of submission, or an independently timed push.
- Branch `forecast-archive`, `nba/2027/index.csv` and its listed
  `nba/2027/YYYYMMDDTHHMMZ.json.gz` snapshots: published futures.
- `forecast-archive/nba/rosters/index.csv` and its listed dated CSV.GZ files:
  roster snapshots, when changed. An unchanged roster needs an explicit hash
  link to its last saved version rather than a fabricated daily copy.

Current schemas do **not** save sufficient actual input hashes, parameter
identity, seed-specific forecasts, or linked independent push receipts for this rule.
Existing game-props timing receipts may anchor a branch commit, but qualify
for futures only after verifying the exact snapshot bytes in that commit tree. Neither
file co-existence nor a Git author/committer date proves pre-cutoff receipt.
The archive-coverage checker fails closed on these omissions. A future collector
must add that evidence before any cutoff is eligible; this branch does not
install or enable one. The existing shadow lacks division/seed-1 forecasts,
so those markets remain unavailable for B until explicitly collected.

Audit command (private output, create-only):
`python research/nba_dated_absence_coverage.py --repo . --start YYYY-MM-DD --end YYYY-MM-DD --output PRIVATE/new-audit.json`.
Refresh the exact remote refs first. The script reads immutable resolved Git
SHAs and checks every requested UTC date, both forecast files, preceding report
capture times, and missing provenance. October 10–28 is a retrospective coverage
diagnostic only, not a prospective prediction test.

Primary futures cutoff: 12:00 UTC daily. Take one paired snapshot completed and
independently received by the archive in the preceding 45 minutes. Archive
receipt, immutable actual input bytes, retrieval/publication timestamps, roster
IDs, overrides, ratings, full futures output and availability plan. Exclude and
count missing, late, unverifiable or partially generated pairs. Never backfill.
Store privately; source/team codes and unmatched reports must be explicit.

For the game diagnostic, one paired forecast per game at 60 minutes before its
scheduled tip, with the same 45-minute production window and pre-cutoff inputs.
Use the same injury reports and report-submission flags for both alternatives.
Missing injury information is a coverage failure, not a healthy roster.

Run 20,000 simulations per variant with three pre-fixed seeds (20261029,
20261030, 20261031). Store seed-specific outputs and use their probability
average. Identical seeds do not imply matched random draws; report seed spread
and simulation error. No newly chosen seed or winner selection is permitted.
If the runtime budget cannot support this, amend the rule before the first pair.

## Prespecified long-absence cohort

Define from the shared pre-cutoff inputs: currently rostered player, status Out,
explicit return estimate at least 28 calendar days ahead, and rotation value
present in the frozen availability layer. Log every unmatched or excluded injury
with the reason. Do not fill absent return dates or equate missing players with
replacement-level ability. Both variants use this same cohort. Report all-team
results as primary and affected-team results as a fixed diagnostic.

Report episode capture time, source update time, estimated return, subsequent
estimate revisions and realised first appearance. Return forecasts are evaluated
from their original capture dates; do not replace earlier estimates with later
ones. Team changes and season end are right-censoring, not confirmed recoveries.

## Evaluation, fixed in advance

1 March 2027: descriptive progress/coverage report, no adoption decision.
30 April 2027: regular-season final evaluation, provided games are resolved.
Conference and championship probabilities are scored only after those outcomes
resolve; April cannot validate unresolved playoff events.

Game primary: paired win log loss. Secondary: Brier score and calibration;
report weekly paired differences and a calendar-week block-bootstrap 95% CI.
Require at least 500 eligible games and an improvement CI entirely above zero
(A loss minus B loss), with no calibration deterioration. Otherwise inconclusive.

Futures: score each resolved market separately (playoffs, division, seed 1,
conference, title), using the existing replay scoring conventions, plus a
prespecified equal-market average. Also report categorical race log loss for
division/conference/title. Report checkpoint means by team/conference and seed
spread; do not count repeated weekly forecasts of the same champion as separate
independent outcomes. Clip probabilities at 1e-6 for log scoring, identically.

One prospective season has too few independent futures races to establish a
reliable futures advantage. Game success cannot automatically promote B's
futures. This season can falsify gross calibration claims and provide directional
evidence; a futures adoption decision requires a separately documented review
of the complete pipeline and uncertainty, rather than invented significance.

No March/April result is an automatic site change. Preserve A, B, all input
ledgers and coverage failures. Markets are benchmarks only, never model inputs.
