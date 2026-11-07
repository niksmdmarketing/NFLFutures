# NHL futures: playoff-gap stretch applied to the rating gap only, and a slope read-out of TAU_PRE. Rule fixed before any run (8 Nov 2026, Sydney)

Status: **final before running. Nothing in this rule has been run.** Live NHL futures stay unchanged whatever the result; a pass authorises a shadow only.

## Why
- Independent reviewer (DeepSeek, 7 Nov 2026) read nhl_model.py: `series()` multiplies `rx - ry` by `po_scale`, but `rx, ry` already contain the per-simulation `tau` draw, so the stretch (4x at game 0 with PO_FADE 3) also scales the rating noise. Checked in the code: true (nhl_model.py:364-367).
- Whether that is a defect or just part of what PO_FADE=3 was tuned with is untested. The 15 Oct 2026 fade replay (WORKLOG) tuned PO_FADE with the noise stretched, so the fade may be absorbing the over-wide noise.
- TAU_PRE 1.0 / 1.25 / 1.5 was already replayed on 15 Oct 2026 (WORKLOG: log loss "same", 0.0000 / +0.0001; 2.0 -0.0005). That result is overall log loss only; per-market slopes were not recorded. This rule adds the slope read-out, not a new tuning of TAU_PRE.
- TypeSafe (7 Nov 2026, choice question): run the TAU_PRE and po_scale replays first 78%.

## Disclosed exposure
- The live fade (3.0), TAU_PRE (1.5), XG_SHARE and OT_EDGE were all chosen on the same 2014-2025 seasons. A pass is a historical result.
- The reviewer's prediction is registered below before the run so it can be wrong.

## Arms (all identical except the named change; canonical baseline of research/NHL_GOALIE_CANONICAL_RULE.md plus the live starting-goalie scale)
`BT_SIMS=2000 NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_RS_SHOT_W=0.2 NHL_RS_XG=raw NHL_PO_FADE=3 NHL_OT_FIX=1 NHL_OT_EDGE=0.5 NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0 NHL_LINEUP_VAL=rapm RAPM_LAM=300000 RAPM_KBOX=1 NHL_LINEUP_GS=0.438` via research/nhl_goalie_roster_replay.py (fails if RAPM inputs are missing; no fallback), seasons 2014-2025 as available, same RAPM cache hashes in every arm.
- **A live:** the string above.
- **B TAU_PRE 1.0:** NHL_TAU_PRE=1.0 (eligible).
- **C gap only:** NHL_PO_GAP_ONLY=1 (po_scale multiplies the deterministic rating gap, the tau draw is unscaled; eligible). Check in isolation: tests/test_nhl_po_gap_only.py (agrees with live at tau 0, differs at tau > 0).
- **D sensitivity, not eligible to pass:** NHL_PO_GAP_ONLY=1 with NHL_PO_FADE=6 (the fade was tuned with the noise stretched; this shows whether it wants to rise).
- Every arm's environment is written to knobs.json next to the CSVs.

## Scores (research/replay_score.py conventions, LOSO not needed: no parameter is fitted)
Per season and market (playoff, division, conference final, finals, title): mean binary log loss, clipped as in the committed scorer; primary = equal-weight mean over markets then seasons; gain = live minus arm. Also reported: calibration slope per market at preseason and first quarter (research/replay_slope.py), 90% season-cluster bootstrap (10,000 draws, seed 20261108).

## Gates (per eligible arm B and C)
1. Primary gain >= 0 (point estimate).
2. Preseason and first-quarter Cup slope closer to 1 than live.
3. No market worse than live by more than 0.0005.
Pass = all three. Fail otherwise. An arm that passes is archived as a shadow for 2026-27 only.

## Registered prediction (the reviewer's, so it can be wrong)
At TAU_PRE 1.0 the preseason Cup slope falls from 2.25 toward 1.5-1.8, the playoff slope barely moves, and mid-season Cup log loss is flat or slightly worse. If the playoff market moves as much as the Cup, the flatness is coming from the prior rather than the variance.

## Blocked on data
The canonical baseline needs the frozen RAPM cache built from the nhl-shifts-data branch (the previous run used /home/claude/shiftbr and research/nhl_goalie_canonical_cache_sha256.txt). It is not in this sandbox. The code and tests are committed; the run waits for that cache.

## Amendments
(none)

## Amendment 1 (8 Nov 2026, reviewer round 3 checked; recorded before any run; nothing above edited)
**Accepted.**
1. **Grid, not four arms.** `po_scale` multiplies the tau draw inside each series, so Cup sensitivity to TAU_PRE depends on `po_gap_only`. Arms are TAU_PRE {1.0, 1.25, 1.5} x NHL_PO_GAP_ONLY {off, on} = six arms. The live arm is (1.5, off); the other five are eligible. This replaces arms A-D above (D is dropped).
2. **Decision statistic is the calibration slope, not log loss.** TAU_PRE moves probability from the tail to the middle, which aggregate log loss barely sees (the 15 Oct runs were 0.0000 / +0.0001). Primary: Cup slope at preseason and first quarter, paired with live on the same seasons and outcomes, 90% season-cluster interval on the slope movement toward 1. Reported separately: conference, finals, playoffs. Log loss becomes a no-harm check only.
3. **Selection rule, fixed now.** Among eligible arms with combined log loss no worse than live by more than 0.0002 and no market worse than -0.0005, choose the arm whose preseason Cup slope is closest to 1. It passes only if the paired slope movement toward 1 has a 90% interval excluding 0. Otherwise fail. A pass authorises a shadow only.
4. **Falsification wording.** The prediction is an interpretation check, not an acceptance test. If the playoff slope moves by more than a third of the Cup slope's movement, the variance diagnosis is not supported; record it and do not present the arm as evidence for the mechanism. The prediction is conditional on the arm: the largest Cup-slope movement is expected at (TAU_PRE 1.0, gap-only off) and the smallest at (1.5, gap-only on), because the 4x amplification path is removed by the fix. If that ordering does not appear, both mechanisms are unsupported.
5. **assert_live_equivalent before any arm is trusted.** Run the live arm at the most recent checkpoint and compare with the archived live forecast for the same date; Monte Carlo SE on a 10% probability is about 0.5pp at 2,000 sims, so max |p_replay - p_live| above 2pp means the string is not live-equivalent and no arm is scored.
6. **Provenance.** knobs.json now also records the code commit and points to the RAPM cache hash file.

**Checked, not changed.**
- *"Canonical string is missing the xG knobs."* True of the strings printed in NHL_GOALIE_ROSTER_RULE.md and NHL_OT_RATE_RULE.md, but the baseline in NHL_GOALIE_CANONICAL_RULE.md (the one this rule uses) already carries NHL_RS_SHOT_W=0.2 NHL_RS_XG=raw NHL_OT_FIX=1 NHL_OT_EDGE=0.5. `NHL_SHOT_W=1` is not a leftover: with `NHL_SHOT_PO=1` it sets the playoff-series rating to shots x league shooting % (that rule, line 19), while the regular-season 20% xG share is the RS_* pair.
- *"Slopes may be computable from the 15 Oct CSVs."* Only the committed replay CSVs (5 Nov) are stored, which are the live-arm configuration; the TAU_PRE variants were scratch runs and were not kept. The live-arm slopes are already in model/replay/CALIBRATION_CI.md.
- *M-only as a placebo for CLV7.* The selection paper test already scores M, X and B and prefers B only if B-M and B-X have paired intervals above 0 (research/SELECTION_PAPER_TEST_RULE.md in the private repo). X (exchange-only) takes the exchange-convergence drift; B-X is the contrast the reviewer asks for. Nothing new to register before 13 Nov.
