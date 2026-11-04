# NHL simulator: overtime frequency and overtime winner edge. Rule, version 1

Written 4 Nov 2026 (Sydney), before any replay of this variant was run. Amendments are added below with dates; nothing above them is edited.

## Why
- `nhl_model.simulate` draws each team's regulation goals as independent Poisson. That sends about 16.5% of games to overtime/shootout at 5.6-6.3 goals a game.
- The real share was 21-25% in every season from 2014-15 to 2025-26 (games_<y>.json, OTL results).
- **Too few loser points.** On 4 Nov 2026 live projected points averaged 91.1 per team, against about 93.5 implied by this season's pace and history. Season points totals look about 2-3 points low, and the standings race is a little too spread out.
- **OT winner edge too strong.** A tied game is won by the home side with probability ndtr(m / 2.4), the full regulation edge. Three-on-three overtime and shootouts are much closer to a coin flip.
- TypeSafe chose this fix first (66%) in the 4 Nov independent review ("sound with fixable issues", 72%).

## Variant (research/replay_nhl.py: NHL_OT_FIX=1)
1. **Overtime frequency.**
   - Target = share of games that went to OT/shootout in the training seasons before y (walk-forward, from games_<y>.json).
   - In each simulation chunk, each game's Poisson tie probability b_g is computed from its expected goals.
   - c = target / mean(b_g); each game that is not tied in regulation becomes a tie with probability (c − 1) × b_g / (1 − b_g), clipped to [0, 1]. So closer games gain more ties, and the league rate matches the target.
   - A converted game gets goal difference 0. The draws come from a separate random generator, so all other draws are unchanged.
2. **Overtime winner.** A tied game is won by the home side with probability ndtr(0.5 × m / 2.4). The edge is half the regulation edge; 0.5 is fixed here before results.
3. Everything else is unchanged: ratings, playoffs (no ties in series) and tiebreakers.

**Sensitivity, reported only:** the frequency fix alone (OT edge 1.0), and OT edge 0.25.

## Baseline
The same replay settings as the other 4 Nov NHL tests:

`NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_PO_FADE=3 NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0 NHL_LINEUP_VAL=rapm RAPM_LAM=300000 RAPM_KBOX=1`

Seasons 2014-2018 and 2021-2025, 2,000 simulations.

## Scoring
- **Probabilities:** research/nhl_holdout.py, baseline first. Gain per market and combined, 90% bootstrap over seasons.
- **Points totals:** the replay now also writes projected mean points (pts_mean) and final points (y_pts). Bias = mean(projected − final) and RMSE, over all team-checkpoints, per variant.

## Decision
TypeSafe split evenly between "points only" and "points plus no harm on probabilities" (49% / 49%, confidence 0.24). The stricter of the two is used:
- **Pass:** all of
  - the absolute points bias is smaller than the baseline's;
  - points RMSE is not worse;
  - the combined log-loss mean gain is at least −0.0002;
  - no market's mean gain is below −0.0005.

  The fix then goes live in nhl_model.simulate (regular season only), with the target from all completed seasons.
- **Fail:** anything else. Live stays as it is.
- No re-tuning of 0.5 under this version.

## Amendments
(none)
