# NBA "hustle" composites: decision rule written BEFORE any result (17 Oct 2026)

Question: does a team that rebounds and gets to the line a lot (the owner's "stocks"-style idea) win more in the future than its point margin so far
suggests? Our team ratings are built on margin, so a composite is only useful if it predicts FUTURE margin BEYOND current margin.

Data: ESPN-style team box scores in data/nba/team_box_<year>.csv (regular season, 2003-2026 end years); NBA Stats tracking hustle team files
(2017-2026; the 2016 file duplicates 2017, see pipeline/nba_hustle_synergy.py).

Composites (league-year z-scores, so eras are comparable):
- H1 "own": z(total rebounds per game) + z(free-throw attempts per game)   (exactly the owner's description)
- H2 "net": z(rebounds minus opponent rebounds per game) + z(FTA minus opponent FTA per game)
- T  "tracking" (2017-2026 only, full-season only): z(deflections) + z(loose balls recovered) + z(contested shots) + z(charges drawn) + z(box-outs), all per game

Outcomes: (a) the same team's margin per game over the rest of the season after checkpoint N = 20 and 41 games; (b) next season's full margin
(a team with fewer than 20 games next season is dropped). T can only be scored against (b) because the tracking files are season totals.

Model: future margin = a + b*margin_so_far (+ c*H). Fit pooled; scored leave-one-season-out (fit on the other seasons, predict the held-out one).
Score: held-out mean squared error of the future margin, A (margin only) vs B (margin + H). Gain = MSE_A - MSE_B (positive = H helps).
Intervals: bootstrap over seasons (90%). 2019-20 and 2020-21 are kept in the main sample and dropped in a sensitivity run.

A composite earns a pre-registered model trial (a shadow, not live) only if ALL hold:
1. Outcome (a), both checkpoints: pooled held-out gain > 0 with bootstrap 90% lower bound > 0, and better in at least 2/3 of seasons.
2. Outcome (b): gain > 0 with the same sign of c as in (a).
3. c has the same sign at both checkpoints and in (b), and the result holds without 2019-20 and 2020-21.
4. The gain is not a reflection of points already counted: also fit with offensive and defensive rating split instead of margin; the sign of c must survive.
Otherwise: not used in the model, reported as a descriptive statistic only. For T (nine season transitions only), the same conditions apply to (b) alone and a pass is a "needs more seasons" result,
not a trial.

Display is separate: rankings are shown on the site regardless of the result, labelled descriptive.
