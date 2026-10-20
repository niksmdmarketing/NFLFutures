# NBA game lines and player props: design for review (20 Oct 2026)

Not built yet. Written so it can be critiqued before any code. It incorporates GPT's earlier review (separate playing time from role; use pre-2021 absences to learn role changes but never as pre-game knowledge; joint simulation for combos; fixed thresholds and forecast timestamps; archive market prices as a benchmark only). Constraints: no paid data; market prices are never an input; rules written before results, as for every other model here.

## 1. Outputs
- Game: win probability (moneyline), probability of covering any spread, probability of going over any total, distributions of each team's score.
- Player: full distributions of points, rebounds, assists, and the combos PR, PA, RA (AR) and PRA; over/under probability for any line.
- All from one simulation, so every output is consistent: a player's points can't imply a team total the game model rejects.

## 2. Data (all free, all held)
| Data | Seasons | Use |
|---|---|---|
| Team box scores | 2003-2026 | Possessions, offence and defence, pace, home edge |
| Player box scores | 2002-2026 | Minutes, points, offensive/defensive rebounds, assists, shot attempts, free throws, turnovers, starter, did-not-play reason |
| Play-by-play with rebuilt lineup stints | 2010-2026 | Who was on court for every possession: on-court usage, rebound chances, assist chances, lineup player ratings |
| Schedules | all | Rest days, back-to-backs, travel, home/away |
| Official pre-game injury reports | 2021-22 to now, plus live collection | What was known before tip-off; status-to-miss rates already calibrated (Out ~100%, Doubtful 97%, Questionable 45%, Probable 8%) |
| Player ratings (RAPM) | 2010-2026 | Lineup strength, efficiency adjustments |
| Tracking / play-type / hustle season tables | 2016+ | Season-level role descriptors (e.g. rebound and assist tendencies); candidate features only |
| DARKO snapshots | from now | Benchmark and candidate prior only |
| Kalshi prices (spreads, totals, player props) | from now | Benchmark only, archived with timestamps, never an input |

## 3. Forecast timestamp and information
Every forecast has a timestamp T and uses only information available at T. Two standard times: morning of game day (before the official report) and just after the ~5:30 pm ET official report. Historical tests reproduce the same information set:
- 2021-22 onward: the archived official reports at the matching time.
- Before 2021: no pre-game reports, so availability for a historical forecast = the previous game's rotation plus known long absences (players who had missed every game since a date). Who actually played in the forecast game is not used as pre-game information.
- Pre-2021 games are still used to estimate structure (how minutes and roles shift when a player is absent), because that is learning a relationship, not forecasting a specific game.

## 4. Simulation (one game, many draws)
For each draw:
1. **Availability.** Each rostered player plays with a probability from his report status (calibrated table), long-absence state, and rest pattern (back-to-back rest rates for stars, estimated from history). Draws are independent across players except for known joint rest patterns.
2. **Minutes.** Given who is available, allocate 240 team minutes (265 in overtime):
   - baseline minutes share = recency-weighted share in comparable games, by role (starter/bench) and coach tendencies;
   - redistribution when a player is out, learned from historical absences: who absorbs the minutes depends on position and depth-chart similarity, estimated per team-season with shrinkage to league patterns;
   - game script: minutes depend on the simulated margin (starters lose minutes in blowouts), so step 2 is completed after step 3's margin is drawn, with a small iteration;
   - known restrictions (if published before T) cap minutes.
3. **Game environment.**
   - Possessions: both teams' pace ratings, rest, home, with its own variance.
   - Points per possession: team offence vs opponent defence (the existing ratings, split into offence and defence), adjusted for the lineups actually drawn in step 1 using player ratings (the small but consistent gain found in the player-first test).
   - Scores: possessions x efficiency for each team with a shared game-pace shock (so the two scores are correlated), plus a margin-dependent overtime chance.
   - The margin and total distributions are checked against history before anything else is built on them (shape, tails, overtime).
4. **Player opportunities.** Separate playing time from role. Per minute on court, each player gets:
   - a usage share of his team's shot attempts, free-throw trips and turnovers;
   - a rebound share of available rebounds (offensive: own team misses; defensive: opponent misses), adjusted for the opponent's rebounding;
   - an assist share of teammates' made field goals.
   Shares are recency-weighted and shrunk to his own history and position, and they shift when teammates are out (usage vacated by an absent player is redistributed by learned patterns, which differ from the minutes redistribution: a replacement starter may play more without shooting more).
5. **Player conversion.** Points from 2-point, 3-point and free-throw attempts with shooting percentages shrunk heavily to longer-run and position averages. Rebounds and assists as over-dispersed counts given opportunities. A shared player-game effect (a "good night" term) links a player's points, rebounds and assists in the same draw, on top of the links that already come through minutes and pace.
6. **Team consistency.** Player points sum to the team score drawn in step 3 (the player conversion step is scaled within the draw), so props and totals never contradict each other.

Each game is simulated about 10,000 times. Every market is read off the same draws: win, cover, over/under, each player's thresholds, and combos (sum of the components in the same draw, so their correlation is automatic).

## 5. Estimation
- Every parameter fitted point in time (only data before T), walk-forward by season.
- Player rates use empirical-Bayes shrinkage with recency weighting; rookies and players new to a team start from position and draft/role priors.
- Redistribution rules (minutes and usage when a teammate is out) are estimated from all historical absences, with shrinkage.
- Settings are chosen on early seasons and tested on later ones; none are tuned on the test seasons.

## 6. Testing (rules written before results)
- **Thresholds fixed before each game:** for every player and stat, a grid around his pre-game median (e.g. half-point lines from the 10th to the 90th percentile of his recent range, fixed by a formula, not by the model's own projection). Game lines on fixed grids of spreads and totals.
- **Primary score:** ranked probability score of each full distribution, plus calibration (probability integral transform) at the fixed thresholds. Win probability by log loss.
- **Baselines to beat:** season average, last-10 average, minutes-adjusted season per-minute rate x projected minutes, and for games the current model.
- **Split by:** forecast timestamp, season, team games played, starters vs bench, games with a key teammate out, and the injury-report era (2022-2026, the only fully honest pre-game test) vs earlier seasons.
- **Combos:** scored on the joint draws, compared with the naive "add the separate projections" baseline, to confirm the joint version is better calibrated.
- **Market benchmark:** frozen forecasts compared with the archived Kalshi prices at matching timestamps, starting this season. Never used in fitting.

## 7. Build order
GPT proposed: (1) margin distribution and totals; (2) minutes and role; (3) individual props, then combos; (4) market comparison. TypeSafe (20 Oct) chose the minutes and role model first (93%) over the game environment (5%); both orders keep the same four parts. Open question for review.

## 8. Main risks
- Minutes: late scratches, coach decisions, blowouts, overtime; the single biggest source of prop error.
- Role changes after trades and injuries, where shrinkage is slow to react.
- Sample size per player; rookies.
- Before 2021, availability known at the time is approximated, so the honest test window is 2022-2026 (four to five seasons).
- Team-level consistency (step 6) may distort individual distributions if done crudely.
- Thin and short market benchmark (Kalshi props start Nov 2025).

## 9. TypeSafe on the design (20 Oct 2026)
- Architecture: one joint game simulator (94%) over separate models (5%) or one machine-learning model per stat (1%).
- Player outcomes: opportunity-based counts with shrunk efficiency, over-dispersion and a shared player-game effect (100%).
- Primary test: full-distribution score plus calibration at fixed pre-game thresholds, against baselines, by timestamp (89%).
- First build: minutes and role model (93%).
