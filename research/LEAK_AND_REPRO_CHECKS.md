# Perturbation leakage tests and reproducibility (11 Nov 2026). Projexions learnings, TypeSafe 96% / 85%; checklist by DeepSeek (relay 046).
## Perturbation test (research/leak_test.py)
Every result after a cut is scrambled to extreme random values (schedule kept identical) and the replay re-run; every forecast column at checkpoints on or before the cut must be unchanged. Sanity check: including checkpoints after the cut makes the test FAIL (AFL p_playoff differed by 0.42), so the harness can see leaks.
- AFL 2024, cut round 12: PASS (234 rows x 15 forecast columns identical).
- NBA 2024, cut day 60, live flags: PASS (270 rows x 10 columns).
- NFL 2024, cut week 9: PASS (320 rows x 5 columns).
- MLB 2024, cut day 60: PASS (270 rows x 6 columns). (A first version dropped scrambled ties, which changed the schedule and showed a spurious difference; fixed.)
Scores only: this test does not catch participation leaks (who played later); those are covered by the prior audit below.
## Prior audit (season-start information only)
- NBA: the replay's roster step uses each player's FIRST team of the season from the whole season's box scores, so players who first appear more than three weeks in are placed on their team at preseason (104/91/110 players in 2019/2023/2025, of whom 84/66/82 on a new team; 2.4% / 2.3% / 2.9% of the season's minutes). Disclosed exposure in the replay only (live uses the real preseason roster); small.
- MLB: the frozen band weights 0.50/0.65/0.85 sit inside or at their walk-forward values in every check season (0.45; 0.65-0.70; 0.80-0.85), so the check-block reading is not materially in-sample. Disclosed exposure.
- NHL, CBB, NFL, AFL 0.65 and NBL 0.4 provenance: AFL/NBL constants were chosen with all seasons in view (already recorded as spent seasons); NHL needs its runner; recorded as disclosed exposure, no change.
## Reproducibility
Determinism checked 11 Nov: AFL 2024 and NBA 2024 (live flags) re-run from their manifests byte-identically, so current runs are reproducible; the gap is only the old committed files. Known failure: the committed NBA replays (5 Nov) do not reproduce row-level from either the 5 Nov or current code; generator unknown. Gate adopted: every new replay run writes a manifest (code commit, settings, seed, input-file hashes) next to its CSVs, and a result is quoted only if a re-run from the manifest reproduces the CSVs exactly (research/replay_manifest.py).
