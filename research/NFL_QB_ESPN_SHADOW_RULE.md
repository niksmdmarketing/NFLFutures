# NFL futures: injured starting QB only for the games he is expected to miss (ESPN return dates). Shadow rule, version 1

Written 4 Nov 2026 (Sydney), before any shadow output was produced or seen. Amendments are added below with dates; nothing above them is edited.

## Why
- Live v4 (`pipeline/ratings.py`) reads next game's official status. If the depth-chart starter is Out or Doubtful, the backup takes **every remaining game** (qb_adj on the whole rating). v5 instead keeps the starter in every game.
- The perfect-knowledge test (research/NFL_QB_ORACLE_RULE.md) gained +0.0064, but most of that comes from knowing future injuries and benchings, which no live input can know.
- The news-timing test (research/NFL_QB_NEWS_RULE.md) gained +0.0007 over no adjustment, inside the noise, and did not beat the whole-season shortcut.
- So the expected gain is small. This shadow is mainly a common-sense correction (a QB on IR for four weeks should not be priced as out for the season). It goes live only if the forward record supports it.
- TypeSafe chose the ESPN-feed shadow over manual overrides or leaving it (67%) and chose the strict gate below (57%).

## What the shadow does
Everything is identical to live v4 except injury-driven QB changes.

**Episode.** A team has an episode when its reference QB (most dropbacks this season, as in v4) is, at run time:
- listed by ESPN's NFL injuries feed (`site.api.espn.com/apis/site/v2/sports/football/nfl/injuries`) as Out, Doubtful, Injured Reserve, Physically Unable to Perform or Suspension; or
- listed Out or Doubtful on the latest official report in nflverse (the report v4 already reads).

Matching ESPN rows to QBs is by normalised name within team.

**Replacement.** This is the highest-ranked QB on the latest depth chart other than the reference QB. His value comes from `ratings.qb_values`, exactly as in v4.

**Games missed.** One draw per simulated season and episode:
1. **Season-ending.** ESPN detail or injury text says out for the season, or ACL / Achilles with no date: he misses every remaining game.
2. **ESPN return date in the future.** Return day = run date + lognormal(median = days until the date, sigma 0.45). This is the NBA layer's RETURN_SIGMA, reused rather than fitted. He misses team games kicking off before that day.
3. **No usable date.** Draw from the historical incumbent-QB absence runs (research/qb_news/absence_runs.csv, 2013-2025). Draws are conditioned on runs longer than m, the consecutive team games he has already missed (from play-by-play: latest games with zero dropbacks), and, if on IR or PUP, at least 4. Remaining games = draw minus m, at least 1. If no run meets the condition, he misses every remaining game.

**Per game.** In a missed game, the team's margin moves by rating_scale × lambda × (replacement value − reference value). It is added to the home margin with the right sign, through `simulate(adj_sims=...)`. The whole-season qb_adj is removed for that team. Teams without an episode keep v4's qb_adj unchanged, including non-injury depth-chart changes.

**Not covered in version 1, disclosed:**
- a non-reference QB returning from injury (for example a regular starter coming back after the backup became the reference QB);
- Questionable listings;
- returns earlier than the date.

**Live futures are not changed.** The shadow is written to futures.json as `shadow_qb_dated` and archived with every run (pipeline/archive.py), next to `challenger_v5`.

## Scoring (forward, 2026 regular season)
- **Checkpoints:** the first archived snapshot after the last game of each week, from the first week the shadow runs through week 18.
- **Markets:** division, playoff, No. 1 seed, conference, Super Bowl.
- **Score:** mean log loss over all 32 teams per market, clipped at 0.002 and 0.998.
- **Primary:** gain = v4 log loss − shadow log loss, averaged over the five markets and the checkpoints. A 90% interval comes from a bootstrap over checkpoints (4,000 draws, seed 1).
- **Reported:** gain per market, the number of episodes that changed a forecast, and how many had an ESPN date, a no-date draw or a season-ending call. The owner's main betting market is reported separately once he names it; it is not a gate.

## Decision
- **Go live:** the 90% interval of the primary gain is above zero, and at least 3 episodes changed forecasts. Live then uses the dated rule for injury-driven QB changes; v5 is decided separately.
- **Otherwise:** the shadow stays a shadow. It is re-scored together with the 2027 season under this same rule. No re-tuning of sigma, the conditioning or the replacement rule under this version.
- **Stop early:** if, by week 12, ESPN's feed has given no return date for any QB on the official report Out or IR list, the shadow is reported as not workable and switched off.

## Amendments
(none)
