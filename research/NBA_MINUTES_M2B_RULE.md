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
