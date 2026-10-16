# NBA roster-adjustment fade: decision rule written BEFORE any fade result (16 Oct 2026)

Question: should the preseason roster adjustment fade out as current-season games accumulate (the team rating increasingly
reflects the new players, so a full-strength adjustment may count them twice)?

Variants (corrected, era-aware replay 2013-2026 without the 2019-20 bubble; research/replay_nba.py, BT_ERA=1, 2000 sims):
- main roster replay (BT_FULL=1): optimistic, because a player's current team is his first team of the season (later signings backfilled)
- NOLEAK roster replay (BT_FULL=1 BT_FULL_NOLEAK=1): conservative but incomplete (rookies, offseason signings and players who never play are misplaced)
- team-only replay (BT_FULL=0): cleanest common benchmark
- fade rate F in {0.5, 1.0} = share of the roster adjustment removed by game 82 (linear); live = 0. Chosen before looking at results.

Deploy a fade only if ALL hold:
1. Combined race log loss (title, conference, division; plus the replay_score markets) improves in the primary sample (without 2020-21).
2. The gain has the same sign in the main AND the NOLEAK roster replays.
3. It is better in a majority of held-out seasons.
4. Preseason performance does not worsen materially.
5. The improvement survives nested (leave-one-season-out) selection of the fade rate.
6. The result is not driven exclusively by 2020-21 (sensitivity sample agrees).
7. The chosen fade approaches zero roster adjustment as current-season games accumulate (F = 1.0 reaches zero at game 82).
Otherwise keep the current model and label the roster adjustment an unvalidated preseason overlay.

Also: the roster term cannot be cleanly back-tested without a dated transaction/roster history; the variants above only bound it.
Race scoring also reports the raw probability sums before normalisation (title 1, conference 1 per conference, division 1 per division).

## Outcome (17 Oct 2026; research/nba_fade_decision.py; TypeSafe 68% keep live, confidence 0.52)
Era-correct replay 2013-2026 (no bubble), 2000 sims. Combined race log loss gain of a fade over the live model (positive = better), primary 12 seasons (no 2020-21):
main f05 -0.0075 (5/12), f10 -0.0213 (3/12); NOLEAK nf05 -0.0078 (4/12), nf10 -0.0182 (3/12); with 2020-21 the same sign (-0.0047/-0.0153; -0.0050/-0.0130).
Preseason unchanged (a fade acts only from game 1 on). Binary markets +0.0008 to +0.0013 (not the rule's primary). Nested leave-one-season-out selection picks no fade in every season.
Conditions 1, 3 and 5 fail: fade REJECTED, roster adjustment stays at full strength all season and stays labelled an unvalidated preseason overlay.
Roster layer v team-only (race loss, all checkpoints): +0.084 main, +0.075 NOLEAK (better); worse than team-only in 2014, 2021 and 2025. Trust ratings not changed.
