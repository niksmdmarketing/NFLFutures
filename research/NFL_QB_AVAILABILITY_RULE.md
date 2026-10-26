# NFL futures: QB-enabled replay and an injury-episode QB return model. Rule fixed before any code or results (26 Oct 2026, Sydney)

Status: **final.** GPT reviewed the draft; all its revisions were accepted (TypeSafe 88%). Nothing had been run when this was committed. Research only; live v4 stays frozen through 2026.

## Why
- Every historical futures replay so far turned v4's QB layer off.
- **The live QB layer** (pipeline/ratings.py):
  - QB values come from a ridge regression of EPA per dropback (QB, offence and defence effects; current season plus two previous seasons, weights 1 / 0.2 / 0.3), converted to points per game.
  - When the expected starter differs from the usual QB, the team rating moves by 0.5 × the value gap for the whole remaining season and playoffs, with no absence length and no return.
- TypeSafe chose to keep the QB values and model absence length (98%) over new QB ratings (0%).

## Definitions
- **Starter:** the starting QB recorded for each regular-season game (nflverse schedules, home_qb_id / away_qb_id; coverage 100% in 2006-2025). Dropbacks are not used to identify starters. A QB who takes a few snaps has not returned to the starting role.
- **Team games:** the team's own games in week order. Bye weeks are not games and are never missed games.
- **Incumbent and episodes:**
  - At the start of each season, the incumbent is the week-1 starter.
  - An **episode** begins at the first team game whose starter is not the incumbent. Its incumbent is frozen for the whole episode.
  - The episode **ends** at the first later game the incumbent starts again. If it is still open after the team's last regular-season game, it is **censored**.
  - After an episode ends, the same incumbent continues; a later absence starts a new episode.
  - If a classified non-injury episode (below) lasts 4 or more games, its replacement becomes the incumbent from the next season.
- **Classification at the episode's first missed game**, using only information dated before that game's kickoff:
  - **Injury:** the incumbent is listed on that week's official injury report (nflverse injuries; Out, Doubtful or Questionable) with a primary injury other than "Not injury related".
  - **Departure:** the incumbent is on another team's weekly roster, or has status CUT / TRD / RET, in that week.
  - **Benching:** the incumbent is on the team's weekly roster with status ACT and not on the injury report.
  - **Ambiguous:** anything else, including reserve status (RES) with no injury-report listing. A RES flag is "reserve status", not proof of injured reserve.
- **Replacement:** the starter of the team's most recent game at the checkpoint.

## Data-validation gate (run first; if any check fails, stop before any performance results)
1. **Starter IDs:** non-missing for at least 99% of regular-season team-games 2009-2025, and equal to the QB with the most dropbacks in that game for at least 90% of team-games.
2. **Injury reports:** present for every regular-season week of 2009-2025, with at least one QB listing in at least 95% of weeks.
3. **Weekly rosters:** present for every week of 2009-2025, with the incumbent found on some roster in at least 95% of episode-start weeks.
4. **Known-case audit** (expected values written now). Each case must be found as an episode with the expected team, first missed game and classification, and the expected return game or censoring:
   - 2017 GB Aaron Rodgers: collarbone, first missed week 7, injury; returned to start week 15.
   - 2019 NO Drew Brees: thumb, first missed week 3, injury; returned week 8.
   - 2019 PIT Ben Roethlisberger: elbow, first missed week 3, injury; censored.
   - 2020 DAL Dak Prescott: ankle, first missed week 6, injury; censored.
   - 2021 SF Jimmy Garoppolo: calf, first missed week 5, injury; returned week 7.
   - 2022 MIA Tua Tagovailoa: concussion, first missed week 5, injury; returned week 7.
   - 2023 NYJ Aaron Rodgers: Achilles, first missed week 2, injury; censored.
   - 2023 CIN Joe Burrow: wrist, first missed week 12, injury; censored.

   Up to one of the eight may differ by one week because of how the data records the starting game; any other difference fails the gate.
5. **Timing:** every field used at checkpoint w is dated on or before the checkpoint, or is a weekly label for a week at or before w. Weekly labels are reconstructed and revised history, not an archived point-in-time feed; this is disclosed.
6. **Counts reported:** episodes by class and season, and censored share. If fewer than 40 injury episodes fall in 2009-2025, the result is labelled inconclusive before the replay.

If check 4 shows classes cannot be separated (more than two of the eight not classified as injury), the experiment is relabelled a "QB-role return model" and needs a separate rule.

## Return model (B only; injury episodes only)
- **Discrete-time hazard** of the incumbent starting again at each next team game. It depends on:
  - games already missed in the episode (1, 2, 3, 4-5, 6+);
  - the incumbent's roster status at the checkpoint (RES or not RES).
- **Fitting:** walk-forward on injury episodes in seasons 2009 to Y-1. Censored episodes contribute their at-risk games, so ongoing and season-ending absences are not dropped.
- **Pooling:** a cell with fewer than 20 at-risk games is pooled into the previous games-missed cell of the same status; if still sparse, across status.
- **No return possible:** if the simulation reaches season end without a return, the QB stays out for the playoffs.
- **Eligibility:** while the incumbent is on reserve status, a return before the league minimum is impossible. The clock starts at his first RES week in the episode:
  - 2009-2011: no return in that season;
  - 2012-2016: 8 weeks;
  - 2017-2019: 8 weeks;
  - 2020-2021: 3 games;
  - 2022-2025: 4 games.

  This applies the injured-reserve rules to any reserve status, a disclosed approximation. The time since injury and the time since reserve placement are tracked separately.
- **Reported:** the number of distinct episodes and at-risk games behind each cell.

## Arms (identical except the QB treatment)
All arms use:
- v4 walk-forward ratings (research/nfl_futures_diagnosis.py v4wf, scale 0.89);
- the frozen simulator: tau 5.0, sigma 11.37, home edge 1.8, neutral sites no edge, correct playoff format, sweep off;
- 10,000 simulations with the same seeds;
- no pressure layer.

QB values come from qb_values on play-by-play through week w and the two previous seasons, rebuilt at each checkpoint, and are identical in A and B. λ = 0.5 in both arms. The core team rating already partly reflects the replacement's performance; this double-counting is shared by A and B and is a limitation.

1. **Base:** no QB adjustment.
2. **A, the historical proxy for v4's permanent QB adjustment:** if an episode is open at the checkpoint, add 0.5 × (value(replacement) - value(incumbent)) to the team rating for all remaining games and the playoffs.
3. **B:**
   - For open **injury** episodes: in each simulation, draw the incumbent's return game from the return model. Each remaining game he is out shifts that game's margin by 0.5 × (value(replacement) - value(incumbent)). The playoffs use the incumbent only if he has returned by the regular season's end.
   - For open benching, departure or ambiguous episodes: the same treatment as A.

## Markets, checkpoints, seasons and scores
- Division winner and make-playoffs after weeks 4, 9 and 13 (six cells); seasons 2013-2025. Conference and Super Bowl are secondary.
- Division: multi-class log loss of the winner. Make-playoffs: binary log loss. Probabilities clipped to [0.001, 0.999].
- Per season, the six cells averaged equally; seasons averaged equally.
- Season bootstrap of whole paired seasons, 10,000 draws, seed 20261026; one-sided 90% lower bound.
- **Reported:**
  - all-season results;
  - affected team-checkpoints (open injury episode);
  - distinct episodes;
  - affected seasons;
  - season-level gains;
  - whether one episode or season dominates;
  - A vs Base and B vs Base.

## Gates (all must hold)
1. B vs A primary gain: one-sided 90% lower bound > 0.
2. B vs A positive in at least 60% of seasons with an open injury episode at a checkpoint.
3. No cell worse than A by more than 0.002.
4. B vs A positive in 2020-25.
5. B vs A positive point estimate separately for division and for make-playoffs.
6. B vs A positive on affected team-checkpoints.
7. B's aggregate log loss no worse than Base, both overall and in 2020-25.

Gates are not relaxed because events are rare; wide intervals mean inconclusive.

## Decision
- **Pass:** B archived as a live shadow with the same episode definitions (live classification from the current week's injury report and roster). Betting use requires later forward evaluation.
- **Fail or inconclusive:** this candidate stops. A vs Base is reported either way.

## Disclosed exposure
- The 2013-2025 QB-free replay was inspected this week.
- v4's simulation settings were tuned on 2022-2025.
- λ was set without a historical test.
- The known-case list was written from general knowledge of those seasons.
