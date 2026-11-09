# News in futures (injuries, trades, return dates, team selection), all sports. Rule written BEFORE any build result (9 Nov 2026)
Owner: "Add it to all futures markets, including trades, injuries, every info that is relevant." TypeSafe (9 Nov): order news layer first (40%), then score the shadows (34%), then the honest history test (26%); rollout SHADOW FIRST in every sport (77%). Design: DeepSeek relays 026-027; Claude builds and checks. Prices are never inputs.

## Job 1: news layer (shared engine pipeline/news_adjust.py where a sport lacks one)
- Units: the sport's rating unit (points, goals), never probability.
- Cost per remaining game g a player misses: value x (missing share now - baseline share already reflected in the team rating), equal weight every affected game (DeepSeek's remaining/total factor dropped as double discounting; DeepSeek agreed 027).
- Absence draw per simulation: return_low/high (dates -> days, rounds -> games) uniform between bounds; class defaults: day-to-day 50% plays, else 1-3 games; test 0-1; weeks 3-8 weeks; tbc from the empirical distribution of collected records; season = rest of regular season plus playoffs.
- Trades/signings/releases: the player's value leaves one team's baseline and joins the other's (NBA: no second roster term; watch for the roster step moving the same team twice). NHL acquired-player term in the shadow only.
- Playoff carry-over: absences reaching the playoffs apply in playoff simulations; short ones revert.
- Caps: per player <= 0.25 sd of team ratings, per team <= 0.5 sd; clamp and log. Stale feed (> 12 h in season): no adjustment; a record unchanged 7 days past its return date is resolved.
- Null gate: empty news -> shadow identical to live (same sims and seed); all records resolved -> identical.
- Archive each refresh: <sport>/futures_news_shadow.jsonl (time, commit, news hash, per-team adjustment, with and without); NBA keeps nba/futures_shadow.jsonl.
- Per sport: NBA have values (nba_avail v2), add trades; NHL live already, add trades/acquired players as shadow; NFL QB only (archive the full QB engine), other positions archive only (no value source); AFL team selection via the Model D player lineup values, build before round 1 (March 2027); NBL archive only until NBL box scores exist.
- Live switch: only by TypeSafe after Job 2 scoring. Nothing in this rule changes a published number.

## Job 2: scoring the shadows
- Weekly (descriptive, no decision): null gate per sport; adjustment audit (max |dp_playoff| per team, capped records, stale hits); windowed check of implied vs realised win rate for games between consecutive snapshots.
- Season end (decision): paired (news - live) Brier for playoff qualification plus win-total MAE; unit team-season; bootstrap over teams, 10,000 draws; read once at the last snapshot before the playoffs. Pass needs the 90% upper bound <= 0 and a positive point estimate. Power, stated on every report: one season (30 NBA team-seasons) detects about 0.02 Brier; the plausible effect is under 0.005; one season cannot decide, three is marginal. TypeSafe choice at season end: continue shadow / promote / drop.

## Job 3: honest history test (EXPLORATORY, not pass-capable; seasons are spent)
- A player is out at a checkpoint once he has missed his team's last K = 3 games in a row while still on the roster (appears for no other team). Duration drawn per simulation from completed absence streaks in seasons strictly before the checkpoint season (refit each season, no leak). Return is not read from later box scores; when the draw expires he rejoins at full value. Report how often the draw brackets the real return (descriptive).
- Arms: live vs live + carry-forward, one per sport (family 2). NBA 2013-2026 (live replay seasons); NHL 2015-2025 needs the lineup cache (cannot run in the sandbox).
- Primary: IN-SEASON playoff and title log loss (correction by Claude: DeepSeek's 'preseason' cannot carry a K = 3 streak; the preseason checkpoint is unchanged by construction and is reported as a null check). Paired by season, season-block bootstrap. No-harm: no stage worse than live by more than 0.002 at the 90% bound.
- Falsification (overrides gains): worse on the check block in both sports -> the missed-games proxy is retired, not re-parametrised.

---
## Amendment 1 (9 Nov 2026): first results. Rule text above unchanged.
**Job 1, NBA facts found in the code:** in-season trades already move NBA futures live through the roster step (pipeline/nba.py _roster_adjustment: current roster vs last season's, coefficient 1.0 from game 20 on, ROSTER_FADE 0, so no fade). Injuries in futures already run as the shadow (nba/futures_shadow.jsonl). Nothing new built for NBA trades; the double-count check DeepSeek asked for (roster step plus results after a trade) stays open.
**Job 2, NBA audit (research/score_news_shadow.py, descriptive):** 370 snapshots 10 Oct to 9 Nov 2026; median largest playoff-chance move per snapshot 4.0 points (largest 7.9); mean move 1.1 points, 0.44 wins; latest biggest: MIN 0.83 -> 0.78, MEM 0.46 -> 0.50, GS 0.82 -> 0.79. Season-end decision unchanged (one season cannot decide).
**Job 3, NBA honest history test (research/replay_nba.py BT_CARRY=1, live flags, 1000 sims, 13 seasons 2013-2026 without 2020; null = live with the same flags):**
```
nba: seasons 2013-2026 (13), null null; IN-SAMPLE, EXPLORATORY. discovery < 2021 <= check
carry          pooled dLL -0.0002 | disc +0.0005 check -0.0012 | best season removed +0.0000 | worst cell second quarter/div +0.0045 (90% up +0.0073) | harm cells 15/45 | decision playoff@preseason: slope null 2.08 arm 2.08 contrast +0.000 [10% +0.000, 90% +0.000]
```
Primary (in-season playoff log loss): -0.0018 (carry better), 9 of 13 seasons better, check block 2021-2026 -0.0033. Mid-season -0.0026, last quarter -0.0020 (check -0.0048). Title flat (-0.0001). Preseason identical by construction (null check passes). No-harm fails as written: 15 of 45 stage x market cells have an upper bound worse than +0.002 (worst second-quarter division +0.0045).
Reading: EXPLORATORY (spent seasons). Falsification clause needs both sports worse on the check block; NBA is better on it, so the proxy is not retired. NHL arm still to run (needs the lineup cache via the GitHub Action). Nothing live changes.

## Amendment 2 (9 Nov 2026): builds per sport. Rule text above unchanged. DeepSeek designed and wrote the code (relays 028-033); TypeSafe chose order and decisions; Claude reviewed, corrected, tested.
- NBA trades: research/NBA_TRADE_DOUBLE_COUNT_RULE.md. Live now gives no roster-step credit for mid-season moves (TypeSafe 54%); old behaviour archived as tf_*.
- NFL: already built before today (pipeline/nfl_qb_shadow.py, shadow_qb_dated v2.1: injured starting QB replaced only for the games he is expected to miss). No other position has a value source; nothing added.
- NHL: acquired players are already a tested lever (replay NHL_LINEUP_C roster term; live goalie roster term); no second term added. Job 3 carry arm added to research/replay_nhl.py (NHL_CARRY=1; DeepSeek code with Claude's corrections: runs only within a player's spell, conditional chance still out, caching) and runs on GitHub (.github/workflows/nhl-job3.yml, results to branch research-results) because NHL data cannot be built in the sandbox. Live settings except RAPM lineup values (no cache on the runner); paired null vs carry.
- AFL: shadow in pipeline/afl_site.py (game_adj hook; news_adjustments; archive afl/futures_news_shadow.jsonl). Structural baseline: S already uses the previous-match lineup, so only a starter injured since, or a listed player returning, moves it; replacement = best non-lineup player. Needs pipeline/afl_model_d_contrib.json, exported off-site by research/afl_model_d_ratings.py (top 30 derived contributions per team only). Live from March only after scoring. Tests tests/test_afl_news.py.
- NBL: shadow in pipeline/nbl_news.py + nbl_site.py (game_adj hook; archive nbl/futures_news_shadow.jsonl). DeepSeek's 'blocked on data' was wrong: season player stats exist. Claude's corrections: this season included in values; only listed players count; per-game rounds. BETA 0.45 is NBA's, unvalidated for NBL (flagged in every archived row). Tests tests/test_nbl_news.py.
- Stores: refresh.yml sets AFL_INJ_STORE / NBL_INJ_STORE to the injury-monitor worktree and commits afl/ and nbl/ with the NBA archive.
