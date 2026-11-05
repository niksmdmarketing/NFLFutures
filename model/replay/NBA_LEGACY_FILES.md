# Legacy NBA replay files (labelled 6 Nov 2026)
`model/replay/nba_<season>.csv` (2013-2026) are **legacy** results, kept for the record and not used as baselines (research/NBA_REPLAY_STANDING_RULE.md, Amendments 1, 4 and 5).
- 2016-2019 and 2021: built with BT_ERA=0 (play-in and 82 games in every season), verified exact.
- 2013-2014: old franchise codes (NJ) not mapped, so Brooklyn's earlier seasons were missing from the game-level fit.
- 2013-2015: no division-winner top-four seeding.
- 2013 and 2021-2026: extra simulated games (postponed originals, the NBA Cup final from 2024, a filler game for the cancelled 2013 Boston-Indiana game).
- 2015 and earlier: committed code and settings not re-verified here.
The corrected baseline is `model/replay/nba_base_v2/` (2009-2026 except 2020, era-correct, manifest included). Every later NBA challenger comparison reruns both baseline and challenger under the corrected setup.
