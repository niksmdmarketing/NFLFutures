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
