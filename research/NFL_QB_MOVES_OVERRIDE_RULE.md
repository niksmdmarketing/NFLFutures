# NFL v4: confirmed QB moves before nflverse catches up (rule, 11 Nov 2026, Sydney)

Written before the refresh that applies it. Decided by TypeSafe (override 99%; non-QB trades left unmodelled 98%).

## Problem
The v4 QB layer takes QB1 from the nflverse depth chart. Its latest snapshot (10 Nov 15:32Z) is older than the 10 Nov 4pm ET deadline trades, so it still shows Cousins at LV and Murray (Out) at MIN.

## Rule
- `pipeline/nfl_qb_moves.json` lists confirmed QB1 changes. A change goes in only when at least two major outlets report it (trade done, or starter named or expected).
- An entry applies only while that team's latest depth-chart row is older than the entry's `as_of`. After that, nflverse wins, so no entry ever goes stale.
- The injury check still applies: if the new starter is listed Out or Doubtful, the entry is ignored.
- A QB with no NFL dropbacks gets the model's usual replacement-level value. Nothing is hand-set.
- Prices are never used.

## Entries (11 Nov 2026)
- MIN: Kirk Cousins (traded from LV; expected to start ahead of Wentz, with Murray out with a hamstring injury). Sources: ESPN, AP/Yahoo.
- LV: Fernando Mendoza (rookie, now the starter). Sources: Las Vegas Review-Journal, Fox.

## Not changed
Non-QB deadline trades (Downs, K. Allen, J. Davis, Bates, Neuzil, Henley, Hooker, Cisco, Godchaux, etc.) are not modelled by v4. The non-QB layer was tested and closed (research/NFL_NONQB_INJURY_RULE.md).
