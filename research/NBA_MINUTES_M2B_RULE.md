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

