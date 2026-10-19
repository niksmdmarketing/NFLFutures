# NBA: does DARKO add to our game forecasts? Rule written BEFORE any result (19 Oct 2026)

TypeSafe (19 Oct 2026) listed this as part of the NBA early-season set-up. DARKO (darko.app) data are used privately with the source's permission; the raw snapshots stay on the user's computer and are never committed. Only derived numbers (log losses, counts) appear in this repository.

## Point in time
A game on US date D is predicted from the latest DARKO snapshot whose capture date (UTC, field as_of_utc) is strictly before D, exactly the rule our own published forecasts follow (snapshot date < game date). Days without a snapshot use the previous one. No snapshot, no DARKO prediction: that game is dropped from the comparison for BOTH models, so every comparison is on identical games. Snapshots are never edited or back-filled. The first snapshot is 18 Oct 2026 (before tip-off).

## Candidate D (frozen now; nothing is fitted to results)
Team strength S = sum over the team's players (tm_id) of (x_minutes / 48) x dpm. This is net rating per 100 possessions for a full lineup.
Margin for home team h against away a: M = (S_h - S_a) x 1.0 + 2.3 (home edge; 0 at neutral sites).
Win probability P_D = Phi(M / 12.0).
Blend B = 50/50 in logit space of our published pre-game probability (the Outlook page's, from the forecast archive) and P_D. No weights are fitted.
Team code crosswalk: DARKO team_name to the site's team codes (research/nba_darko_test.py, TEAM_CODE); unmatched names stop the run.

## Test
Checkpoint 1: the first date on which every team has played at least 20 games. Checkpoint 2: 41 games per team. At each checkpoint all completed regular-season games so far, on games with both predictions.
Measures: log loss of ours (O), D, B; Brier; calibration slope of B; paired difference O - B in log loss with a 90% interval from a day-block bootstrap (resampling game days, 2,000 draws); the same difference in the first and second chronological halves of the games.

## Gates (all, at checkpoint 1)
1. Log loss of B below O, with the 90% interval above zero.
2. B better than O in both chronological halves.
3. Calibration slope of B between 0.8 and 1.2.
4. D alone no worse than O by more than 0.010 in log loss (a sanity check that the mapping is sensible, not a requirement that D wins).
Reported, not gated: results at checkpoint 2; D alone against O; by home/away favourite; weights a stacked fit would choose (walk-forward, not used).

## Decision
TypeSafe decides. Pass at checkpoint 1: B is shown on the NBA Outlook as a labelled shadow for the rest of 2026-27 and must still hold at checkpoint 2 before it replaces anything; no change to the live NBA forecast within this season. Fail: recorded here; DARKO stays unused. One season is a small sample, so even a pass is a shadow, not a replacement.

## Not covered
Our own player-availability layer is a separate shadow with its own rule (research/ nba_avail tests). DARKO's minutes already reflect its own injury view, so this test measures DARKO as a whole, not availability alone.
