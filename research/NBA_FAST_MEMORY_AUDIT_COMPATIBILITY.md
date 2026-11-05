# NBA fast-memory archive auditor compatibility review

5 November 2026. End-to-end props assessment found that nba_fast_memory_audit.py called .get on old list-format timing files and crashed before validating current records. Match the primary auditor: legacy job-run lists contain no independent push evidence and are ignored, never converted into receipts. No model, parameter, workflow, archive or adoption rule changes.

Three unit regressions cover legacy lists, valid complete push records, and incomplete metadata. Full frozen archive cc67463d82031f20cb0903743497f6cbfcf7c511 checked with the compatibility guard: 558 observed challenger snapshots, 186 eligible game/horizon pairs, 672 actual input/code/parameter blobs verified; no observed-record errors. This is operational verification only. Missing activation windows remain excluded and reported.

Complete NBA/NFL props findings and price/outcome evidence stay in the private repository, research/PROPS_ASSESSMENT.md, on its props-assessment branch. Do not infer a market edge or promote the candidate from this audit.
