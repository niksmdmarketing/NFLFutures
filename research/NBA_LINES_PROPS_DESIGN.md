# NBA game lines and player props: design for review, version 2 (20 Oct 2026)

Not built yet. Version 2 adopts all of GPT's second review (TypeSafe 100%): no scaling of player points to a team score; possession-level simulation so every count adds up by construction; observed vs estimated opportunities labelled; the minutes-score loop handled quarter by quarter; lineup effects measured relative to the team rating's own lineup; the shared "good night" effect off by default; a stricter evaluation with appearance and settlement rules. Version 1's earlier review points are kept (playing time separate from role; pre-2021 absences used to learn structure, never as pre-game knowledge; fixed thresholds and timestamps; market prices archived as a benchmark only).
Constraints: no paid data; market prices are never an input; rules written before results.

## 1. Outputs
- Game: win probability, probability of covering any spread, of going over any total, each team's score distribution, overtime probability.
- Player: probability of appearing; distributions of points, rebounds, assists and the combos PR, PA, RA, PRA given appearing; over/under probability for any line under a stated settlement rule (section 7).
- All from one simulation whose events add up: player points sum to the team score, assists never exceed teammates' assistable baskets, rebounds never exceed available misses.

## 2. Data (all free, all held) and what it really measures
| Data | Seasons | Observed | Not observed |
|---|---|---|---|
| Team box scores | 2003-2026 | Points, shot attempts and makes, free throws, rebounds, turnovers; possessions estimated | - |
| Player box scores | 2002-2026 | Minutes, points, offensive/defensive rebounds, credited assists, attempts, makes, free throws, turnovers, starter, did-not-play reason | - |
| Play-by-play with rebuilt lineup stints | 2010-2026 | Who was on court for each possession; each shot, make, miss, free throw, turnover, rebound and credited assist; minutes by quarter | Tracking-style "rebound chances" (contested boards) and "potential assists" |
| Schedules | all | Rest, back-to-backs, travel, home/away | - |
| Official pre-game injury reports | 2021-22 to now | Status before tip-off at the report time | Minutes restrictions, late scratches after the report |
| Player ratings (RAPM) | 2010-2026 | Derived from stints | - |
| Tracking / play-type / hustle season tables | 2016+ | Season aggregates | Usable in a historical forecast only from the date each table was published; candidate features only |
| DARKO snapshots | from now | - | Benchmark / candidate prior only |
| Kalshi prices | from now | Benchmark only, timestamped, never an input | - |

Exposure terms are computed from stints and labelled as observed exposures, not tracking opportunities:
- rebound exposure = missed shots (own and opponent's) while the player is on court;
- assist exposure = made field goals by on-court teammates;
- usage exposure = team possessions while on court.
Potential assists and contested-rebound chances are not available and are not claimed.

## 3. Forecast timestamp and information
Every forecast has a timestamp T and uses only information known at T: morning of game day, and just after the ~5:30 pm ET official report.
- 2021-22 onward: archived official reports at the matching time.
- Before 2021: availability for a historical forecast = previous game's rotation plus known long absences; who actually played is not used as pre-game information.
- Pre-2021 absences are still used to estimate structure (how minutes and roles shift when a player is out).

## 4. Simulation (one game, about 10,000 draws)
**Step 1 - Availability.** Each rostered player appears with a probability from his report status (calibrated table: Out ~100% miss, Doubtful 97%, Questionable 45%, Probable 8%), long-absence state and rest pattern (back-to-back rest rates). Output per draw: the available roster.

**Step 2 - Rotation plan by quarter.** For the available roster, a baseline minutes plan per quarter (starters' first-quarter stint, bench entries, closing lineup), learned from stints: recency-weighted, by role, shrunk to team and league patterns. When a player is out, his minutes are reassigned by learned redistribution patterns (position and depth similarity), estimated from all historical absences with shrinkage.

**Step 3 - Game environment parameters.** Expected possessions (both teams' pace, rest, home) and expected points per possession (team offence vs opponent defence from the existing ratings, split into offence and defence). A lineup adjustment is applied relative to the lineup already represented in the team rating (the team's usual minutes-weighted rotation over the rating window), so only the difference from that usual lineup moves efficiency; injuries are not counted twice. Whether this lineup adjustment helps is tested against the complete existing game model before it is kept.

**Step 4 - Possession-level play, quarter by quarter.** Each quarter:
- the number of possessions is drawn around its expectation (with a shared game-pace term so both teams' possession counts move together);
- on each possession, the five on-court players (from the rotation plan) compete for usage according to their usage rates; the possession ends in a turnover, a shot (2 or 3) with a make probability, free throws, or an offensive rebound that extends it;
- on a made field goal, an assist is credited with a probability that depends on shot type and the passer's assist rate among the on-court teammates (never the scorer);
- on a miss, the rebound goes to one of the ten on-court players according to their offensive and defensive rebound rates;
- per-player rates are shrunk to long-run and position levels and adjusted for the opponent (defensive rebound rate allowed, turnovers forced, three-point attempt rate allowed).
Calibration: the possession-level rates for both teams are tilted (one parameter per team per game) so that the expected points per possession equals the step-3 expectation. Nothing is scaled after the draw, so all counts stay integers and add up.

**Step 5 - Score-dependent rotations.** Entering each quarter, the rotation plan is adjusted to the current score: in the fourth quarter (and late third), starters' minutes fall with the margin according to a blowout rule learned from stints. This replaces version 1's unspecified "iteration".

**Step 6 - Overtime.** Only if regulation ends tied: a five-minute period with its own possessions and closing-lineup rotation; repeated for multiple overtimes; playing-time limits and foul-outs handled through the rotation (six fouls end a player's game; fouls drawn from per-minute foul rates).

**Step 7 - Read-outs.** From the same draws: win, cover, over/under; each player's appearance indicator and stat lines; combos summed within each draw.

**Extra dependence.** The shared "good night" player effect is off by default. Stats already move together through minutes, pace, usage and score. It is added only if historical residuals (after the possession simulation) show unexplained co-movement, and then tested.

## 5. Estimation
- Every parameter point in time (data before T), walk-forward by season.
- Player rates: empirical-Bayes shrinkage with recency weights; rookies and players new to a team from position and role priors.
- Rotation and redistribution patterns from historical stints and absences, with shrinkage.
- Settings chosen on early seasons and tested on later ones.

## 6. Build order (GPT and TypeSafe agree)
1. Availability and minutes: probability of appearing, minutes distribution given appearing, by quarter. Tested on its own (minutes are observable).
2. Game environment: possessions, efficiency, margin and total distributions, overtime; checked against history and the existing win model.
3. Role and stat generation in the possession simulation; individual props first.
4. Combos, then the comparison with archived market prices.
Each stage has its own pre-registered rule and must beat its baseline before the next is built on it.

## 7. Evaluation (rules written before results)
- **Separate the three pieces:** probability of appearing (log loss), stat distribution given appearing, and settlement. A player who does not play is scored as "did not appear", not as zero; market comparisons follow the contract's rule for non-participants (void vs settled), stated per market.
- **Scoring:** ranked probability score over the full support of each integer stat (not only a threshold grid), plus discrete calibration with randomised PIT; coverage of central intervals; fixed pre-game threshold grids reported as well, set by formula before each game.
- **Baselines with real distributions:** season average, last-10 average, and minutes-adjusted per-minute rate, each given a historically fitted distribution (for example a fitted over-dispersed count around that average), so baselines and model are compared on the same distributional score.
- **Game lines:** margin and total scored by ranked probability over integer outcomes; win by log loss; compared with the existing win model.
- **Splits:** forecast timestamp, season, starters vs bench, games with a key teammate out, the injury-report era (2022-2026, the only fully honest pre-game window) vs earlier seasons.
- **Combos:** joint draws vs the naive "add the separate projections" baseline, on the same scores.
- **Market benchmark:** frozen forecasts vs archived Kalshi prices at matching timestamps, with matched settlement rules, from this season. Never used in fitting.

## 8. Main risks
- Minutes: late scratches, coach decisions, blowouts; the biggest source of prop error.
- Role changes after trades and injuries.
- Possession simulation calibration: tilting rates to match the team expectation must not distort individual players (checked by player-level calibration).
- Small samples per player; rookies.
- Honest pre-game test window is only 2022-2026.
- Thin, short market benchmark (Kalshi props from Nov 2025).

## 9. TypeSafe on the design
- Version 1 (20 Oct): one joint simulator (94%); opportunity-based counts (100%); full-distribution scoring at fixed pre-game thresholds (89%); minutes and role first (93%).
- Version 2 (20 Oct): adopt all of GPT's second-review revisions with a possession-level simulation, good-night effect off by default, availability and minutes first (100%).

## 10. Implementation notes after GPT's third review (20 Oct 2026; design accepted, start stage one)
1. Available is not appears: availability is drawn first (health/report), then the rotation decides whether an available player gets minutes. Appearance probability = P(available) x P(minutes > 0 | available); bench props depend on the second factor.
2. One continuous game: possessions alternate on a shared clock (each possession consumes time; the clock, not two independent counts, ends quarters). Offensive rebounds extend a possession; and-ones and technical free throws keep possession; end-of-quarter heaves can end without a rebound; team rebounds and dead-ball rebounds are explicit outcomes (no player credited).
3. The efficiency tilt changes only a stated set of rates (turnover rate, two- and three-point make probabilities, free-throw trip rate), each kept within bounds learned from history, and team and player distributions are checked together; it must not push every player's shooting to implausible levels.
4. Fouls: deferred. Version 1 has no foul-outs; free throws come from per-possession trip rates. Foul modelling is added later only if it earns its place.
5. Combo baseline: independent draws from the same component distributions (same marginals, no dependence), so the test isolates whether the joint dependence helps; the naive sum-of-means is reported too.
6. Forecast times are relative to each game's tip-off (6 hours and 1 hour before), using the latest official report actually published before that time.
7. Market prices: archiving starts now (Kalshi collector on the user's PC), not at the final stage.
8. Stage one's first test covers appearance probability, minutes distributions, returning players and teammate absences; score-dependent minutes are added once the game environment exists.
TypeSafe (100%): proceed on this basis.
