# NBA replay baseline audit (5 Nov 2026)
Bounded audit after the joint-model fail (research/NBA_JOINT_TEAM_PLAYER_RULE.md, Amendment 3). Uses only data and outputs already in the repo and the joint-test run. No new model, no tuning. Written to fix how later NBA challengers are compared.

## 1. What future information each roster convention uses
| Convention | Pre-season roster | In-season roster | Future information it uses |
|---|---|---|---|
| **A0** (live replay, research/replay_nba.py `_season_extras`) | each player's first team anywhere in the season | static, same all season | Knows every player who plays at all that season, including stars who miss the start and return later and mid-season signings; knows each player's first team of the year. Excludes players who never play. |
| **A1** (BT_ROSTER=v2) | first team within that team's first 10 games | last team played for before the checkpoint | Knows who plays in a team's first 10 games (early-season transactions, injury returns by then). Does not know players who first play after game 10. In-season rosters use only past games. |
| **NOLEAK** (BT_FULL_NOLEAK=1) | adds players who sit out the whole season on last season's team | same | Closer to a live roster for absentees only. Still uses first-appearance team for everyone who plays. |
| **Live forecast** | current roster at the time (transactions known to the minute) | same | None. This is the only unbiased convention, and no historical transaction feed is available here. |

No replay convention here equals the live forecast. A0 over-includes (late-returning and mid-season players are on the roster from week 0). A1 under-includes (anyone first appearing after team game 10 is missing from the pre-season roster).

## 2. A1 minus A0 (positive means A1 better), same era settings, 10 test seasons
Combined -0.0032, 2 of 10 seasons better (90% -0.0046 to -0.0018).
- By season (combined across markets): 2016 -0.0069, 2017 +0.0002, 2018 -0.0025, 2019 -0.0057, 2021 -0.0056, 2022 +0.0019, 2023 -0.0020, 2024 -0.0011, 2025 -0.0060, 2026 -0.0044.
- By market (mean over seasons): title -0.0018, finals -0.0048, division -0.0085, No.1 seed -0.0003, playoffs -0.0007. Division is the biggest loser, then finals.
- By stage (combined): pre-season -0.0055, games 1-19 -0.0044, 20-41 -0.0019, 42+ -0.0034. The loss is largest before the season and does not vanish once everyone has played.
- Pre-season only: division -0.015, finals -0.004, playoffs -0.006. The biggest single-season pre-season losses are 2016 (all markets), 2025 (division -0.063, playoffs -0.038) and 2026 (division -0.046).

## 3. Which players and assignments drive it
- The difference is almost all **omissions**, not changed teams. Players who first appear after their team's 10th game are missing from A1's pre-season roster: 60 to 163 per season, 12 to 29 per season with 500+ minutes. Players on a different team in A0 and A1 pre-season: 0 to 4 per season.
- Largest omissions by minutes: 2016 Kyrie Irving (CLE, 1,665 min), 2017 Jrue Holiday (NO) and Patrick Beverley (HOU), 2018 Nicolas Batum (CHA) and Rajon Rondo (NO), 2019 DeMarre Carroll (BKN), 2021 Kemba Walker (BOS), 2022 Pascal Siakam (TOR, 2,579), 2023 Dennis Schroder and Markelle Fultz, 2024 Miles Bridges (CHA, 2,586), 2025 Trey Murphy III and Isaiah Hartenstein, 2026 Paul George (PHI).
- Largest pre-season rating shifts A1 vs A0 (points per 100): 2016 CLE 1.70; 2018 SA 3.30; 2024 MEM 2.67; 2025 LAC 3.05 and NY 2.28; 2026 MEM 3.50, BOS 2.82 and CHA 2.67. Mean absolute shift across all teams 0.39.
- Reading: many of these are injured stars or players on long absences. A0 keeps them on the roster from week 0, which a live forecast also would (they are signed to the team, and injury news is known). A1 drops them, which a live forecast would not. So the A1 loss is partly an error in A1's roster rule, not only evidence of A0's lookahead. A1 is not a cleaner baseline; it is differently flawed. This corrects the earlier wording that A1 "removes the lookahead".

## 4. Provenance of the committed replay files (model/replay/nba_<season>.csv)
- 2022-2026: reproduced exactly (max difference 0.0 in every market and mean wins) by the current command: BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1, default BT_ERA=1, BT_SIMS=2000, on the stints rebuilt here (NBA_STINTS pointing at a directory of stints_<y>.parquet; with no stints directory the RAPM layers silently return nothing and the output is wrong).
- 2016-2019 and 2021: do **not** reproduce under BT_ERA=1. They reproduce exactly (max difference 0.0 on the first three checkpoints of 2016 and 2021) with **BT_ERA=0**, so they were built with the play-in format and 82 games applied to every season. Under the era-correct setting (BT_ERA=1: no play-in before 2020-21, 72 games in 2021) playoff probabilities differ by up to 0.25 and 2021 mean wins by 7.0.
- Label: those five committed files are "play-in format in every season (BT_ERA=0)". Nothing earlier in the NBA scoring that used them is wrong as a comparison among arms run with the same setting, but their absolute log losses are not era-correct, and any score compared across the two settings is invalid. The 2013-2015 files were not rechecked.
- The A0 arm of the joint test used BT_ERA=1 for all arms, so the joint-test comparisons are internally consistent.

## 5. Baseline convention for later experiments (proposal, to be confirmed)
1. Use BT_ERA=1 (era-correct) and BT_FULL=1 with the live playoff settings as A0 for the baseline, regenerated fresh for any new test, with the stints directory path and the command recorded in the rule.
2. State the residual lookahead in every new rule: A0 knows every player who plays that season and his first team; it does not know players who never play.
3. Report the NOLEAK arm alongside, since it bounds one part of the leak. Do not describe A1 as leak-free.
4. Where a challenger's change interacts with rosters (any new roster or player-based layer), run both A0 rosters and a rule that keeps a player on his previous team until he plays for another (a closer analogue of what is known live). The new rule is not built or tested here.
5. Treat all historical NBA player-based results as optimistic by an unmeasured amount. A1 minus A0 (-0.0032) is not an estimate of it: A1 loses information A0 legitimately has (injured players signed to the team) as well as the lookahead, so its size says nothing about which way the net bias runs.

## Not done
- No transaction feed: nothing here can recreate the live roster at each date, so the lookahead cannot be removed, only bounded.
- 2013-2015 committed files not rechecked.
- The previous-team-until-new-team convention in point 4 is proposed, not implemented.

## Corrections (5 Nov 2026, after GPT's review; text above is not edited)
- Section 5, point 3: NOLEAK is an **absence sensitivity**, not a bound. It addresses one omission and establishes neither an upper nor a lower bound on forecast bias.
- Section 5, point 5: historical NBA player-based results carry **a bias of unknown direction and size**, not an "optimistic" bias. A1 minus A0 cannot determine the direction.
- Section 5, point 4: the previous-team convention is a further sensitivity; it misses known transfers until a player appears. Roster sensitivities are applied to both baseline and challenger and the paired gains compared.
- Section 4: the claim that the five older files reproduce under BT_ERA=0 was based on the first three checkpoints of 2016 and 2021. All five complete files have since been checked and match exactly (standing rule, Amendment 1). Also withdrawn: "nothing earlier is wrong as a comparison among arms run with the same setting". Arms sharing a wrong playoff format are not automatically valid, because the format can affect models differently.
- The audit's missing-stints observation is now enforced by code (standing rule section 2), not by recording a directory path.
Standing rule: research/NBA_REPLAY_STANDING_RULE.md.

## Correction 2 (5 Nov 2026)
A1's pre-season and in-season rosters also suffered from an All-Star bug (research/NBA_JOINT_TEAM_PLAYER_RULE.md, Amendment 4): All-Stars were moved onto the All-Star sides at the checkpoint after the All-Star game. Without those ten checkpoints A1 vs A0 is -0.0028 (3 of 10 seasons better) instead of -0.0032. The audit's conclusions about late-returning players stand.
