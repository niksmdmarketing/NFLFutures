# NBA owner overrides: how the season scores them. Rule, version 1

Written 8 Nov 2026 (Sydney), before any outcome that could score them. The overrides (model/nba_overrides.json, 2 players with projected minutes/rating, set 15-16 Oct 2026) are judgement, not replayed. Every refresh archives the forecast with them (p_*) and without them (n_*). This rule fixes how those are compared at season end. Amendments below with dates; nothing above them is edited.

## What is compared
Archived pairs per team per refresh date: playoff chance (p_playoff vs n_p_playoff), conference-final chance (p_conf vs n_p_conf), title chance (p_title vs n_p_title). Only refresh dates on or after the first archive containing n_* fields count; dates before are not scored.

## Known limits, stated now
- The "without" run uses 20,000 simulations; the live run 100,000, same seed but different batch sizes, so the draws are NOT shared. Monte Carlo noise in the paired difference is about 0.23pp at a chance of 0.10 and 0.35pp at 0.50 (arithmetic: sqrt(p(1-p)/20000 + p(1-p)/100000)). Per-team differences under about 0.7pp are unreadable.
- A season gives ONE title winner. Title scoring is therefore descriptive only: the winner's p and n, no interval, no decision.
- Teams within one season are correlated (one schedule, one outcome set). A bootstrap over teams treats them as independent and understates uncertainty; any interval is labelled that way.

## Primary measure (decides)
Paired playoff-qualification log loss, averaged over the refresh dates, across 30 teams: mean LL(n_p_playoff) - mean LL(p_playoff), positive meaning the overrides helped. Report per refresh date and the average. 90% interval by bootstrap over teams (4,000 draws, seed 1), labelled optimistic.
Secondary, same construction: conference-final chance (outcome: reached the conference finals).
## Decision
- The overrides stay if the primary difference is above 0 or its interval contains 0 (no-harm).
- They are removed (a dated amendment, a version change and the no-harm measurement at N=2000, per the four-agent plan) only if the primary interval is entirely below 0 AND the measured Monte Carlo noise is smaller than the point difference.
- If the point difference is smaller than the noise floor above, the report says "unreadable" and nothing changes.
- No result is read before the regular season ends (games complete); mid-season looks are descriptive and spend no decision.
## Confound to state with every report
The overrides went live 15-16 Oct, before opening night. The archive starts the "without" version at the same time, so no pre-override period exists; the comparison is a paired difference between two forecasts made at the same time, not a before/after.

## Amendment 1 (8 Nov 2026, after DeepSeek's review, relay 011; before any outcome)
- **Arithmetic corrected:** noise of the difference at a chance of 0.50 is 0.39pp (sqrt(0.25/20000 + 0.25/100000) = 3.87e-3), not 0.35. 0.10 gives 0.23pp. The two runs share no draws, so this is an unpaired difference; "paired" above means same team and date, not shared simulation.
- **Power, stated plainly:** for a team near 0.5, a shift of dp in playoff probability gives an expected log-loss gain of about 2dp^2 with per-team spread about 2dp, so the t-statistic over m affected team-seasons is about dp x sqrt(m). At dp = 2pp and m = 3, t is about 0.03; clearing 1.6 needs m of about 6,400 at 2pp or 260 at 10pp. Averaging over refresh dates adds nothing because the outcome is the same at each date. The "primary measure" above therefore CANNOT confirm or refute a real 2-5pp effect from two overridden players and is DESCRIPTIVE ONLY. The previous "removed only if" clause is withdrawn; no removal can come from outcome scoring.
- **Report with any outcome comparison:** the number of team-seasons with |dp playoff| >= 1pp and the largest |dp| (open: not available in this environment, because the NBA forecast archive is written on the build side; to be read from the first archive pull), the number of non-zero team differences, and bootstrap clusters by team-season. Teams' playoff outcomes are negatively dependent (16 of 30 qualify), so any interval is stated as approximate.
- **Where a correct answer is obtainable:** the mechanism. A deterministic check that the projected-minutes override reaches the player and team rating by the intended amount, on the dates intended, with no stale-input fallback. That check is registered as the validation of the overrides; outcome scoring is descriptive.
- **Action in the unreadable cell (non-outcome reason, set now):** the overrides are the owner's judgement (15-16 Oct 2026, TypeSafe and GPT consulted), not a corrected input error and not an accuracy claim backed by evidence. They stay on at the owner's direction, labelled "unvalidated judgement" everywhere they appear, and nothing is claimed about their benefit. The version string carries the date.
- **Not to do:** raising the no-overrides run to 100,000 simulations would cut noise to 0.13pp (p 0.10) and 0.22pp (p 0.50) but does not change the power problem, which is the binary outcome; it is not worth the compute and must not be presented as a fix.
