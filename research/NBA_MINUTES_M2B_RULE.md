# NBA minutes M2b: fix the normal-night truncation. Rule written BEFORE any result (20 Oct 2026)

Follows the checks in research/NBA_MINUTES_TAIL_RULE.md. M2 fits its normal-night mean correctly (fringe players 16.91 against actual 16.97) but then cuts off the lower tail. That pushes the component's mean up, to 17.93 for fringe players. GPT and TypeSafe (98%) agree this is the minimal fix. No new features. Rebounds and assists v2 stay frozen, v1 stays archived, and any v3 is evaluated separately.

## The one change
For each player-game, the normal-night component is a discretised normal truncated to integer minutes k >= 0.6 x stage-one mean (and <= 53). Its location and scale are chosen so that **after truncation** its mean and sd equal the targets:
- target mean = M2's least-squares mean, fitted on earlier seasons' normal nights;
- target sd = M2's sd function, fitted on the same normal nights.

Method: moment matching through the truncated-normal relations, inverted numerically per player-game. Only earlier seasons are used, and nothing is a fixed subtraction. The short-night part, pi, the appearance probabilities and the fitting window (2017..s-1) are unchanged from M2.

## Checks before scoring (implementation)
On the earlier-season normal nights used for fitting, and separately on the test seasons:
- the component's mean after truncation must be within 0.3 minutes of actual normal nights, for both the fixed low-minute-risk group and other players;
- its sd must be within 10% of the actual sd of normal nights around the target mean.

If a check fails, that is reported as an implementation failure and nothing is scored.

## Gates
**Minutes:**
1. M2b passes M2's minutes gates against stage one: unconditional RPS 90% lower bound above zero; PIT deciles given appearing within 0.08-0.12.
2. M2b's unconditional RPS is not worse than M2's (point estimate).
3. On the fixed low-minute-risk group, M2b is closer to actual than M2 on both average minutes given appearing and P(under 15 minutes) (point estimates).

M2b replaces M2 only if all three hold.

**Points:** P+T with M2b against the original baselines (B3m with M2b), on all four original prop gates. The rule for its decision is unchanged.

**Rebounds and assists (v3 = v2 with M2b instead of M2):** v3 replaces v2 only if all three hold:
- RPS lower, with a 95% one-sided bound above zero;
- PIT deciles 0.07-0.13;
- smaller over gap on the fixed low-minute-risk group.

## Reported
- Fixed-group table (stage one / M2 / M2b / actual).
- Fixed and own confident-over groups by season.
- 6 hours before tip-off.

## Decision
The written gates decide; TypeSafe helps interpret. No live-model changes.

## Outcome (20 Oct 2026) - promising correction; failed the original adoption rule; not adopted
Run: research/nba_minutes_m2b_test.py (research/nba_minutes_m2b_results.json).

**Implementation check, as written: FAIL.**
- On the fitting seasons M2b passes everywhere:
  - fringe component mean within 0.07 minutes of actual normal nights;
  - other players within 0.13-0.28;
  - sd within 4%.
- On the test seasons the 0.3-minute tolerance is exceeded in some seasons: other players 2026 (28.86 against 28.39) and 2025 (+0.32), fringe 2024 (16.89 against 16.55).
- Those test-season gaps come from the forecast error of the target mean itself; M2's untruncated target is off by similar amounts there. They do not come from the truncation. The check was therefore mis-specified for test seasons. But the rule counts it, so this is recorded as an implementation failure, and M2b does not replace M2.

**Disclosure.** The script computed the checks and the scores in the same run, so the scores were seen. They are reported here as unscored context only, not as a test:
- minutes RPS M2b 0.059273 (M2 0.059558, stage one 0.059701);
- fixed fringe group: average minutes 13.80 (M2 14.48, actual 13.50), P(under 15) 0.550 (M2 0.477, actual 0.553);
- rebounds and assists v3 would meet the replacement conditions: low-minute-risk over gap rebounds 0.039 -> 0.008, assists 0.041 -> 0.020;
- points still fails calibration (lowest decile 0.142); fixed confident points overs 0.765 predicted against 0.651 (M2 0.779).

**Decision (written rule; TypeSafe 98%):** M2 and rebounds/assists v2 stay frozen.

## Clarification after GPT's review (20 Oct 2026; TypeSafe: forward route 68%, other points adopted 84-85%)
- **Label:** "promising correction; failed the original adoption gate". Not "proven improvement", not "disproved".
- **What the check mixed up:** calculation correctness and forecast accuracy.
  - The calculation fix works: truncation now preserves the fitted mean on the fitting data.
  - The 0.3-minute test-season tolerance measured forecast accuracy and was an arbitrary gate.
- **The seen results:** 2022-2026 results for M2b are development evidence, not an untouched confirmation. Development figures:
  - minutes RPS 0.059273 against M2 0.059558 (against stage one: 90% bound +0.000392);
  - rebounds v3 against v2: +0.000034 (95% bound +0.000023);
  - assists: +0.000024 (+0.000018).
  - An M2b-against-M2 interval was not computed in this run.
- **Policy on checks:** calculation checks use fitting data or mathematical identities. Forecast-performance checks still use held-out or future games.

## Forward test of M2b / v3 (written 20 Oct 2026, before any 2026-27 result)
- **Period:** the 2026-27 NBA regular season, opening night to the last regular-season game. **One evaluation, after the regular season ends.** Interim numbers may be shown only as labelled "interim" and decide nothing. The stopping point is fixed now.
- **Forecasts:**
  - v2 (M2 minutes) and v3 (M2b minutes) are produced at the same times from the same inputs: 1 hour before tip-off (main) and 6 hours, using the official report available at that time.
  - Both use the 2026-27 parameters fitted on 2017-2026 (model/nba_props_frozen.json).
  - Archived before tip-off. Any game whose forecast was not archived before tip-off is excluded from both versions and counted.
- **Minimum evidence:** 30,000 candidate player-games. If the season delivers fewer, the same rule continues into 2027-28.
- **Adoption (all must hold):**
  - **minutes:** M2b's unconditional RPS better than M2's, with a week-block 90% one-sided bound above zero;
  - **per stat (rebounds, assists, judged separately):**
    - v3's prop RPS better than v2's, with a 90% one-sided bound above zero;
    - v3's PIT deciles given appearing within 0.07-0.13;
    - a smaller over gap on the fixed low-minute-risk group. The group is defined from v2's minutes at forecast time, P(minutes < 15 | appear) >= 0.2.
- **Reported:** confident overs (fixed from v2 and own), by month; points with M2b (points has its own rule).


## Forward-test protocol details (20 Oct 2026, GPT review; before any 2026-27 forecast). Where it conflicts with the section above, this governs.
1. **The cutoff is the deadline, not tip-off.**
   - A "1-hour" forecast must be generated at or before tip-off minus 60 minutes, using only inputs retrieved by then. A "6-hour" forecast likewise, at tip-off minus 360 minutes.
   - Generation runs every 15 minutes. Every run inside [cutoff - 45 min, cutoff] produces and archives a forecast.
   - The forecast used for scoring is the latest one generated at or before the cutoff (pre-specified, not chosen afterwards).
   - A game with no forecast in that window has no valid forecast at that horizon. It is excluded from both versions and counted, with the reason (no run in window, data fetch failure, report missing, code error).
2. **Frozen, identifiable versions.** Each forecast record stores:
   - code commit and parameter file hash (model/nba_props_live_params.json);
   - model version (v2: M2 minutes; v3: M2b minutes; points with each, reported only);
   - generation time, and each input's retrieval time and content hash (schedule, official report file and its published time, box-score data);
   - the complete predicted distributions: appearance probability, minutes distribution, and the full points / rebounds / assists distributions.
   
   The method and parameters are frozen. Its inputs (completed games) naturally update.
3. **Primary and secondary.**
   - 1 hour is the primary test; 6 hours is secondary and decides nothing.
   - The 30,000 minimum counts distinct player-games with a valid 1-hour forecast. A player-game forecast at both horizons counts once.
4. **"Clearly better", defined now.**
   - **Score:** unconditional RPS as in the prop rule (points 0-60, rebounds 0-25, assists 0-20; minutes 0-53 as in stage one).
   - **Uncertainty:** paired differences, averaged per player-game. The bootstrap resamples whole calendar weeks (2,000 draws), so players sharing games and dates stay together. A second, team-season cluster bootstrap is reported; both one-sided 90% lower bounds must be above zero.
   - **Calibration:** randomised PIT deciles given appearing, all within 0.07-0.13.
   - **Subgroup:** the low-minute-risk group is determined game by game from the frozen v2 pre-game forecast (P(minutes < 15 | appear) >= 0.2 at that forecast) and shared by both versions. It is not a fixed list of players.
   - **Missing forecasts:** counts and reasons are reported.
5. **Replays.**
   - Games before the archive started, or missed by it, may be replayed from archived inputs as supplementary evidence only.
   - Replays never enter the adoption result, because archived injury reports alone do not guarantee every other input was available at the claimed time.
6. **TypeSafe.** Its percentages are decision support, not validation evidence. The written reasoning, implementation checks and archived results decide.

## Forward archive implementation (20 Oct 2026, before the first valid forecast)
**Code and parameters:**
- research/nba_props_live.py: live forecaster.
- research/nba_props_live_core.py: frozen fit and predict.
- model/nba_props_live_params_2027.json: sha256 4771633e…d2d1, fitted on 2017-2026, or 2020-2026 for stage one.
- .github/workflows/nba-props-forward.yml: every 15 minutes, 10:00-05:59 UTC.
- Output: forecast-archive branch, nba/props_forward/<US date>/<game>_<horizon>_<run>.json.gz, run logs in .../runs/, fetched official reports in .../reports/. Manual test runs go to .../tests/ and are never scored.

**Calculation checks (fitting data and identities):**
- The frozen parameters reproduce the research fits exactly when refitted for 2026: stage one differences < 1e-14; M2 and M2b distributions < 1e-16; prop fits identical.
- An offline replay (HOU-LAC, 10 Feb 2026, 1-hour forecast) reproduces the research candidate features exactly for the 34 research candidates (stage one within rounding).

**Differences from the research pipeline, fixed now:**
1. The expected margin input to M2's short-night probability uses the team rating fitted on games before the forecast day, without the injury term (the research used the weekly checkpoint with the injury term). Replay effect: M2/M2b minutes probabilities differ by up to 0.03 per minute value, and prop means by up to 0.05 points.
2. Expected pace uses the same day-level rating (replay difference about 0.01 possessions).
3. The short-night share uses the player's last 20 appearances before the game. The research carried the value forward to non-appearance rows, omitting the latest appearance; the pi model was fitted on appearance rows, which use the live definition.
4. Only completed games enter. The research processed games in tip-off order, so a same-day trade could remove a player from his old team's candidates once his new team's game had started (a small look-ahead). The replay keeps him as a candidate.
5. Opponent factors for the forecast game use all completed games. The research's tip-order processing could include the other team's row of the same game.
6. In the current season, an injury-report name not yet matched to a box score this season is matched through last season's names (unique matches only), so listed players can be candidates before their first game.
7. As in the research, candidates are players who have appeared for the team this season plus players on the report in use. On opening night only listed players are candidates; season debuts are not scored (stage-one limitation).
8. Box scores come from the SportsDataverse release. Completed current-season games missing from it are filled from ESPN game summaries. Each record logs which games were filled or failed.

## Archive requirements after GPT's review (20 Oct 2026, before the first valid forecast). Status: built and smoke-tested, not yet verified in live operation
1. **Coverage.** Each forecast record lists, for each team:
   - roster size (ESPN roster file);
   - players forecast;
   - players on the injury report;
   - roster players excluded because they are not candidates (season debuts, unseen players);
   - forecasts for players not on the roster.
   
   Early-season reports give eligible players, forecasts captured and exclusions separately. Debut and fallback players stay outside the test until they have their own validation.
2. **Reproducibility.** Every input actually used is stored as an immutable, content-addressed copy, nba/props_forward/inputs/<sha256>.<ext>:
   - schedule;
   - roster;
   - player and team box scores, with exactly the columns used and ESPN fills included;
   - market-data report files;
   - the official report PDF.
   
   Each record lists those hashes, and records its forecast-finished time and its age at the cutoff.
   - **Archive time:** the archive time of a forecast is the completion time of its run's Save step, as recorded by GitHub's Actions API. It is captured by research/nba_props_forward_timing.py, twice daily, into nba/props_forward/timing/. It is not the run's own clock.
   - **Qualifying:** a forecast qualifies only if that recorded time is at or before its cutoff. No self-reported or backdated timestamp can make a late capture qualify.
3. **Paired check (in every record).** v2 and v3 are computed from the same rows (same players, same eligibility), with one input hash. The short-night probability is identical (max difference recorded; 0 in the replay). The minutes mass below the short-night threshold is identical (0 in the replay). Only the normal-night part differs, which is the intended correction. The live-versus-research differences listed above apply equally to both versions.
4. **Schedule reliability.** GitHub's 15-minute schedule is not a guarantee. For the first nights, a review will report:
   - actual run times against the schedule;
   - each selected forecast's age at the cutoff;
   - input freshness (latest completed game included per team, report time);
   - every missed window.
   
   The archive is not relied on before that review.
5. **Uncertainty definition.**
   - **Team-season cluster:** each player-game belongs to the team-season of the team he was forecast for. A traded player's games split across his teams, and the two teams of a game sit in different clusters even though they share the game.
   - **Week bootstrap:** resamples whole calendar weeks across the league.
   - These are two robustness checks on the same results, not independent confirmations. Both bounds must be above zero.
6. **Research bug found during the live checks (20 Oct 2026).** The league's injury report uses team codes NYK, SAS, GSW, NOP, UTA and WAS; ESPN uses NY, SA, GS, NO, UTAH and WSH.
   - The 2020-2025 report files carried no code, so team names mapped correctly. The 2026 file carried the league codes, so in the research's 2026 season those six teams never received report statuses (listed share 0.0 against 0.30 for the other teams).
   - **Affected results:** every stage-one, M2, M2b and prop result for the 2026 test season, for those six teams (6 of 30 teams in 1 of 5 test seasons). Models and baselines were affected alike.
   - **Live forecaster:** maps the codes (the fix applies to the 2026 history rows it builds as well).
   - **Correction:** a corrected re-run of the historical tests is to be done and reported as a disclosed correction alongside the originals, which are kept.
