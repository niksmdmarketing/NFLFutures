# NBA futures: within-season recency in the team ratings. Rule fixed before any code change or result (6 Nov 2026, Sydney)

Status: **final before running.** Nothing in this rule has been run. Live NBA futures stay unchanged whatever the result.

## Why
- Owner question (6 Nov 2026): do the models carry enough time decay?
- What already exists (code and WORKLOG checked before writing this):
  - NBA futures ridge (pipeline/nba.py `_fit_ratings`): older seasons decay x0.2 a year; current-season games weigh 8 each, all equal. Weight 4 -> 8 was chosen on the 14-season weekly replay (13 Oct 2026).
  - NFL: within-season recency (half-life 4 weeks) was tested as part of v5 and was inconclusive (research/NFL_V5_PROMOTION_RULE.md).
  - AFL and NBL: recency-weighted in-season ratings gave no gain (model/replay/WORKLOG.md).
  - NBA player props, minutes and AFL player model already carry game-count half-lives.
- Not found in the record: a test of within-season recency in the NBA futures team ratings. This rule covers only that.
- TypeSafe (choice question, 6 Nov 2026) put NBA-only first (43%); NBA+NHL 2%, all sports 1%, nothing more 0%.

## Disclosed exposure
- The baseline settings (current weight 8, decay 0.2, ridge 24, tau, sigma) were chosen on the same 2013-2026 seasons used below. A pass is therefore a historical result, not independent proof.
- No within-season recency result for NBA futures has been seen by me before writing this.

## Change tested (one form, one primary setting)
In `_fit_ratings`, current-season game weights become CW x w_g, where w_g = 0.5^(age_g / H), age_g = days from the game to the latest game in the training window (the checkpoint, so point in time), and w_g is rescaled so the mean weight over the current season's games stays exactly CW (8). Total current-season weight against the prior seasons is unchanged; only the split inside the season moves. Prior-season weights (decay 0.2) and everything else (ridge, roster step, RAPM mix, tau, sigma, simulation) are unchanged. H = 0 means off (live behaviour, the default).
- **Primary variant:** H = 90 days.
- **Sensitivity only, not eligible to pass:** H = 45 and H = 180.

## Both arms identical except H
- research/replay_nba.py as committed, 14 seasons 2013-2026 (the script's own era handling and skipped season), weekly checkpoints, BT_SIMS 2000, BT_OUTDIR a scratch folder (committed replay CSVs not touched).
- Baseline is re-run in the same session with H = 0, not read from the committed CSVs.
- Paired simulation seed: seed set A = 20261009 (the code's current fixed seed); seed set B = 20261110 (new, set through a BT_SEED switch whose default leaves the code unchanged).

## Scores
- Per season and market: mean binary log loss over all checkpoints, probabilities clipped to [0.002, 0.998] (research/replay_compare.py convention).
- Primary score: the equal-weight average over the markets title, finals, division, seed 1 and playoffs, then over seasons.
- Gain = baseline loss - variant loss (positive = variant better).
- Bootstrap: resample whole seasons, 10,000 draws, seed 20261106, one-sided 90% lower bound.
- Also reported: every market separately, by quarter of season, calibration slope.

## Gates (all on the average of seed sets A and B)
1. Primary gain: one-sided 90% lower bound > 0 and gain positive in at least 8 of 14 seasons.
2. Gain positive (point estimate) in each of the five markets.
3. No market worse than baseline by more than 0.002.
4. Gain positive in the first and second quarter of the season (where recency should matter most).
5. Seed sets A and B agree on gates 1-4. If they differ the result is **inconclusive**, not a pass.

## Decision
- **Pass:** archive the H = 90 variant as a live shadow beside the displayed model for the rest of 2026-27 (v4-style challenger, displayed model unchanged), scored on the live archive. Promotion would need that forward evidence. A historical pass is not a claim of proven improvement or profit.
- **Fail or inconclusive:** record as is; NBA futures keep equal in-season weights.
- Results are written to research/nba_futures_recency_results.json and an amendment section below, dated, never by editing this rule.

## Amendments
### Result note (7 Nov 2026; replays run after this rule and the code were committed; nothing above edited)
Run: 6 arms x the script's 13 replayable seasons (2013-2026; the COVID-bubble season is skipped by the script, so "14" in gate 1 meant 13 available; the result fails under either count), 2,000 sims, seed sets A and B, scratch outputs, committed CSVs untouched. Results: research/nba_futures_recency_results.json.
- **Verdict: FAIL** (sets A and B agree). H = 90 days: primary gain +0.00011 mean log loss (A +0.00006, B +0.00015), one-sided 90% lower bound -0.00061, better in 4 of 13 seasons (gate 1 fails).
- By market (average): title -0.0010, finals +0.00003, division +0.0003, seed 1 +0.0007, make-playoffs +0.0005; title is worse (gate 2 fails; gate 3 holds, none worse than -0.002).
- By quarter: first +0.0002, second -0.0005 (gate 4 fails), third +0.0005, fourth +0.0004.
- Title calibration slope (seed A): 1.374 baseline vs 1.343 with recency; others within 0.01.
- Sensitivity only: H = 45 days -0.0004 (4 seasons better); H = 180 days +0.0003 (6 seasons better). Neither could pass.
- **Decision:** NBA futures keep equal in-season weights. No shadow. Recency is within noise of zero in both directions, consistent with the NFL, AFL and NBL recency tests.
