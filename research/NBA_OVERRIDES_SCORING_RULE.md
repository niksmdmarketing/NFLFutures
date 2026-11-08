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
