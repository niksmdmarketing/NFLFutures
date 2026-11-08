# Leave-one-season-out refit of tuned constants (AFL first). Rule, version 1

Written 8 Nov 2026 (Sydney), before the result. Amendments below, dated; nothing above them is edited.

## Why, and the vacuity guard
The AFL live constants (PRIOR_REG 0.65, GAME_SD 32, HGA 7.0) were tuned on match outcomes 2012-2026, the same seasons any later check uses, so in-sample scores flatter them. A refit that returns "stable" is a pass that could not have failed unless the test says what it could detect. This rule states that first.

## Test
- Data: AFL home-and-away games 2012-2026 from the live pipeline frame (the same one used for the top-10 edges). Forecast for each game: rating = A.srs of the season's earlier rounds with prior PRIOR x last season's final rating (k = 8, as live), win probability = Phi((r_home - r_away + HGA) / SD). Weekly refit (all games of earlier rounds only). Seasons 2013-2026 scored (2012 supplies the first prior).
- Grid: PRIOR in {0.3, 0.4, ..., 1.0}, HGA in {4, 5, 6, 7, 8, 9}, SD in {28, 30, 32, 34, 36}. Live point (0.65 treated as 0.7 on the grid for the fold fit; the live value itself is scored directly).
- LOSO: for each held-out season s, pick the grid point minimising log loss on the other seasons, score it on s. Compare, per held-out season, with the LIVE constants' log loss on s.
- Numbers reported: (1) fitted constants per fold and their range; (2) mean held-out log loss of LOSO-fitted minus live (negative = refit better), 90% bootstrap interval over seasons (4,000 draws, seed 1); (3) the all-season in-sample log loss of the grid best versus live.
## What could be detected (written now)
Seasons have about 200 games with per-game log loss spread about 0.5, so one season's log loss has SE about 0.035 and the mean over 14 seasons about 0.009. The test can therefore detect a held-out gain of about 0.015 (90% half-width about 0.015) and nothing smaller. A gain below that is INSUFFICIENT, not "stable".
## Decision
- If the LOSO-minus-live difference is below -0.015 with its interval below 0, a constant is flagged as mis-tuned: pre-register a replacement in a dated amendment (no live change from this result alone).
- If the interval contains 0: the constants are "not shown to differ"; no change. The report states the detectable size above.
- If fitted constants move across folds by more than one grid step in any dimension: report them as unidentified at this sample (the data cannot pin them).
- Any change needs the no-harm measurement and a dated version string before it goes live.

## Result, AFL (8 Nov 2026, `research/loso_afl.py`, 14 held-out seasons 2013-2026; applied exactly as written above)
- Fold fits: prior 0.8-0.9, HGA 6-7, SD 36 in every fold (the top edge of the SD grid).
- Held-out log loss, LOSO-fitted minus live (0.65, 7.0, 32): -0.0004, 90% interval [-0.0020, +0.0011], better in 8 of 14 seasons.
- In-sample all-season log loss: grid best (0.8, 7, 36) 0.5782; live-like 0.5792. The in-sample gap, 0.0010, is far below the 0.015 detectable size.
Reading by the rule: the interval contains 0 and the point difference is far below the detectable size of about 0.015, so this is INSUFFICIENT to show the live constants are mis-tuned and equally unable to show they are right. Fold fits move by at most one grid step in prior (0.8-0.9) and HGA (6-7), so those are identified to that resolution; they sit above (prior) and below-to-equal (HGA) the live values, but the held-out data does not reward moving. SD is pinned to the grid edge (36) in every fold, so it is not identified and a wider grid is needed before reading anything into 32 versus 36; this test used weekly-refit game probabilities, not the season-long simulation where the 36-to-32 change was made, so the two are not comparable. No live change. NBL and the other sports' constants are not covered here.
