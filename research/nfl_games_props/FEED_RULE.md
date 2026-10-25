# Existing-feed availability experiment, 23 October 2026

Written before fitting/scoring this extension. Existing prototype, outputs and production remain unchanged.

Audit locally held injuries, depth charts and official-report collector. Preserve file hashes and timestamp semantics. A source's modification timestamp is not proof of historical retrieval/publication time. Capture current official report and current depth chart only if accessible, preserving original bytes, fetch time and hashes; a failed fetch is recorded, not replaced by guessed data. No recurring collection or workflow changes.

Historical experiment: injury files with date_modified, 2020–2024. Test 2021–2024, training on 2020 through the preceding season for BOTH controls. Join season/week/team/GSIS ID, use only report modifications strictly before kickoff minus one hour, retain missing/unknown explicitly. Missing player rows do not establish health. Final revised files can omit earlier report versions: disclose that survivorship limitation.

Baseline uses existing five involvement features. Challenger adds categorical game/practice report statuses and a flag for eligible team-report evidence. Categorical logistic regression, fixed C=1; no feature/threshold search. No deterministic Out override because outcomes include offensive involvement, and revised reports have limitations. Train volume/rates on the prototype's original earlier-season schedule; only involvement probabilities differ. Recompute attempts/receptions PMFs, score identical players, count RPS and involvement log loss. Report seasons and paired season bootstrap; exploratory historical evidence only, never automatic adoption.

No expected-starter labels inferred from actual target-game attempts. Weekly depth charts without publication time cannot establish a one-hour historical starter. A source snapshot later than cutoff is ineligible. Current mapping: historical GSIS ID exact; live name aliases require unique canonical name plus team and compatible position; ambiguous/unmatched rows retained, never fuzzy-guessed. Store the source profile ID and mapping method.

Proceed to a shadow recommendation only if prop RPS improves overall with a positive season-cluster lower bound and at least 3/4 seasons improve, without worsening involvement log loss. Otherwise report failure/mixed results. Four revised-data seasons do not establish a market edge, and are not untouched holdouts.
