# NBA player props: simple challenger. Rule written BEFORE any result (20 Oct 2026)

Item 1 of research/RESEARCH_PROGRAMME.md. The model is minutes x shrunk per-minute production, with a full distribution. No feature search: the model, its two adjustments, the baselines and the gates are fixed here. Stage one (research/NBA_MINUTES_RULE.md) is used exactly as frozen.

## Population, seasons and forecast time
- **Player-games:** stage one's candidates (players who appeared for the team earlier this season and are still on it, plus players on the report in use), regular season.
  - Test seasons 2022-2026, 1 hour before tip-off (stage one's main forecast time).
  - Every model is scored on the same player-games.
- **Fallback group:** the stage-one fallback players (unseen before the game) are scored separately and reported, not gated. Their selection uses hindsight (stage-one limitation).
- **Walk-forward:** anything fitted for season s uses seasons before s (from 2017) plus earlier games of season s only.
- **Outcomes:** points, rebounds, assists from the box score. A player who does not appear has 0, scored as part of the unconditional distribution. Reported separately: scores given appearing, and for void settlement (non-appearance excluded).

## Challenger P
For player i in a game:
1. **Minutes:** stage one's unconditional distribution. P(appear), and given appearing a discretised normal on 1-53 (stage-one mean and sd).
2. **Per-minute rate for each stat:** recency-weighted per-minute production over his earlier games this season and last season (half-life 15 games played, last season's games included at weight 0.5). It is shrunk toward his position group's league rate (guards / wings / bigs; the same groups as stage one) with prior weight m0 minutes. m0 is set per stat by maximum likelihood of the per-minute rates on the earlier seasons (one number per stat per test season).
3. **Stat given minutes m:** negative binomial with mean rate x m. The dispersion is one parameter per stat, fitted on the earlier seasons by maximum likelihood given the actual minutes.
4. **Full distribution:** P(0) = 1 - P(appear) + P(appear) x sum over m of q(m) x NB(0 | rate x m). For k > 0, P(k) = P(appear) x sum over m of q(m) x NB(k | rate x m). Availability and minutes uncertainty are therefore included.

### Adjustments, each tested separately against P
- **P+T, teammate absence:** rate x (1 + b_s x V).
  - V is the share of the team's expected stat production (rate x usual minutes over its rotation) belonging to teammates ruled Out or Doubtful on the report in use.
  - b_s is one coefficient per stat, fitted on earlier seasons and bounded to 0..1.
  - Minutes already reflect absences through stage one's vacated-minutes term, so this adjusts only the per-minute rate (no double counting of minutes).
- **P+O, opponent and pace:** rate x (opponent factor)^c_s x (game pace / league pace).
  - The opponent factor is the opponent's season-to-date stat allowed per 100 possessions (to all players), relative to the league. It is shrunk toward 1 with prior weight 10 games, and blended with last season over the first 10 games.
  - Game pace is the average of the two teams' rating paces (as in stage two).
  - Per possession, so pace and defence are separated. It is not by position.
  - c_s is fitted per stat on earlier seasons, bounded to 0..1.

## Baselines (same appearance probabilities, so only the stat model differs)
Each uses stage one's P(appear) and, given appearing, a negative binomial around its own mean, with dispersion fitted on earlier seasons:
- **B1:** season-to-date average per game played (last season's average for his first game; position-group average if none).
- **B2:** last-10-games-played average.
- **B3:** per-minute rate (season to date, unshrunk) x stage one's expected minutes given appearing.

## Scores
- **Primary:** ranked probability score over the integer support of each stat, unconditional.
  - Supports: points 0-60, rebounds 0-25, assists 0-20; outcomes clipped into the support.
  - Formula as in the stage-one rule: mean over thresholds 0..max-1 of (F(k) - 1[y <= k])^2.
  - Outcomes above the support are counted and reported.
- **Reported:**
  - RPS given appearing;
  - randomised PIT deciles given appearing;
  - central 50% and 80% interval coverage;
  - over/under calibration at lines set by formula before each game (each player's B1 mean rounded to the nearest .5), reported for P only;
  - by season, starters vs bench, and players with a rotation teammate Out.

## Gates (per stat; P vs each baseline B1, B2, B3)
1. Pooled unconditional RPS lower than each baseline, with a week-block bootstrap (2,000 draws) one-sided 90% lower bound on the gain above zero.
2. Better than each baseline in at least 4 of the 5 test seasons.
3. Calibration given appearing: every randomised PIT decile between 0.07 and 0.13.

P passes for a stat if gates 1-3 pass for that stat. Stats are judged separately.

### Adjustment gates
- P+T and P+O are each judged against P, per stat (2 adjustments x 3 stats = 6 tests).
- Familywise one-sided error 10%, Bonferroni: each test requires a bootstrap one-sided 98.33% lower bound on the RPS gain above zero.
- Not worse on the other two stats (point estimate).
- An adjustment is kept only for the stats where it passes.

## Decision
The written gates decide; TypeSafe helps interpret.
- **P passes for a stat:** P (plus any adjustment that passed for that stat) becomes the prop benchmark for that stat. It is labelled "historical improvement", archived as a frozen forward test from the 2026-27 season, and compared with Kalshi quotes per research/RESEARCH_PROGRAMME.md item 2. It is not on the site until a forward season of evidence and a separate decision.
- **P fails for a stat:** recorded. That stat's baseline-beating model is revised under a new rule.
- Any later player-level simulator must beat P on the same player-games before it is used.

## Limitations carried over
- Stage one's limitations apply: traded players, scheduled-time report replay, unseen players.
- Per-minute rates ignore within-game role changes (blowouts, foul trouble) except through the minutes distribution.
- Opponent factors use all players, not positions. This is deliberate (no defence-versus-position averages).

## Amendment 1 (20 Oct 2026, before any code or result): evaluation extension after GPT's review of the AND-1 / PROPHET thread
These add reported items only. Gates, model and baselines are unchanged. PROPHET follows a reference market's prices, so it is outside our independent-model constraint and nothing is taken from it. AND-1's mechanics are undisclosed and nothing is copied.
1. **Forecast time:** everything is also scored at 6 hours before tip-off (stage one's second time), side by side with 1 hour. Reported: accuracy at each time and the size of the 6h-to-1h change.
2. **Overs and unders separately:**
   - At the formula lines (each player's B1 mean rounded to .5), report calibration of P(over) and P(under) separately, by stat, starters vs bench, and forecast time.
   - The scores are the mean predicted probability against the observed frequency, by probability decile for each side.
   - No side preference or under bias is built in. Any selection rule found from these numbers needs fresh testing on later data.
   - The short-minutes tail (stage one) is checked specifically for inflated over probabilities: the over-side calibration for players with low-minute risk is reported.
3. **Dependence in uncertainty:** the week-block bootstrap resamples whole weeks, so props sharing a player, game or injury news stay together. Counts of player-games are not presented as independent tests.

## Amendment 2 (20 Oct 2026, before any code or result): GPT's review of the rule. Where it conflicts with the text above, this governs.
1. **Pace (P+O).** The opponent-and-pace adjustment becomes: rate x (opponent factor)^c_s x (expected game pace / pace of the player's history). Pace of history is the weighted average box-score pace of the games behind his rate, with the same recency weights. Upcoming pace is not divided by league pace, so the historical environment is not counted twice.
2. **Minutes-matched baseline.** New baseline B3m: B3's unshrunk season-to-date per-minute rate, mixed over the same stage-one minutes distribution as P (same P(appear) and q(m)). B3m is added to the gated baselines (B1, B2, B3, B3m). P vs B3m isolates shrinkage and recency. B3m vs B3 (reported) isolates the value of the minutes distribution.
3. **Teammate absence, incremental (P+T).** V = expected missing teammate share now minus the missing share already reflected in the player's rate.
   - Teammate shares are each rotation teammate's (usual minutes 12+) share of the team's expected stat production.
   - Now: the sum of (1 - P(appear)) x share over teammates, from stage one at the forecast time.
   - Reflected: the weighted average, over the games behind his rate (same weights), of the actual share of teammates missing in those games.
   - Rate x (1 + b_s x V), with b_s in 0..1, fitted on earlier seasons.
4. **Combining adjustments.**
   - Each adjustment is adopted per stat, independently. The "not worse on the other two stats" condition is removed.
   - If both P+T and P+O pass for a stat, only the one with the larger pooled RPS gain is kept.
   - The combined P+T+O is reported, not adopted, under this rule.
5. **Scores aligned with use.**
   - New gate 4: P's RPS given appearing must be lower than each baseline's (point estimate), so any claim about void-on-non-appearance props rests on the conditional score.
   - Essentially unclipped sensitivity scores are reported: supports points 0-100, rebounds 0-45, assists 0-35.
6. **Fitting m0.** For each stat, m0 is chosen on the earlier seasons by maximising the negative-binomial log likelihood of each player-game's actual count.
   - The mean is the shrunk rate computed from that player's prior games only, times his actual minutes.
   - The dispersion is refitted for each m0.
   - Grid: m0 = 0, 25, 50, 100, 200, 400, 800 minutes.
   - The chosen m0 and dispersion are reported per test season.
7. **The minutes cap.** Stage one's minutes support is 1-53. Appearances above 53 minutes (multiple overtimes) are scored at 53 in minutes. The stat outcomes are always the actual counts.

## Outcome (20 Oct 2026) - rebounds and assists pass; points fails on calibration only
Run: research/nba_props_simple_test.py build / score. Results: research/nba_props_simple_results.json; first run kept as nba_props_simple_results_firstrun.json. 219,445 candidate player-games, 2022-2026, 1 hour before tip-off.

Unconditional RPS (lower is better):

| Stat | P | B1 season avg | B2 last 10 | B3 per-min x exp. minutes | B3m same minutes distribution | P vs B1 | P vs B3m |
|---|---|---|---|---|---|---|---|
| Points | 0.03787 | 0.03987 | 0.03967 | 0.03917 | 0.03831 | 5.0% better | 1.1% better |
| Rebounds | 0.03703 | 0.03815 | 0.03819 | 0.03776 | 0.03755 | 2.9% | 1.4% |
| Assists | 0.03018 | 0.03110 | 0.03110 | 0.03079 | 0.03068 | 3.0% | 1.6% |

- **Gates 1, 2 and 4 pass for every stat against every baseline:**
  - 90% bootstrap lower bound above zero (smallest: points vs B3m, +0.00036);
  - better in 5 of 5 seasons;
  - better given appearing.
- **Gate 3, calibration given appearing (PIT deciles 0.07-0.13):**
  - rebounds pass (0.093-0.115);
  - assists pass (0.096-0.104);
  - **points fail:** the lowest decile is 0.160 (B3m 0.145). Low-scoring nights after appearing happen more often than predicted.
- **Adjustments:** both pass the 98.33% bound for every stat. Gains on P:

| Stat | P+T (teammates) | P+O (opponent and pace) | Kept by rule (larger) | P+T+O combined (reported) |
|---|---|---|---|---|
| Points | +0.00016 | +0.00004 | P+T | +0.00020 |
| Rebounds | +0.00002 | +0.00004 | P+O | +0.00006 |
| Assists | +0.00015 | +0.00006 | P+T | +0.00021 |

- **Fitted values (stable across seasons):**
  - shrinkage prior m0: 25 minutes (points, assists), 50 (rebounds);
  - teammate coefficient b: points 0.20-0.30, rebounds 0.05, assists 0.40;
  - opponent exponent c: 0.70-0.85.
- **Value of the minutes distribution** (B3 minus B3m): positive for all stats. Points +0.00086, rebounds +0.00021, assists +0.00011.
- **Six hours before tip-off:** same ordering and gate results.
- **Unclipped scores:** same ordering.
- **Overs and unders (amendment 1, reported):**
  - At formula lines, given appearing, overall P(over) is slightly too high: points 0.491 against 0.479 observed, rebounds 0.482 against 0.458, assists 0.461 against 0.446.
  - The inflation is concentrated where GPT expected it. For players with low-minute risk (P(minutes < 15 | appear) >= 0.2), predicted overs against observed: points 0.525 vs 0.447, rebounds 0.491 vs 0.440, assists 0.453 vs 0.400.
  - Confident points overs are badly overstated: predicted 0.84 against 0.62 observed (2,179 cases).
  - No selection rule follows from this.

**Decision (written gates; TypeSafe 100% agrees):**
- Rebounds (P+O) and assists (P+T) become the prop benchmarks. Labelled "historical improvement over season, last-10, per-minute and minutes-matched baselines (RPS)". Frozen as a forward test for 2026-27; not on the site.
- Points fails and is revised under a new rule targeting the low-outcome tail: short-minutes nights and points dispersion given minutes.
- The inflated over probabilities for low-minute-risk players are the main known weakness of all three stats.

## Diagnostics after the outcome (20 Oct 2026; GPT review; research/nba_props_diag.py, nba_props_diag.json). Descriptive, nothing selected
1. **The exact frozen versions are calibrated.**
   - Rebounds P+O: PIT deciles 0.094-0.114, pass.
   - Assists P+T: 0.095-0.105, pass.
   - Points P+T: lowest decile 0.161, fail (as for P).
2. **Points: forecast against actual minutes.** Using actual minutes in place of the forecast minutes (a diagnostic only; actual minutes are never a forecast input):
   - the points PIT lowest decile falls from 0.161 to 0.131;
   - over probabilities for low-minute-risk players fall from 0.525 to 0.464, against 0.447 observed;
   - confident points overs go from 0.85 predicted against 0.65 observed, to 0.89 against 0.88.
   
   So minutes uncertainty, mainly short-minutes nights, is the main cause. A small production-dispersion part remains (lowest decile 0.131, top decile 0.090).
   
   The same holds for rebounds and assists. With actual minutes, the low-minute-risk over gap disappears: rebounds 0.437 against 0.440, assists 0.411 against 0.400.
3. **The subgroup weakness persists every season.**
   - Low-minute-risk overs: points predicted 0.51-0.54 against observed 0.44-0.46; rebounds 0.49 against 0.43-0.45; assists 0.44-0.47 against 0.39-0.41.
   - Confident points overs (p >= 0.8): 0.84-0.85 predicted against 0.61-0.71 observed in every season (430-560 cases a season; correlated, and identified during this investigation).
4. **Archive.** Rebounds P+O and assists P+T are frozen unchanged in model/nba_props_frozen.json (code commit, procedure, 2026-27 parameters fitted on 2017-2026).
   - Label: historically better overall, with a known subgroup weakness (overs too high for players at risk of short minutes).
   - A revised minutes model would create new versions, evaluated separately.
5. **Statistical caveat.** The week-block bootstrap captures shared game-day effects but not all dependence across a player's season. The test seasons were also used in developing the minutes model, so 5 of 5 seasons is encouraging, not untouched-holdout evidence.
