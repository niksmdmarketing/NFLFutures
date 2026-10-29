# All-team component ledger — 29 October 2026

Built `research/nba_component_ledger.py`. Run it with `--source` pointing to the
private Pacific-audit input folder and `--output` to a new private directory.
It uses saved files only, records hashes, and refuses to overwrite an output
directory. No downloads, simulations, model tuning or public data exports.

The local ledger covers all 30 teams and 519 roster entries. It contains the
team-only prior refit, current-results difference, old/new roster strengths,
roster coefficient and centering, override/no-override roster terms, player-mix
share, published final rating, archived injury/base futures and dated absences.
Per-player projected minutes, box impact, override notes/date evidence are kept
privately. There are no remaining unmatched active overrides.

The historical export does not contain exact RAPM strengths or playoff deltas.
The player-mix contribution is reconstructed from rounded published ratings;
its inferred strength has an explicit rounding bound. Exact missing fields are
null. Do not describe this as a new full RAPM reproduction. Added optional
`audit` dictionaries to the production roster and player-mix functions so an
authorised future caller can capture their exact stages and failure/skip status.
These observers do not change the forecast calculation or enable a workflow.

The prior refit is a diagnostic, not the archived opening-night forecast.
Archived injury differences change all injuries together and contain Monte
Carlo noise. Later-retrieved raw inputs are not proof of historical availability.

Important audit lead: nba_avail.RATING_W weights current games at 4; the current
team fit uses 8. This is a documented inconsistency with the stated baseline
description, not proof that changing one number fixes the blended model.
No weights changed in this branch.

Verification: exact all-team rating equality before/after override retirement;
the team fit and roster step reproduce the published rounding; observer
invariance and skip-status tests. Full public suite: 88 tests, 85 pass, 2 skipped,
1 pre-existing Windows SQLite cleanup error. The unchanged baseline reproduces
that same error (85 tests, 82 pass, 2 skipped). No failure is hidden as a pass.

Local evidence: `outputs/nba_all_team_ledger_20261029/` in the shared workspace.
Raw inputs and player-level ledgers stay outside GitHub. Nothing merged/deployed.
