# NFL: do untested team stats improve the rating? Rule written BEFORE any result (20 Oct 2026)

Asked by the user: repeat the AFL comparison for sports with deep data. TypeSafe chose NFL first (87%, re-asked after noting that NFL is already a team-stats model).
What already exists, so it is not redone: the NFL rating is already built from opponent-adjusted team stats (pass and rush EPA and success rate, sacks, special-teams EPA, SRS, with recency; model/v5_notes.md), and a play-level player model from participation data was tested on 14 Oct 2026 and gave no gain with strictly pre-game lineups. The open question is the play-by-play stats that have never been tried.

## Models (pipeline/nfl_engine.py machinery, unchanged)
- A: the v5 candidate inputs: recency half-life 4 weeks, team-effect shrinkage 60 (cached run nfl_eng_h4a60).
- B: A plus six new opponent-adjusted offence/defence components, each built exactly like the existing ones (ridge team effects, same recency, same current/prior-season blend by play counts using the pass group's k):
  1. turnover rate per scrimmage play (interceptions + lost fumbles)
  2. explosive play rate (pass 15+ yards, run 10+ yards)
  3. havoc rate (turnover, sack, tackle for loss or pass breakup)
  4. third/fourth-down conversion rate (first down or touchdown on 3rd/4th-down plays)
  5. red-zone touchdown rate (touchdown on plays starting inside the opponent's 20)
  6. QB hit rate per dropback
Both use the same game-level walk-forward ridge (pipeline/nfl_engine.py score): test season s is fitted on 2010..s-1 only.

## Test
Regular-season games 2013-2025 (13 walk-forward seasons, about 3,500 games). Every game uses only plays from earlier weeks.

## Gates (B against A, all must pass)
1. Mean win log loss over the 13 seasons lower, with a season-bootstrap (2,000 draws) 90% interval for the gain above zero.
2. Lower log loss in at least 9 of 13 seasons.
3. Lower mean margin RMSE.
4. Late-season (week 10+) RMSE not worse.
Reported: per-season gains; the fitted weights of the new components.

## Decision
TypeSafe decides. Pass: the components go into the v5 candidate (weights refitted on 2010-2025, shown in shadow beside v4); v4 stays live through 2026 by the standing rule. Fail: recorded and unused.

## Outcome (20 Oct 2026) - fails all gates; not adopted
Run: ENG_ALPHA=60 ENG_EXTRA2=1 python pipeline/nfl_engine.py x2h4a60 4 0, then research/nfl_extra_stats_test.py (results research/nfl_extra_stats_results.json).
Log loss A 0.6368, B 0.6413 (gain -0.0045, 90% -0.0092 to -0.0007); better in 5 of 13 seasons; margin RMSE 13.32 vs 13.43; late RMSE 13.39 vs 13.54.
Reading: once EPA and success rate are in, turnovers, explosives, havoc, conversions, red-zone TDs and QB hits add noise, not signal (turnovers and red-zone rates are known to be mostly luck week to week).
Decision (TypeSafe 99%): recorded; NFL rating unchanged (v4 live, v5 shadow as is). TypeSafe (81%) then advised stopping the cross-sport comparisons for now.
