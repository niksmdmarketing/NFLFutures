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
- **Fixed-time site refreshes** (92%): the always-running NBA props loop job now also starts "Refresh site" at 01, 06, 13, 19 and 22 UTC. The 19 and 22 slots put a model snapshot within 3 hours before the daily Australian title-price capture (title paper test; TypeSafe 100%: fix the timing, keep the 3-hour window). The site's own schedule stays as the fallback. Public runner, free minutes.
- **Data status table** (90%): `pipeline/freshness.py` writes `data/freshness.json` each refresh; the Updates page shows it. "Behind" = a game played two or more days ago is still not in the model.
- **Private build start time: unchanged** (keep 56%, ask owner about a second build 26%). Moving it earlier would land before the 9am-Melbourne football gate.

## Left for the owner
- NBA paired archive: TypeSafe split 53% restart on time with a dated amendment vs 42% pause. No change made.
- Nothing else. The paper-test reference window was settled (kept at 3 hours; see the private repo note of the same date).

## Update, 16 Nov 2026
- **NBA paired futures archive restarted** (owner decision, 15 Nov; TypeSafe 98% on the design). The 15 Nov bundle was made by hand inside the window (received 11:18:09 UTC, eligible). 15 earlier cutoffs are recorded as missing in a ledger and counted, never backfilled; the daily check passes again and still fails on any new miss. From 16 Nov the loop job starts the collector at 11:16 UTC. Rule: Amendment 1 of `NBA_DATED_ABSENCE_FORWARD_RULE.md` on branch `claude/nba-paired-archive-restart-20261115`.
- **First night of the fixes:** fixed-time refreshes started at 19:01, 22:01 and 01:01 UTC. The private build took 20.4 minutes and finished (the old limit would have cancelled it). The 15 Nov title-price capture (20:22 UTC) had a model snapshot 1h09 earlier: 0 of 188 paper-test opportunities failed the 3-hour window (188 of 188 failed on 14 Nov).
