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
