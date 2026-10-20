# NBA: player-first game model vs the current team model. Rule written BEFORE any result (20 Oct 2026)

Asked by the user: a separately designed model that gives player ratings more weight, compared with the current one. TypeSafe: build it (99%; re-asked after correcting the record, 83%).
Already known, so not repeated: weekly refits of player ratings mixed into the team rating at 15-30% made futures slightly worse (WORKLOG 14 Oct 2026); pre-season player strength alone was worse than the team rating but a 40% mix was better (deployed). Not yet tested: a standalone player-first prediction for each game, built from the players expected to play that game.

## Data and point in time
Regular-season games, seasons 2014-2026 (season = end year). Weekly checkpoints as in research/us_match_ratings.py: every game in week w of a season is predicted from information before the first day of that week. Lineup stints: /home/claude/nbapbp/stints (rebuilt from ESPN play-by-play by research/nba_stints.py); player minutes: data/nba/player_box_<y>.csv.

## Models
- A (current): the live in-season team rating, nba._fit_ratings refitted weekly on games before the week (live settings), margin = (net gap + home edge) x pace, as in us_match_ratings.py.
- B (player-first): player ratings = RAPM refitted weekly from all stints before the week (research/replay_nba._player_ratings with cutoff: last season weight 1, the season before 0.5, this season's stints weight 1, ridge 3000 toward 2.5 x box-score value, young-player development as live). Team strength for a game = sum over the expected players of rating x expected minutes / 48. Expected players and minutes, strictly before tip-off: the players who played in the team's previous regular-season game; expected minutes = each one's average over his last 10 games played (any team), scaled so the team totals 240. Players with no rating: -1. First game of a season: the players of the team's last game of the previous season who have not appeared for another team since (none have yet) - i.e. last season's final rotation.
- C (combined): margin from A and B together.
For B and C the margin is a linear function (intercept + slope(s)) fitted by least squares on all earlier test seasons' games only (walk-forward); the first season, 2014, is used only for fitting. A is given the same walk-forward linear recalibration (a + b x A's margin), so A is not handicapped by scale. Win probability = Phi(margin / sd), sd = residual sd on the earlier seasons.
Best case, reported only: B and C with the players who actually played and their actual minutes.
Not included: the live game-level availability layer, because before 2021 it uses who actually played (game-day information); A here is the team rating alone.

## Test
Test seasons 2015-2026 (12). Measures: margin MSE, win log loss, calibration slope (actual margin on predicted).

## Gates (B vs A and C vs A separately; all must pass for that model)
1. Pooled margin MSE lower, season-bootstrap (2,000 draws) one-sided lower bound at 2.5% (5% split over two challengers) above zero.
2. Better (lower MSE) in at least 8 of 12 seasons.
3. Lower win log loss.
4. Better in both the first 20 team games of a season and later.
5. Calibration slope between 0.8 and 1.2.
Reported, not gated: the actual-lineup best case; by-season gains; the fitted weights.

## Decision
TypeSafe decides. A pass leads to a futures replay test (same rule style) before anything reaches the site; a fail is recorded. Nothing live changes from this test.

## Outcome (20 Oct 2026) - player-first alone fails; combined passes all gates
Run: research/nba_player_first_test.py build / score (rows data/research/nba_player_first_rows.csv, results research/nba_player_first_results.json). 14,440 test games, 2015-2026.

| Model | Margin MSE | vs A | Seasons better | Log loss | Gates |
|---|---|---|---|---|---|
| A team rating | 179.3 | - | - | 0.6201 | - |
| B player-first (previous-game lineup) | 192.9 | -7.6% | 0 of 12 | 0.6489 | fail |
| C combined | 177.7 | +0.93% (lower bound +1.11) | 12 of 12 | 0.6172 | **pass all five** |
| Best case B / C with actual lineups | 195.5 / 178.0 | -9.0% / +0.72% | - | 0.6499 / 0.6170 | reported only |

C: early (first 20 team games) +1.24, later +1.81; slope 1.006. The player term's walk-forward weight rose from 0.06 (2015) to 0.26 (2026) as the stint history grew; the team-rating weight fell from 0.96 to 0.85.
Actual lineups do worse than previous-game lineups because actual minutes include garbage time, which is shaped by the result; so the pre-game version is not leaning on hidden information.
Reading: player ratings alone are much noisier than team results, but as a second opinion on top of the team rating they help every season, a little.
Caveats: A is the team rating alone; the live single-game predictions also use the availability layer, which overlaps with C's lineup information. Futures not tested.
Decision (TypeSafe 97%): before any live use, test (1) whether C still adds on top of the live availability layer for single games and (2) a futures replay with C's player term; shadow only until both pass.

## Amendment 1 (20 Oct 2026, written before either result): the two follow-up tests
**Test 1 - on top of the availability layer (single games).** Per-game availability values from research/nba_availability2.py (cached file nba_avail2_games.csv, joined on date, home, away).
- 1a, all test seasons 2015-2026: availability = v2_base (the version whose test justified deployment; before 2021 it uses who actually played, so it is generous to the baseline). A' = walk-forward linear on [A margin, availability difference]; C' = [A margin, player strength difference, availability difference]. Gates for C' vs A': MSE lower with season-bootstrap 90% one-sided lower bound above zero; better in at least 8 of 12 seasons; lower log loss.
- 1b, strictly pre-game: games covered by official pre-game injury reports (2022 onward, variant v2_official, the live input). Same models and gates, except the bootstrap resamples whole weeks and the season count is "better in a majority of covered seasons".
Both 1a and 1b must pass.
**Test 2 - futures.** research/replay_nba.py with the live settings (BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1; these reproduce the committed model/replay/nba_*.csv, which are the baseline) plus a new option BT_PF=1: at each checkpoint the team rating becomes rating + k x (S - mean S), S = player strength of the team's latest lineup (RAPM refitted at the checkpoint with this season's stints, expected minutes as in model B), k = c / b from Test-0's walk-forward C weights for that season (player-strength weight over team-rating weight). The playoff rotation is unchanged. Seasons 2015-2026 except 2020 (skipped by the replay): 11 seasons.
Gates: mean log loss over title, conference, division, No. 1 seed and playoffs lower, season-bootstrap 90% interval above zero; better in at least 7 of 11 seasons; no single market worse by more than 0.002.
**Decision:** TypeSafe decides. Both tests pass: player term goes to the site as a shadow beside the live model first (single-game and futures), then live by TypeSafe decision. Either fails: recorded.
