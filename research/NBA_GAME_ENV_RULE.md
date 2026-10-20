# NBA stage two: game environment. Rule written BEFORE any result (20 Oct 2026)

Stage two of research/NBA_LINES_PROPS_DESIGN.md. Stage one (availability and minutes, research/NBA_MINUTES_RULE.md) is frozen and used as written. This rule adopts GPT's review of the stage-two plan: two challenger versions, with the player part's added value as an adoption requirement; identical games and forecast times against the complete live win model, injury adjustment included; exact scores and pass rules; offence and defence adjusted separately; realism checks on the simulated scores. This is the smallest testable version: team-level possessions only, no players inside the simulation. Player stats come in stage three.

## Games, seasons and forecast time
- Regular-season games, test seasons 2022-2026 (season = end year): the official-injury-report era, the only fully pre-game window. Walk-forward: anything fitted for season s uses only earlier seasons plus games of season s before the forecast.
- Team ratings come from weekly checkpoints, as in research/us_match_ratings.py: `nba._fit_ratings` (live settings) refitted on games before the first day of the week. All models use the same checkpoint.
- Forecast time: 1 hour before tip-off (main). Availability information is the official report used by stage one at that time. 6 hours before is reported only.
- Every model is scored on the same games: the games where every model has a forecast. Games dropped for missing data are counted by reason.

## Models
**L - the live win model, complete (baseline).**
- Margin mean m_L = (net gap + home edge) x pace - 0.45 x (availability difference). The net gap and home edge come from the team rating. The availability difference is the v2_official variant (research/nba_availability2.py), i.e. the live injury adjustment.
- Win probability = Phi(m_L / s_eff), with s_eff = sqrt(GAME_SIGMA^2 + 2 TEAM_TAU^2) as live.
- The live model has no margin or total distribution, so L gets fitted ones:
  - margin: a normal with mean m_L and standard deviation fitted on earlier seasons, discretised to integers with zero excluded (the probability of zero moves to the two sides in proportion);
  - total: a discretised normal with mean (home rating + away rating) x pace / 100, where each rating = base + own offence - opponent defence (+ the home-offence term for the home team), and standard deviation fitted on earlier seasons.
  
  L contains no player information beyond the availability term.

**B - simple averages (reported, not a gate).** Each team's season-to-date offensive rating, defensive rating and pace (the previous season's values for its first 10 games, blended linearly), the same discretised-normal form, and the same fitted standard deviations.

**G0 - team-only game environment.**
- Expected possessions = the average of the two teams' rating paces.
- Expected points per possession for each team = the same as L's total model (base + offence - opponent defence, plus home).
- Margin and total come from the simulation below. Injury information enters G0 only as L's availability term, split equally between the two teams' expected points per possession (the margin shift is the same as L's; the total is unchanged). G0 therefore has the same information as L.

**G1 - G0 plus the projected lineup, with offence and defence adjusted separately.**
- Player offence and defence ratings: two-sided RAPM from lineup stints before the checkpoint (each stint gives two rows: home offence against away defence, and away offence against home defence). Points per 100 possessions on each row; season weights as in research/replay_nba._player_ratings (last season 1, the season before 0.5, this season 1); ridge 3000 on each side; each side's prior is half the player's net box-score prior (2.5 x box value / 2); unrated players -0.5 on each side.
- Projected lineup: stage one's unconditional expected minutes at the forecast time for each candidate (P(appear) x expected minutes if he appears), scaled so the team totals 240.
- Usual lineup: the team's minutes per game in the games and season weights the team rating uses (players since traded are included, because they shaped the rating).
- Team offence adjustment = k_O x [sum over projected (minutes/48 x O-rating) - the same sum over the usual lineup]. Team defence adjustment likewise with k_D.
- These replace L's availability term (no double counting). They move each team's expected points per possession separately, so absences can move the total, not only the margin. Pace is not adjusted in this version.
- k_O and k_D are fitted walk-forward on earlier test seasons, by least squares of each team's actual points per 100 possessions on the predicted adjustment. 2022 uses k_O = k_D = 1 (no fitting).

## Simulation (G0 and G1; 4,000 draws per game, fixed seed)
- One shared clock: four 12-minute quarters (720 seconds each). The teams alternate possessions; each possession uses a duration drawn from the league's empirical distribution of possession lengths, from earlier seasons' stints and play-by-play.
- That distribution is scaled per game so that the expected number of possessions equals the expected pace.
- Each possession scores 0, 1, 2, 3 or 4 points, drawn from the league's empirical points-per-possession mix (earlier seasons; offensive rebounds and free throws already inside the possession). The mix is tilted by one parameter per team per game (exponential tilting) so that its mean equals that team's expected points per possession.
- A shared game factor: each draw multiplies both teams' possession durations by one common factor (log-normal, standard deviation fitted on earlier seasons to the spread of actual game pace), so both teams' scores move with pace.
- End of quarter: the possession in progress ends when the clock runs out.
- Overtime: if regulation ends tied, 300-second periods with the same rates, repeated until the tie is broken.
- No late-game fouling, no garbage time and no score-dependent rates in this version. The realism checks below show whether those omissions matter.
- Outputs: P(home win), the integer distribution of the final margin, the integer distribution of the total, and P(overtime).

## Scores (defined before results)
- **Margin RPS:** the final margin (home minus away, overtime included) clipped to -50..50. Forecast cumulative F(k) for k = -50..49; RPS = (1/100) x sum over k of (F(k) - 1[y <= k])^2. Mean over games.
- **Total RPS:** the final total clipped to 160..300; the same formula over the 140 thresholds, divided by 140.
- **Win log loss.**
- **Calibration (reported):**
  - randomised PIT deciles for margin and total;
  - win calibration slope (logistic regression of the result on logit p);
  - central 50% and 80% interval coverage for margin and total.
- **By season:** every score is reported for each test season.
- **Uncertainty:** week-block bootstrap (resampling whole calendar weeks of the pooled test set), 2,000 draws, fixed seed.

## Gates
**A. Realism (G0 and G1 each; pooled test seasons, simulated vs actual):**
1. Standard deviation of the total within 10% of the actual.
2. Standard deviation of the margin within 10% of the actual.
3. Correlation between the two teams' scores within 0.10 of the actual.
4. Share of games decided by 3 points or fewer (overtime included) within 2 percentage points.
5. Overtime frequency within 1.5 percentage points.
6. Every PIT decile for margin and for total between 0.08 and 0.12.

**B. Against L (G0 and G1 each, 1 hour before, 2022-2026):**
1. Total RPS lower than L's, with the bootstrap 90% one-sided lower bound on the gain above zero.
2. Total RPS lower in at least 4 of the 5 seasons.
3. Margin RPS not worse than L's by more than 0.5% (point estimate).
4. Win log loss not worse than L's by more than 0.002 (point estimate).

**C. The player part (G1 vs G0):**
1. Margin RPS or total RPS lower, with the bootstrap 90% one-sided lower bound on that gain above zero. Both are tested, with 5% each (Bonferroni).
2. Neither score worse (point estimate).
3. Win log loss not worse.

## Decision (TypeSafe decides, on these outcomes)
- **G1 passes A, B and C:** G1 becomes the game environment for stage three.
- **G1 fails C, and G0 passes A and B:** G0 becomes the game environment, and the player adjustment is not used.
- **Neither passes A and B:** recorded. Stage two is revised under a new rule before stage three. A failure of realism gate A is recorded with which check failed.
- Nothing on the site changes from this test. Kalshi spreads and totals (archived from 20 Oct 2026, never an input) are compared with frozen forecasts later in the season as a reported benchmark.

## Reported only
- B (simple averages).
- The 6-hour forecast.
- L with its standard deviation refitted walk-forward, instead of the live s_eff.
- Fitted k_O and k_D by season.
- Splits: games with a rotation player (25+ minutes per game) out vs not; team games 1-10 vs later; close and lopsided expected margins.
- Diagnostic: stage one's short-minutes tail (PIT lowest decile 13%) - which games it concentrates in. Stage one is not changed here.

## Limitations carried from stage one (unchanged)
- Traded players stay on their old team's candidate list until they appear for the new team. There are no dated rosters before 20 Oct 2026.
- Injury reports are replayed at their scheduled publication time (from the NBA file name). Actual delays and later file replacements cannot be seen.
- Unseen players (debuts, new signings not on a report) are absent from G1's projected lineup.
- RAPM settings were chosen earlier on overlapping seasons, so the player ratings are not fully out of sample.

## Amendment 1 (20 Oct 2026, after GPT's review; written before any code or result). Where it conflicts with the text above, this governs.
1. **Player adjustment fitted to the team model's errors.** For each team-game, the target is actual points per 100 possessions minus the team-only expected rating (base + own offence - opponent defence + home term; no injury term). Regressors: the team's offence lineup delta (O-ratings) and minus the opponent's defence lineup delta (D-ratings). k_O and k_D are estimated jointly by least squares with a ridge toward (1, 1) of strength 1,000 team-games (penalty 1,000 x mean square of each regressor), no intercept. Fitting seasons: all seasons from 2017 up to s-1 for test season s (so 2022 is fitted on 2017-2021, with no default). For 2017-2021 the projected minutes come from the stage-one model refitted on seasons 2016..s-1, using official report statuses where they exist (2020-2021) and none before; for 2022-2026 they are exactly stage one as frozen.
2. **L is internally consistent.** L's margin distribution is the normal N(m_L, s_eff) with the live s_eff (not fitted), discretised so that a positive integer k takes the mass of (k-1, k] and a negative k the mass of [k, k+1). Its win probability is then exactly the live Phi(m_L / s_eff). L's total standard deviation has no live counterpart and is fitted on earlier seasons. The version of L with a fitted margin standard deviation is a separate reported benchmark (L_fit), not the gated baseline. The same discretisation is used for B.
3. **Statistical thresholds.**
   - Gate B1 uses a one-sided 90% lower bound.
   - Gate C has a familywise one-sided error rate of 10%: each of the two scores (margin, total) is tested with a one-sided 95% lower bound (5% each), and C1 passes if either bound is above zero.
   - The "not worse" conditions (B3, B4, C2, C3) are point-estimate conditions: they establish observed non-deterioration, not confidence that meaningful damage is excluded. For each, the one-sided 90% bound on the deterioration is reported, not gated.
4. **What G1 tests.** G1 uses the expected lineup (unconditional expected minutes), so a questionable player contributes part of his impact in every draw rather than separate plays/sits scenarios. It tests an expected-lineup adjustment, not stage one's full uncertainty, and can miss tails. Reported only: G1s, which samples each player's appearance per draw (Bernoulli with stage one's P(appear)), gives appearing players their expected minutes given appearing, rescales to 240, and recomputes the adjustment in each draw with the same k_O and k_D.
5. **Simulation details.**
   - Possession points use the empirical support observed in earlier seasons' play-by-play, including 5+ point possessions (no truncation at 4).
   - A possession starts only while the quarter clock is above zero. It is completed and scored in full even if its drawn duration runs past zero; the quarter then ends.
   - The first quarter starts with a random tip (50/50). The tip loser starts quarters 2 and 3, the tip winner quarter 4. Each overtime starts with a new random tip. Within a period, possession alternates after every possession.
   - Possession outcomes are independent given the team rates and the shared pace factor. No shooting-variance factor is added; the realism checks show whether that omission understates scoring variability.
6. **Clipped scores made visible.**
   - Reported for every model: the number of games outside the RPS ranges (margin -50..50, total 160..300).
   - Also reported: an essentially unclipped RPS over margin -90..90 and total 100..360, and the mean absolute error and 99th-percentile absolute error of the forecast medians.
   - The gates use the clipped RPS as written.
7. **Decision table (the written gates determine the result; TypeSafe helps interpret, it does not override).**
   - G1 passes A, B and C: G1.
   - Otherwise, G0 passes A and B: G0. This covers G1 failing C, and G1 passing C but failing A or B.
   - Otherwise: recorded, and stage two is revised under a new rule.

## Outcome (20 Oct 2026) - neither G0 nor G1 passes; recorded as a fail
Run: research/nba_game_env_test.py (results research/nba_game_env_results.json; first scoring run kept as nba_game_env_results_firstrun.json). 6,108 test games 2022-2026 (42 without a lineup for both teams dropped from every model). 4,000 draws per game for G0 and G1; the reported-only G1s and G1_6h used 2,000.
Mechanics note (before scoring): play-by-play before 2020 lacks free throws, so possession inputs come from 2020+ seasons only (2022 uses 2020-2021).

| Model | Margin RPS | Total RPS | Win log loss |
|---|---|---|---|
| L live model (complete) | 0.07660 | 0.07670 | 0.6088 |
| B simple averages (reported) | 0.07937 | 0.07631 | 0.6337 |
| G0 team-only simulation | 0.07781 | 0.07678 | 0.6144 |
| G1 simulation + lineup | 0.07894 | 0.07631 | 0.6245 |
| G1s sampled lineup (reported) | 0.07896 | 0.07637 | 0.6244 |
| G1 at 6 hours (reported) | 0.07923 | 0.07639 | 0.6266 |

The realism checks compare simulated games with actual ones (pooled):

| Check | Actual | G0 | G1 |
|---|---|---|---|
| Spread of totals (sd) | 20.2 | 21.6 (pass) | 21.6 (pass) |
| Spread of margins (sd) | 15.4 | 18.3 (fail) | 18.1 (fail) |
| Correlation of the two scores | 0.26 | 0.16 (fail) | 0.18 (pass) |
| Games decided by 3 or fewer | 14.5% | 13.9% (pass) | 14.0% (pass) |
| Overtime rate | 5.0% | 2.2% (fail) | 2.2% (fail) |
| PIT deciles | | margin 0.058-0.134 (fail) | margin 0.060-0.130 (fail) |

**Gate B, against L:**
- G0 fails all four parts. Total gain -0.00008; margin RPS 1.6% worse; log loss 0.0056 worse.
- G1 improves totals: gain +0.00039 (90% lower bound +0.00027), better in 5 of 5 seasons. It fails on margins (3.1% worse) and on log loss (0.0156 worse).

**Gate C, G1 against G0:**
- Totals are better: 95% lower bound +0.00033 (C1 passes).
- Margins are worse in every season, and log loss is worse (C2 and C3 fail).

**Decision by the written gates:** neither model qualifies. Stage two is to be revised under a new rule.

## Diagnosis (20 Oct 2026; after the fail, per GPT's request; research/nba_game_env_diag.py, nba_game_env_diag.json). Descriptive, nothing selected
1. **Within-game noise, not exaggerated team differences.** The variance of G0's game means is small (margin 44 against 236 for actual margins). The excess is in the simulated within-game uncertainty, compared with the actual prediction errors around the same means:

| | Home score | Away score | Covariance (correlation) | Margin | Total |
|---|---|---|---|---|---|
| Actual prediction errors (variance) | 138 | 138 | 44 (0.32) | 188 | 365 |
| G0 simulated within-game (variance) | 178 | 177 | 33 (0.18) | 289 | 420 |

   Margin variance = home + away - 2 x covariance. The excess of about 100 comes from each team's variance being about 40 too high and the covariance about 11 too low.
2. **Possession accounting.**
   - The real play-by-play counts about 98.7 possessions per team per game. Box-score pace (used to calibrate the simulation) is about 102, so the simulation has about 3% more possessions.
   - Simulated possession counts vary by 4.85 per team within a game. That is about the same as the actual spread of possession counts around expected pace across games, which also contains pace-forecast error. The extra shared pace factor was therefore fitted at 0: nothing was counted twice, but the count variation is too large.
   - Simulated count variation is also independent of possession outcomes. Durations are drawn independently; the duration CV is 0.72, and 5.6% of play-by-play possessions have zero length.
   - Within real games, team points given the possession count vary about as n x per-possession variance (about 140). The two teams' scores are positively correlated beyond the counts (0.05-0.25 by season). The simulation has no such link.
3. **Overtime.** Too few overtimes follow partly from the wide margins: a normal with the actual error sd of 13.7 implies about 3% ties. End-game behaviour (fouling, last shots) is absent and likely explains the rest.
4. **G1 audit.**
   - Lineup deltas are in team points per 100 possessions (minutes/48 x per-100 five-man ratings). The net delta correlates 0.42 with the injury term, as expected.
   - k_O was 0.66-0.69 and k_D 0.26-0.35 across test seasons, fitted to the team model's residuals.
   - Mean level (MSE of the game means):
     - margins: injury term 188.0, lineup term 194.3, both 189.7, team only 197.8. The lineup term is weaker than the injury term for margins.
     - totals: L 366.2, G1 362.4 (offence part 363.6, defence part 366.0), simple averages B 361.9. Total bias is about +1.1 for both L and G1, so G1's gain on totals is not a level effect. It is about the same size as B's, and whether the two overlap is untested.
   - Not adopted.
5. **Short-minutes diagnostic.** Players expected to play 24+ minutes who played 12+ fewer: 4.2% in blowouts (final margin 20+) against 2.9% in other games. Blowouts are 19% of games and hold 26% of these short nights.
