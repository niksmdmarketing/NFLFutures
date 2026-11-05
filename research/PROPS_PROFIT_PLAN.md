# Player props: plan to find out whether they can be bet profitably (6 Nov 2026)
Goal: bet player props only where the evidence shows the models beat market prices. NBA first, NFL second, other sports only after one of these shows something. TypeSafe ordered the overnight work (6 Nov 2026).

## Price sources
- OddsPapi (owner signed up 6 Nov; key to be added tomorrow as ODDSPAPI_KEY): historical odds free of quota from January 2026; current odds 250 requests a month. Books DraftKings, FanDuel, Pinnacle (max 3 per request). Scripts ready in the private repository: pipeline/oddspapi_nba_history.py and workflow "OddsPapi player-prop history (NBA, NFL)", modes discover and backfill, sport nba or nfl.
- PrizePicks lines: GitHub servers blocked (HTTP 403); a PC collector package was delivered as a backup reference.
- Kalshi and Polymarket: no standard player prop markets (checked 6 Nov).

## Tasks
| # | Task | Owner | When | Status |
|---|---|---|---|---|
| 1 | NBA props price test rule (research/NBA_PROPS_PRICE_TEST_RULE.md) | Claude | overnight, first (TypeSafe 91%) | written |
| 2 | OddsPapi scripts aligned with the rule's information times (60 min, 6 h, close); NFL option | Claude | overnight | done |
| 3 | Scoring code: de-vig, main line, edge, closing-line value, date-clustered bootstrap, logistic information test; tested on synthetic data | Claude | overnight | done (research/nba_props_price_test.py, nba_props_price_run.py) |
| 4 | NBA player-name matching (bookmaker names to ESPN ids), tested on ESPN rosters | Claude | overnight | done (research/nba_props_names.py, 99.8% on synthetic variants) |
| 5 | NBA window-1 forecasts (1 Jan 2026 to end of regular season) from the frozen 2026b parameters, 60 min, ready to join | Claude | overnight | running (489 replay runs; 325 done to 10 Mar 2026 and checkpointed to the private repo, research_archive/nba_props_window1; 164 left, resumable with research/nba_props_window1.py) |
| 6 | NFL: point-in-time prop probabilities from the frozen NFL props model for 2026 (January playoffs if in scope, and 2026-27 weeks so far); NFL name matching; NFL price-test rule draft; review of the NBA rule | GPT | overnight (TypeSafe 65% for GPT) | handed over |
| 7 | Owner adds ODDSPAPI_KEY; Claude runs discovery (about 5 counted requests) then the free backfill for NBA, then NFL | Owner, Claude | tomorrow | waiting |
| 8 | Mechanics check, then scoring under the rule | Claude | after 7 | waiting |
| 9 | Forward daily collection within 250 requests a month | later | only if a stat passes | deferred |
| 10 | Other sports (NHL shots, soccer) | later | only after NBA or NFL shows something | deferred |

## Notes (6 Nov 2026, overnight)
- Window-1 check on the first 167 cutoffs (242 games, 8,720 player rows): every row has points, rebounds and assists distributions (v2 and v3); no record generated after its cutoff. Mean predicted points given appearing 10.1 vs 10.6 actual for players who played. Players without a box-score row are mostly low appearance probability (mean 0.19), as expected for players who did not play.
- Four games in window 1 were postponed (401810384, 401810499, 401810506, 401810507). They have forecasts but no results; the scoring drops them because it keeps only players with minutes above zero.
- Four cutoffs on 15 Feb 2026 (All-Star weekend) had no target games and logged ok=False with nothing to forecast; expected.
