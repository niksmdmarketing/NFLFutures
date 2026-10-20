# NBA single games: player term against the complete live pipeline. Rule written BEFORE any result (21 Oct 2026, Sydney)

Asked by the user ("do it", after TypeSafe ranked this first, 83%). Follows research/NBA_PLAYER_FIRST_RULE.md.
That rule found that the player term helps single games on top of the team rating (+0.93% margin MSE) and on top of the availability layer (+0.3-0.4%). Its known weakness 1 is that the baseline was the team rating alone, not the live pipeline: the live ratings also carry the roster step and the pre-season player mix (fading to zero by game 20). This test closes that gap. Nothing live changes from it.

## Versions (identical except for the in-season rating)
- **L (live):** the weekly point-in-time replay of the live ratings (research/replay_nba.py with BT_FULL=1: team rating, roster step, pre-season RAPM mix with development, current-season weight 8, decay 0.2).
  - Game margin exactly as the live page: (rating_home - rating_away + HFA) x (pace_home + pace_away) / 200 - 0.45 x (availability_home - availability_away).
  - Win probability = Phi(margin / GAME_SIGMA).
  - No recalibration (the live numbers have none).
- **PT (challenger):** identical, except that from the first checkpoint with games played the rating becomes (b / b_A) x rating + (c / b_A) x (S - mean S).
  - This is replay_nba.py BT_PF=2, the same formula as the live 2026-27 shadow (pipeline/nba.py _player_term_shadow).
  - S = RAPM strength of each team's usual rotation over its last 10 games before the checkpoint (absences as zero, players since traded dropped, scaled to 240).
  - Weights b, c, b_A are the walk-forward weights for that season (research/nba_player_first_results.json, fitted on earlier seasons only).
- The pre-season checkpoint (week 0) is identical in both, so it is excluded from scoring.
- No setting, weight or form is searched here.

## Games and availability
- Each regular-season game is predicted from the latest weekly checkpoint before its date (inputs strictly before the checkpoint), as in the earlier rule.
- **Primary:** seasons 2022-2026, games covered by official pre-game injury reports, availability = v2_official (the live input; nba_avail2_games.csv from research/nba_availability2.py).
- **Robustness:** seasons 2015-2026, availability = v2_base (before 2021 it uses who actually played, so it is generous to both versions alike). 2020 is included for games (the replay's futures skip it; ratings are still fitted).

## Scores
- Win log loss (primary), margin MSE, calibration slope (logistic regression of the result on logit p).
- Paired PT-minus-L differences per game; week-block bootstrap (2,000 draws).
- Reported by season, and for early games (both teams with at most 20 games played) and later games.

## Gates (all must hold for PT)
1. **Primary log loss:** PT lower than L, with a one-sided 90% week-block lower bound of the gain above zero.
2. **Seasons:** PT has lower log loss in at least 4 of 5 primary seasons.
3. **Margins:** PT's primary margin MSE is not higher than L's (point estimate).
4. **Early and late:** on the primary games, PT is not worse than L in log loss for either early or later games (point estimates).
5. **Calibration:** PT's primary calibration slope is between 0.8 and 1.2.
6. **Robustness:** on 2015-2026 PT's log loss is not higher than L's (point estimate).

## Decision (TypeSafe, recorded before results)
- **PT fails:** recorded; the live game numbers stay; the player term stays a futures-only archived shadow.
- **PT passes:** it becomes the single-game challenger "G-PT1" for 2026-27.
  - Archived before tip-off beside the live probability and margin (same file and timing as the Forecast > Games record), with its weights file hash.
  - Not shown on the site while being tested (TypeSafe 91%); the published numbers stay L.
  - **Adoption at season end** (TypeSafe 99%): PT replaces L for the published game numbers if, on the 2026-27 forward games scored on pre-tip-off forecasts, its log loss is not worse than L's (point estimate) and its calibration slope is between 0.8 and 1.2. A 90% week-block interval of the gain lying entirely below zero blocks adoption.
  - One season cannot confirm a gain this small; the adoption rests on the historical result plus a forward check that it is not worse, and is labelled that way.
- Futures are not affected either way (the futures test failed; research/NBA_PLAYER_FIRST_RULE.md).

## Outcome (21 Oct 2026) - PT fails; the live game numbers stay
Run: research/nba_games_pt_test.py (checkpoints data/research/nba_games_pt_ck_<y>.json; results research/nba_games_pt_results.json). One code bug was fixed before any score: a wrapper re-wrapped itself across seasons (multi-season builds crashed), so every season was rebuilt one per process.

| | Games | Log loss L / PT | Gain (PT better if positive) | One-sided 90% bound | Seasons better | Margin MSE L / PT | Calibration slope L / PT |
|---|---|---|---|---|---|---|---|
| Primary, 2022-2026 official reports | 5,897 | 0.60752 / 0.60827 | -0.00076 | -0.00165 | 2 of 5 | 188.53 / 188.27 | 0.983 / 0.923 |
| Robustness, 2015-2026 v2_base | 13,848 | 0.60681 / 0.60688 | -0.00007 | -0.00057 | 8 of 12 | 171.44 / 171.40 | 0.993 / 0.955 |

- Primary by season: 2022 +0.0015, 2023 -0.0016, 2024 -0.0002, 2025 +0.0006, 2026 -0.0041. Early games -0.0006, later -0.0008.
- Gates: 1 (log loss bound) fail; 2 (4 of 5 seasons) fail; 3 (margin MSE) pass; 4 (early and later) fail; 5 (calibration slope) pass; 6 (robustness) fail.
- **Reading.** Against the complete live pipeline the player term no longer helps. Its margins are marginally more accurate, but its probabilities are slightly over-confident (slope 0.92): it widens rating gaps while the game spread stays fixed. Most of its earlier gain against the bare team rating is already carried by the live roster step, pre-season player mix and availability layer (weakness 1 of the earlier rule, now confirmed).
- **Decision (written rule; TypeSafe was unavailable when this was recorded).** Recorded as a fail. The live game numbers are unchanged. The player term stays a futures-only archived shadow. A rescaled version would be fitted after seeing these results, so it is not tried under this rule.
