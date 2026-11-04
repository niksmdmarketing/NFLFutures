# Two NBA award bug fixes: paired verification, 4 November 2026

Correction commit `0c6862f` is separate from this replay. Only two behaviors change:
retain canonical NBA teams regardless of games played, and exempt ROY / `6MOY`
from the 65-game gate. MVP/DPOY eligibility and the existing approximate qualifying-
minute count are otherwise unchanged. No shrinkage, temperature or rate retuning.

Official source: NBA's CBA 101, award eligibility section:
https://cms.nba.com/wp-content/uploads/sites/4/2024/11/2024-25-CBA-101.pdf
Its 65-game list covers MVP, All-NBA, DPOY, All-Defense and MIP, not ROY/Sixth Man.
Do not describe the existing 15-minute-count approximation as a full CBA implementation.

Replay unchanged main `332f1a7` and corrected `0c6862f` against identical hashed
player-box inputs, 2003–2026 for training/rookie history. Score seasons 2010–2026,
all existing regular checkpoints (day 21, then every 14 days through end minus 3),
plus the existing preseason checkpoints. Same leave-one-season-out final-season
logit training, candidate pools, 300 simulations and default per-call seed.
Do not run the separate early-shrink candidate or search any settings.

Keep original published replay CSV intact; write both variants and full candidate
probabilities privately. Report paired changes per award and season:
- eventual-winner log loss (existing floor .002);
- full-field Brier score and probability-mass deficits;
- favourite confidence vs actual favourite win frequency;
- descriptive reliability bins on the same union of candidates per paired race.
Bootstrap whole seasons for the log-loss difference, 10,000 draws, seed 20261104.
Repeated checkpoints of one winner are not independent seasons. Existing LOSO
training is retained for replication; it is not chronological walk-forward.

Specifically report ROY/Sixth Man 2024–2026 (65-game era) as well as all seasons.
The loader's 40-game problem can be masked when historical replay reads the full
season before applying cutoffs. A regression with first-three-game NBA data and
an exhibition team checks the actual early-loader failure independently.

These are input/rule corrections, not candidate performance thresholds: do not
restore incorrect eligibility merely because a historical score worsens. The
paired replay describes what changed and what old published scores were affected.
Award value remains hidden until 20 team games. No site deployment is part of this
comparison, and no raw ESPN rows or candidate-level records go to the public repo.
