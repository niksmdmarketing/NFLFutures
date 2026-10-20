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

## Outcome (20 Oct 2026) - M2 passes; points still fails calibration; rebounds and assists replaced by their M2 versions
Run: research/nba_minutes_tail_test.py (results research/nba_minutes_tail_results.json). As a check, the frozen versions with stage-one minutes reproduce the earlier scores exactly (points P+T 0.037713).

**Minutes (M2 vs stage one):**
- Unconditional RPS 0.059558 against 0.059701: gain +0.000143, 90% lower bound +0.000114, better in 5 of 5 seasons.
- PIT given appearing 0.083-0.119 (stage one 0.092-0.131). Both gates pass.
- Mean pi 0.127 against an actual short-night rate of 0.132.

**Points (P+T with M2):**
- Beats B1, B2, B3 and B3m-with-M2: every lower bound above zero, 5 of 5 seasons, better given appearing.
- PIT lowest decile 0.146 (was 0.161). The calibration gate (0.13) still fails.

**Rebounds P+O with M2 against the frozen version:**
- RPS gain +0.00005 (95% bound +0.000039).
- PIT 0.091-0.109.
- Fixed-group low-minute-risk over gap 0.051 -> 0.039.
- All three conditions hold: replaced.

**Assists P+T with M2 against the frozen version:**
- Gain +0.000024 (95% bound +0.000017).
- PIT 0.095-0.105.
- Gap 0.052 -> 0.041.
- Replaced.

**Fixed groups (amendment 1), points:**
- Low-minute-risk overs: 0.525 -> 0.509 predicted, against 0.447 observed.
- Confident overs (fixed group, 2,473): 0.847 -> 0.779 predicted, against 0.651 observed.
- M2's own confident group (1,266): 0.852 against 0.763.

**Decision (written gates; TypeSafe 100%):**
- M2 recorded as passing.
- Points recorded as failing calibration.
- Rebounds and assists move to version 2 (M2 minutes) in model/nba_props_frozen.json; version 1 is archived.
- The subgroup weakness label stays, because the gaps remain about 4 points.

**Diagnostic for the next points rule** (descriptive): in the fixed low-minute-risk group, stage one's mean minutes given appearing is 14.55 against 13.50 actual, and P(minutes < 15) is 0.509 against 0.553. A mean-minutes bias for fringe players remains, beyond the short-night tail. It likely drives the remaining over gap and part of the points low tail, together with points dispersion given minutes.

## Checks after the outcome (20 Oct 2026; GPT review; research/nba_minutes_m2_checks.json). Descriptive
Fixed low-minute-risk group (48,571 appearances, 2022-2026):

| Measure | Stage one | M2 | Actual |
|---|---|---|---|
| Average minutes, given appearing | 14.55 | 14.48 | 13.50 |
| P(under 15 minutes) | 0.509 | 0.477 | 0.553 |
| P(short night) | - | 0.256 | 0.272 |

Other players: average 28.42 / 28.66 / 28.37; P(under 15) 0.036 / 0.046 / 0.045.

**Normal-night component.** On historical normal nights, the untruncated fitted mean is right (fringe 16.91 against actual 16.97). Removing the lower tail pushes the component's mean up to 17.93 for fringe players (other players 29.63 against 29.20).

So the remaining fringe bias is largely an implementation artefact of how M2 builds its normal-night part. For fringe players, M2 is no better than stage one on average minutes and is worse on P(under 15). The next step (TypeSafe 98%) is a narrow fix under its own rule: fit the normal-night component as a truncated distribution, so that its mean after truncation matches normal nights. Everything else stays unchanged.
