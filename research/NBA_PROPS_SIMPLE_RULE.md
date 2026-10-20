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
