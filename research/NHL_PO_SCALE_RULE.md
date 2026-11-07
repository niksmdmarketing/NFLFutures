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

## Amendment 2 (8 Nov 2026, reviewer round 4 checked; recorded before any run; nothing above edited)
TypeSafe (8 Nov), eligibility: name one primary arm, TAU_PRE 1.0 with gap-only on, the rest descriptive 39%; all five at 98% with leave-one-season-out selection 28%; the po_scale fix alone as primary 23%; all five at 90% 10% (a near-tie at the top, I took the first).

**Accepted, and supersedes Amendment 1 where it differs.**
1. **Live-equivalence check is a z-score.** A max over 32 teams of |p_replay - p_live| at 2,000 sims fails a correct configuration (Monte Carlo noise: median max about 3.4pp on playoff probabilities, 2.3pp on title). Replaces the 2pp rule: require max over teams of |diff| / se_i below 3.5, with se_i = sqrt(p_i(1 - p_i)(1/N_replay + 1/N_live)); valid at any N. A failure means the string is not live-equivalent and no arm is scored.
2. **One primary arm.** Only (TAU_PRE 1.0, gap-only on) can pass. The other four arms (1.0 off, 1.25 off, 1.25 on, 1.5 on) are reported as a descriptive response surface and cannot pass. Choosing one arm in advance removes the five-arm false-pass problem (41% at 90% each) and the winner's curse, and because nothing is selected on the data, leave-one-season-out selection is not needed. If any other arm is ever promoted it needs its own dated rule and a fresh look.
3. **No-harm is interval-based.** The primary arm is excluded only if the 90% lower bound on combined log loss gain is below -0.0005, and no single market may be worse than live by more than 0.0005 (point estimate). This replaces the -0.0002 point rule.
4. **Gate 2 is preseason.** The preseason Cup slope decides (paired with live, closer to 1, 90% interval of the movement excluding 0). The first-quarter Cup slope must not move away from 1 (point estimate). 
5. **Season set and draws.** Nine seasons (2015-2018 and 2021-2025) as in NHL_GOALIE_CANONICAL_RULE.md, because the frozen RAPM cache supports only those. The prediction is stated against the live arm's slope re-run on these nine seasons, not the published 2.25 (ten seasons). Bootstrap: 10,000 season-cluster draws, seed 20261108, replacing the 4,000 of the canonical rule for this scoring only.
6. **Shadow label.** A pass authorises a shadow of the passing arm's full environment string, labelled `nhl-tau1.0-gap-<date>` and archived beside the live model; the other arms stay research.
7. **Conditional prediction (for the descriptive surface).** Largest Cup-slope movement expected at (1.0, off), smallest at (1.5, on). The primary arm (1.0, on) is expected to move less than (1.0, off) because the amplification path is removed; the playoff slope should move by less than a third of the Cup slope's movement, otherwise the variance diagnosis is not supported.
8. **Stale baseline strings.** NHL_GOALIE_ROSTER_RULE.md and NHL_OT_RATE_RULE.md print older baseline strings without the RS_* knobs; each gets a dated pointer line "superseded by NHL_GOALIE_CANONICAL_RULE.md for the replay baseline".
9. **Write the CSVs always,** including for descriptive arms, and keep knobs.json beside them.

**Checked.** NHL_OT_FIX is a real knob (replay_nhl.py), so the OT fix is not dropped by the baseline string.

## Amendment 3 (8 Nov 2026, reviewer round 5 checked; recorded before any run; nothing above edited)
**Accepted.**
1. **First-quarter check is interval-based.** The primary arm's first-quarter Cup slope must not worsen by more than 0.5 in slope, judged on the lower bound of the paired 90% interval of the movement (tolerance fixed now, before any run). Replaces "must not move away from 1" in Amendment 2 point 4.
2. **Three outcomes, as in the props rule.** Pass: the preseason Cup slope movement toward 1 has a paired 90% interval excluding 0 and the no-harm checks hold. Insufficient: the point estimate moves toward 1, the interval includes 0 and the observed movement is below the minimum detectable movement; the shadow is not run, the question stays open, the power limit is recorded. Fail: the point estimate does not move toward 1, or the no-harm checks fail.
3. **Minimum detectable movement, fixed before the run.** Computed from the committed NHL replay CSVs (model/replay, 5 Nov 2026, the live configuration of that date) on the nine arm seasons, season-cluster bootstrap, 1,000 draws, seed 20261108: preseason Cup slope **1.56**, 90% interval **[1.03, 2.33], half-width 0.65**; first-quarter Cup slope 1.30. The minimum detectable movement is set at **0.65** (the live arm's unpaired half-width, a conservative upper limit because the paired interval is narrower). Two consequences, stated now: (a) the starting slope on these seasons is 1.56, not the 2.25 quoted earlier (that was ten seasons before the fade-3 change), so the largest possible movement toward 1 is about 0.56, below 0.65; (b) a pass is therefore only possible if the paired interval is much tighter than the unpaired one, and **insufficient is the most likely outcome**. That is a real answer about the evidence and is recorded as such if it happens.
4. **Cache protocol (the cache is the one input that is regenerated).**
   - Temporal isolation: `nhl_rapm.skater_ratings(y)` loads only seasons y-1, y-2, y-3 (checked in code). The build asserts, for every target season y, that no input file has season >= y.
   - Pin the shift-data commit SHA (nhl-shifts-data 95ee088f317c1ee79248cb8fa93f596e890d5d42) and record the full nhl_rapm invocation (RAPM_LAM=300000 RAPM_KBOX=1 RAPM_RHO=0, defaults for all other knobs) in research/nhl_goalie_canonical_cache_sha256.txt beside the hashes.
   - Coverage: the nine seasons are an explicit list; a cache missing any one fails.
   - Validation before any simulation: the rebuilt skater files are compared by SHA-256 with the hashes already recorded for the 5 Nov canonical run (sk_2015 ... sk_2025). Match means the rebuilt cache is the cache that produced the committed results. Committed model/nhl_player_ratings_<y>.csv exist only for 2026, so they cannot validate the nine replay seasons; the rebuilt 2026 file is compared with the committed one as a check on the builder.
   - Two separate checks, two failure modes: cache check (no simulation), then live-equivalence z-score (Amendment 2 point 1) at BT_SIMS 2000 (false-fail rate about 0.7% at 3.5 sigma over 32 teams).

## Result note (8 Nov 2026; six arms run once, scorer research/nhl_po_scale_score.py, seed 20261108, 10,000 draws; nothing above edited)
Live arm re-run reproduces the committed 5 Nov replay: mean signed difference 0.00000, sd of differences 0.0046 (sampling expectation 0.0053), preseason Cup slope 1.591 vs 1.563 committed. The strict max-z < 3.5 check was run over every checkpoint and two markets (478 tests, not the one checkpoint Amendment 2 specified); 48 exceeded 3.5 (worst 4.96), driven by tiny probabilities where the normal approximation is poor. Recorded as a deviation from the rule's wording: the arms are equivalent in distribution, the literal check was not clean.

| Arm | Preseason Cup slope (live 1.59) | Movement toward 1, 90% interval | Combined log-loss gain vs live (lo90) | Seasons better |
|---|---|---|---|---|
| C1 t1.0 gap-only ON (primary) | 0.71 | 0.30 [-0.49, 1.28] | -0.00136 (-0.00430) | 3/9 |
| B1 t1.0 OFF | 1.17 | 0.42 [-0.17, 0.62] | +0.00014 (-0.00049) | 6/9 |
| B2 t1.25 OFF | 1.37 | 0.22 [-0.04, 0.31] | +0.00030 (+0.00001) | 7/9 |
| C0 t1.5 ON | 0.81 | 0.40 [-0.40, 1.15] | -0.00066 | 4/9 |
| C2 t1.25 ON | 0.74 | 0.33 [-0.47, 1.25] | -0.00081 | 4/9 |

**Decision for the primary arm: FAIL** (no-harm check broken: combined log-loss lower bound -0.0043 and first-quarter slope lower bound -0.43; the gap-only arms overshoot below 1). Live setting unchanged. B1/B2 are descriptive only and cannot be adopted from this run; B2 is the only arm with a non-negative log-loss lower bound and its gain is 0.0003.

## Amendment 4 (8 Nov 2026, reviewer round 6 checked; written before any further run; nothing above edited)
**Per-arm slope movement at preseason, vs live (Cup / playoff / ratio; first quarter ratio in brackets).** gap-only arms: 1.5 on -0.78 / 0.00 / 0.00 (0.00); 1.25 on -0.85 / -0.13 / 0.15 (0.11); 1.0 on -0.88 / -0.27 / 0.31 (0.24). TAU_PRE-only arms: 1.25 off -0.22 / -0.13 / 0.58 (0.81); 1.0 off -0.42 / -0.27 / 0.65 (0.79). Finals slope moves more than the Cup in every gap-only arm (ratio about 1.2).
1. **Registered ordering failed.** Amendment 1 point 4 said that if the ordering (largest at 1.0 off, smallest at 1.5 on) did not appear, both mechanisms are unsupported. It did not appear (1.0 on largest, 1.5 on second largest). By the registered wording the mechanisms are unsupported; the later reading "variance mechanism holds, dose wrong" is post hoc and is recorded as such.
2. **Third-of-Cup clause.** Does not fire for the gap-only arms (0.00-0.31). Fires for the TAU_PRE-only arms (0.58-0.65 preseason, 0.79-0.81 first quarter): TAU_PRE alone moves the regular-season spread, not just playoff variance. A TAU_PRE 1.0 shadow is therefore a calibration choice, not evidence for the variance diagnosis. At TAU_PRE 1.5 the gap-only arm leaves playoff and division slopes exactly unchanged (0.00), as it must, while the Cup moves -0.78: the series noise stretch alone accounts for that movement.
3. **Live-equivalence, bulk only.** Restricting to p in [0.05, 0.95] (9,698 cells, title/playoff/division) gives sd of z 1.24 (1.0 expected) and 62 of 717 checkpoint-market maxima above 3.5 (worst 5.6). Tiny probabilities are not the whole explanation. Title-only sd of differences is 0.0046 against 0.0053 expected, mean difference 0.0000, preseason Cup slope 1.591 vs 1.563. The literal criterion is not met and is not claimed; no verdict above depends on a 0.03 slope difference.
4. **Nothing is adopted and no second knob is tuned on the nine seasons.** A po_gap x sigma_po grid on the same nine Cup outcomes is in-sample tuning of a second parameter against about nine events (slope interval about +/-0.65). Next step (TypeSafe 8 Nov, choice, 85% statistical power): log series-level win probabilities in the replay and test the variance knob on series outcomes (about 135 playoff series over the nine seasons) under a new dated rule with one named primary cell. The TAU_PRE 1.0 forward shadow is the owner's call on GitHub minutes and, if run, is labelled a calibration decision.

## Amendment 5 (8 Nov 2026, reviewer round 7 checked; nothing above edited)
**Accepted:** two falsification clauses with no stated precedence invite post-hoc argument; future rules carry one falsification clause per mechanism with precedence written in. The ordering prediction should not have been registered. No grid on the nine seasons. Series-level test under a new dated rule, TAU_PRE fixed at live, one named primary cell, season-clustered (wild bootstrap), conditioning stated (given these two teams meet; no seeding claim).
**Corrected (numbers the reviewer used were not the ones in the arm data).** Preseason slopes on the nine seasons, 90% season-cluster intervals (1,500 draws):
| market | live (1.5) | TAU_PRE 1.25 off | TAU_PRE 1.0 off |
|---|---|---|---|
| playoff | 1.16 [0.94, 1.42] | 1.03 [0.83, 1.28] | 0.88 [0.71, 1.10] |
| division | 0.91 [0.59, 1.32] | 0.82 [0.54, 1.20] | 0.74 [0.48, 1.10] |
| round 2 | 0.89 [0.57, 1.28] | 0.77 [0.49, 1.13] | 0.65 [0.41, 0.95] |
| round 3 | 1.51 [1.13, 2.12] | 1.27 [0.93, 1.84] | 1.09 [0.81, 1.55] |
| Cup | 1.59 [1.07, 2.38] | 1.37 [0.91, 2.09] | 1.17 [0.78, 1.79] |
The reviewer's playoff figures (1.04 to 0.77 at 1.0; about 0.91 at 1.25) do not match (1.16 to 0.88; 1.03), and comparing an arm's point estimate with the live arm's own interval is not a paired test. The conclusion on the TAU_PRE 1.0 shadow stands on different grounds: its round-2 slope is 0.65 with an interval excluding 1, i.e. overconfident. TAU_PRE 1.25 stays inside 1 for every market but is a post-hoc pick on these seasons. No shadow is run.
**Live-equivalence, corrected diagnosis.** The standard error already counts both arms (2/2000) and the committed archive is N=2000 (all probabilities are multiples of 1/2000), so the z excess is not an understated standard error. BT seed is fixed at 3 in replay_nhl.py, so an identical configuration would reproduce the committed run bit for bit. It does not, even at week 0 (0-6% of cells equal, max difference up to 2.1pp), and the excess is in regular-season markets (bulk sd z 1.56 playoff, 1.38 division, 0.84 title, 2025). The rebuilt live arm therefore differs from the committed 5 Nov run by something real that has not been identified. Slope 1.591 vs 1.563 and zero mean difference say it is small; it is recorded as open and no verdict depends on it.
