# Data freshness audit and process changes (15 Nov 2026, Sydney)

Owner request: check every model on the site is getting the latest data; say what is not, how to fix it, and how to improve the process. Decisions by TypeSafe; code for the status table by DeepSeek (relay ds050), checked and adjusted by Claude.

## What was checked (10:30 UTC, against real results)
| Model | Results in the model | Verdict |
|---|---|---|
| NFL | Week 9 complete + Thursday of week 10; injuries week 10; depth chart 15 Nov | Current |
| NHL | Through 14 Nov (all 14 games) | Current |
| NBA | Through 13 Nov; 5 games of 14 Nov missing | Normal lag: the source publishes once a day at about 12:30 UTC |
| NBL | Through 15 Nov | Current |
| College football | Through 14 Nov US | Current |
| College basketball (live v1) | Through 13 Nov | Same once-a-day source as NBA |
| Football (soccer) | Through 8 Nov; international break until 20 Nov | Current |
| AFL | Off-season, 2027 fixture | Current |

Injury feeds (NFL, NBA, NHL, NBL, AFL) all collected at 09:32 UTC with no failed source.

## Problems found
1. **Protected site missed its daily update on 5 of 9 scheduled days (7, 8, 9, 11, 12 Nov).** The private build ran 18-20 minutes against a 20-minute limit and was cancelled. Football stats take 10-13 of those minutes.
2. **Site refresh timing.** Scheduled every 2 hours; GitHub ran it about 3 times a day at irregular times.
3. **NBA paired futures archive (GPT's research job) has failed every day since 6 Nov.** It must run 11:15-12:00 UTC; GitHub starts it 17:00-22:00 UTC. One real bundle exists (4 Nov). Not a site model.
4. **College basketball shadows v3 (Torvik) and v4 (KenPom weekly) have no fresh input.** Torvik blocks GitHub (last snapshot 27 Oct); no weekly KenPom page has been saved. Both need the owner's browser.
5. **AFL news shadow is inactive** until the owner runs `research/afl_model_d_ratings.py` off-site (it writes `pipeline/afl_model_d_contrib.json`).
6. **PrizePicks NBA collector is blocked** (HTTP 403 since 5 Nov).
7. Nothing on the site showed how fresh each sport was.

## Changes made (TypeSafe)
- **Private build time limit 20 -> 35 minutes** (raise: 93% across the two raise options). Private repo, no extra build triggered.
- **Fixed-time site refreshes** (92%): the always-running NBA props loop job now also starts "Refresh site" at 01, 06, 13 and 19 UTC. The site's own schedule stays as the fallback. Public runner, free minutes.
- **Data status table** (90%): `pipeline/freshness.py` writes `data/freshness.json` each refresh; the Updates page shows it. "Behind" = a game played two or more days ago is still not in the model.
- **Private build start time: unchanged** (keep 56%, ask owner about a second build 26%). Moving it earlier would land before the 9am-Melbourne football gate.

## Left for the owner
- NBA paired archive: TypeSafe split 53% restart on time with a dated amendment vs 42% pause. No change made.
- Paper-test reference window: see the private repo note of the same date.
