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
