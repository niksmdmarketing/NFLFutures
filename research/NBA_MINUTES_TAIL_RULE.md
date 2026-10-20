# NBA minutes: short-night tail correction (points first). Rule written BEFORE any result (20 Oct 2026)

Follows research/NBA_PROPS_SIMPLE_RULE.md (outcome and diagnostics). Points beat every baseline but failed calibration. With actual minutes the low tail mostly disappears (PIT lowest decile 0.161 -> 0.131), and so does the over-probability gap for players at risk of short minutes, for all three stats. So the targeted correction is to the minutes distribution given appearing: stage one's single normal has too little mass on short nights.

The frozen versions are unchanged: stage one, and rebounds P+O and assists P+T (model/nba_props_frozen.json). Everything here creates new versions, evaluated separately.

## Model change (one change only)
Minutes given appearing become a two-part mixture:
- **Short night**, with probability pi:
  - minutes = round(ratio x stage-one mean), with ratio drawn from the empirical distribution of (minutes / stage-one mean) among short nights in earlier seasons;
  - a short night is an appearance with minutes < 0.6 x stage-one mean;
  - clipped to 1..53.
- **Normal night**, with probability 1 - pi: the stage-one discretised normal, with its mean and sd refitted on the earlier seasons' non-short appearances only, so the tail is not added twice.
- **pi**, from a logistic regression fitted on earlier seasons' appearances, with these fixed pre-game inputs:
  - stage-one mean minutes;
  - report status at the forecast time (Questionable, Probable, Available-listed, unlisted);
  - expected absolute margin of the game (the live model's margin, research/nba_game_env_test.py games table), for blowout risk;
  - team back-to-back;
  - the player's short-night share over his last 20 appearances (shrunk to the league rate with prior weight 10);
  - early season (team games 1-10).

Appearance probabilities are unchanged (stage one). Seasons, forecast times, walk-forward fitting (2017..s-1 for test season s; stage-one inputs as frozen), population and bootstrap are as in the prop rule.

## Versions evaluated
- **M2**, the revised minutes model, against stage one, on minutes.
- **Points:** P+T with M2 (and B3m with M2, so the minutes-matched baseline shares the new minutes), against the same baselines as before.
- **Rebounds P+O and assists P+T with M2:** compared with the frozen versions (separate decision below).

## Gates
**Minutes (M2 vs stage one, 2022-2026, 1 hour before tip-off):**
1. Unconditional minutes RPS lower, with a week-block bootstrap 90% one-sided lower bound above zero.
2. Every PIT decile of minutes given appearing between 0.08 and 0.12. Stage one's lowest decile was 0.132.

**Points (P+T with M2):** all four original prop gates against B1, B2, B3 and B3m (B3m with M2):
- 90% lower bound;
- 4 of 5 seasons;
- PIT deciles 0.07-0.13 given appearing;
- conditional RPS better.

**Rebounds and assists replacement:** a revised version replaces the frozen one only if all three hold:
- unconditional RPS lower than the frozen version, with a one-sided 95% lower bound above zero (two stats, 10% familywise);
- PIT deciles within 0.07-0.13;
- the low-minute-risk over gap is smaller (point estimate).

Otherwise the frozen version stays.

## Reported
- Over/under calibration overall and for low-minute-risk players (P(minutes < 15 | appear) >= 0.2 under each version's own minutes).
- Confident overs (p >= 0.8) by season.
- 6 hours before tip-off.
- Fitted pi coefficients.
- The short-night ratio distribution.
- Points with actual minutes, as the diagnostic ceiling.

## Decision
The written gates decide; TypeSafe helps interpret.
- **M2 passes the minutes gates and points passes:** points P+T with M2 joins the frozen forward test, with the same label and a subgroup check.
- **M2 passes, points fails:** M2 is recorded. Points' remaining production-dispersion issue gets its own rule.
- **M2 fails:** recorded. Nothing changes.

## Amendment 1 (20 Oct 2026, before any code or result): GPT's review. Where it conflicts with the text above, this governs.
1. **Fixed comparison groups.**
   - The low-minute-risk group is defined once, from the frozen stage-one minutes: P(minutes < 15 | appear) >= 0.2. The same player-games are used for stage one and M2.
   - The confident-over group is also fixed once, from the current versions: stage-one minutes with P+T for points, P+O for rebounds, P+T for assists, p(over) >= 0.8 at the formula line.
   - The replacement condition "low-minute-risk over gap smaller" uses the fixed group.
   - Each model's own groups (defined under its own forecasts) are reported separately.
2. **The normal-night component excludes short nights.** Its support is restricted to integer minutes k >= 0.6 x stage-one mean (and <= 53), truncated and renormalised. The short-night component's support is k < 0.6 x stage-one mean. pi is therefore exactly M2's total probability of a short night.
   - Refitting: on earlier seasons' non-short appearances, the mean is refitted by least squares with stage one's inputs and form, and the sd by stage one's method (sd = a + b x mean, from absolute residuals).
   - Fitting window for all of M2's parts: seasons 2017..s-1 for test season s.
   - Short night: rounded actual minutes < 0.6 x stage-one mean.
3. **Wording.** Points with actual minutes is a diagnostic reference, not an accuracy ceiling. Actual minutes partly reflect how well the player is performing in the game.
