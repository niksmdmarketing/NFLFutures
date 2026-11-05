# NBA and NHL award models: published evaluation against a baseline. Rule, version 1

Written 5 Nov 2026 (Sydney), before any evaluation figure was computed. Amendments are added below with dates; nothing above them is edited.

## Why
- NFL awards publish an evaluation (settings.json awards_eval): log loss of the model for the eventual winner against a uniform baseline over the candidate pool. The Value page uses it to block awards that have not beaten their baseline (private pipeline/value_policy.evaluation).
- The 10 NBA/NHL awards publish none, so their comparisons are blocked: NBA MVP, DPOY, ROY and Sixth Man; NHL Hart, Vezina, Norris, Calder, Art Ross and Rocket Richard.
- TypeSafe (55%) chose this as the next model improvement. The owner asked for it.

## Data (existing point-in-time replays; nothing is rerun)
- NBA: model/replay/nba_awards_replay.csv, method `sim` (the live site method: forward simulation plus conditional logit, weights leave-one-season-out). End years 2010-2026, a checkpoint every 14 days.
- NHL: model/replay/nhl_awards_replay.csv, method `T1.0` (the live method, temperature 1). Seasons 2011-2025.
- Rows used: in-season checkpoints with 0.10 <= frac <= 0.90 (the share of the season played).

## Baseline
A uniform chance over the award's candidate pool, as in NFL awards_eval.
- Per row: log(N) if the eventual winner is in the model's pool (p_winner > 0); otherwise the same clipped loss as the model (-log 0.002).
- Pool sizes, from pipeline/nba_award_sim.SPECS and nhl_awards.pool:
    - NBA: MVP 25, DPOY 20, ROY 15, Sixth Man 15.
    - NHL: Hart 26, Vezina 10, Norris 12, Calder 16, Art Ross 15, Richard 15 (the race pages list the top 15).

## Pass, per award (all of these)
1. Mean log loss below the baseline's over all used rows.
2. Below the baseline in each third of the season (frac < 1/3, 1/3 to 2/3, 2/3 and over).
3. The favourite is not overconfident. Mean favourite chance minus the share of rows where the favourite won must have a 90% season-bootstrap interval (4,000 draws, seed 1) that includes 0 or lies below 0.

## Publish
model/award_eval_nba_nhl.json, per award:
- seasons, log_loss, baseline_log_loss, mean_p_winner, winner_in_pool;
- fav_said, fav_won, with the interval;
- pass, and the reasons for a fail.

The NBA and NHL awards builders attach it as `eval`, like NFL. An award that fails publishes its eval with log_loss >= baseline_log_loss or `pass: false`, so the Value policy keeps it blocked.

## Limits, stated now
- A uniform baseline is weak; beating it is necessary, not sufficient (GPT review). It is used because it is what NFL publishes.
- Seasons are few (15-17 per award), and checkpoints within a season are dependent.
- Australian award prices are not collected, so a pass shows on the award pages and the research page, not on the main Value list.

## Result (5 Nov 2026): all 10 pass
research/nba_nhl_award_eval.py -> model/award_eval_nba_nhl.json. In-season checkpoints at 10-90% of the season. Log loss of the eventual winner (model vs uniform pool baseline):

| Award | Seasons | Model | Baseline | Mean chance on winner | Favourite said / won (90% CI of gap) |
|---|---|---|---|---|---|
| NBA MVP | 17 | 1.388 | 3.219 | 43% | 57% / 62% (-0.19 to +0.09) |
| NBA DPOY | 17 | 2.911 | 3.199 | 15% | 35% / 26% (-0.07 to +0.23) |
| NBA ROY | 17 | 0.973 | 2.708 | 58% | 72% / 71% |
| NBA Sixth Man | 17 | 1.710 | 2.910 | 36% | 53% / 51% |
| NHL Hart | 15 | 2.658 | 3.559 | 22% | 36% / 40% |
| NHL Vezina | 15 | 1.734 | 2.556 | 33% | 49% / 44% |
| NHL Norris | 15 | 2.354 | 2.865 | 21% | 39% / 35% |
| NHL Calder | 15 | 1.675 | 2.836 | 31% | 48% / 44% |
| NHL Art Ross | 15 | 1.650 | 2.935 | 38% | 51% / 53% |
| NHL Richard | 15 | 1.104 | 2.708 | 49% | 60% / 64% |

- Every award beats the baseline overall and in each third of the season, and no favourite is significantly overconfident.
- NBA DPOY is the weakest: its favourites won 26% vs 35% said. The interval includes 0, but the lean is overconfident, so treat DPOY value with care.
- **Published:** pipeline/award_eval.attach adds `eval` to nba/data/awards.json and nhl/data/awards.json. Award probabilities are unchanged.
