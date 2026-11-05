# NBA data quality before extending replays earlier (5 Nov 2026)
Plan step from research/TEST_POWER_RULE.md (Amendment 2): check data quality, not just downloads, before extending NBA replays. Report only; nothing extended. Script: research/nba_early_data_check.py; numbers: research/nba_early_data_check.json.

## Per season (regular season)
| Season | Box games | Play-by-play games | Games with rebuilt lineups | Usable share | Possessions per game | Stint vs box minutes (corr / ratio) | Old team codes |
|---|---|---|---|---|---|---|---|
| 2003 | 1189 | 967 | 940 | 0.97 of pbp, **0.79 of box** | 84.9 | 0.994 / **0.80** | NJ, SEA (29 teams) |
| 2004 | 1189 | 1175 | 1170 | 0.996 | 84.9 | 0.9997 / 1.00 | NJ, SEA (29 teams) |
| 2005 | 1228 | 1219 | 1129 | **0.926** | 86.6 | 0.982 / 0.94 | NJ, SEA |
| 2006 | 1218 | 1216 | 1074 | **0.883** | 86.3 | 0.966 / 0.91 | NJ, SEA |
| 2007 | 1228 | 1215 | 1179 | 0.970 | 87.1 | 0.997 / 0.99 | NJ, SEA |
| 2008 | 1230 | 1218 | 1207 | 0.991 | 88.1 | 0.999 / 1.02 | NJ, SEA |
| 2009-2011 | 1229-1230 | 1226-1229 | 1225-1227 | 0.998-0.999 | 87.9-88.6 | 0.9995+ / 1.04 | NJ |
| 2012 | 990 (66-game lockout) | 991 | 987 | 0.996 | 87.7 | 0.9998 / 1.04 | NJ |
| 2013-2026 | as already used | | | 0.96-1.00 | 87.8-96.0 | 0.997-0.9998 / 1.01-1.09 | All-Star sides only |

## Findings
1. **Lineup data are good from 2007 and excellent from 2009.** 2003 (play-by-play covers only 79% of games; stint minutes 80% of box minutes), 2005 and 2006 (usable 93% and 88%; minutes correlation 0.98 and 0.97) are not good enough. 2006 also fails the standing rule's 90% usable-game check.
2. **Earliest valid test season is 2009.** The pre-season RAPM needs stints from y-1 and y-2, so y = 2009 uses 2007 and 2008. That extends the NBA window from 2013-2026 to 2009-2026 (4 more test seasons, 2009-2012).
3. **Era handling needed first (code, before any extended run):**
   - Team codes: NJ (to 2012) is Brooklyn and SEA (to 2008) is Oklahoma City. The game-level fit and every roster step currently keep only today's 30 codes, so those teams' games are silently dropped. A franchise mapping is needed (it also affects the existing 2013-2014 replays, whose training seasons include NJ).
   - 2012 was a 66-game season (the replay treats every pre-2021 season as 82 games).
   - Before 2015-16, division winners were guaranteed a top-four seed; the simulator does not apply that.
   - 2003-2004 had 29 teams and different divisions (not needed if the window starts at 2009).
4. **All-Star and Rising Stars games are filed as regular season** in the box scores (codes EAST, WEST, LEB, USA, WORLD and others). Every roster or minutes step must drop them (standing rule Amendment 3).
5. **Stint minutes run 4-9% above box minutes from 2009 onward** (higher since 2021). RAPM weights by possessions, not seconds, so the ratings are unaffected; any use of stint seconds would need a check.

## Recommendation (for owner and GPT; not done)
Extend the NBA window to 2009-2026 only after the era fixes in finding 3 are written as a dated change, verified on 2009-2012, and the existing 2013-2026 baseline is regenerated with the franchise mapping (it changes 2013-2014). Report recent and extended windows separately in later rules.
