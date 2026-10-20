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
