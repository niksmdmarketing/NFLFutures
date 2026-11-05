# NBA futures replay: standing rule, version 1 (5 Nov 2026)
Applies to every NBA futures replay or challenger comparison from now on. Written after the joint team-and-player fail and the baseline audit (research/NBA_BASELINE_AUDIT.md), with GPT's corrections. Changes are dated amendments below; nothing above is edited. Historical passes qualify a challenger for forward testing only and never change the live model.

## 1. The baseline (A0)
- Command: `BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1` with `BT_ERA=1` (default), `BT_SIMS=2000`, and `NBA_STINTS` set to a directory of `stints_<season>.parquet` files built by research/nba_stints.py or research/nba_joint_stints.py. `python research/replay_nba.py <first> <last>`.
- Fixed seeds: simulation 20261009, playoff scenario draw 11. Same schedule, outcomes and seeds for every arm in a comparison.
- Era-correct (BT_ERA=1): no play-in before 2020-21, 72 games in 2020-21, the 2020 bubble season skipped.

## 2. Inputs are checked, never defaulted (enforced in code)
research/nba_replay_guard.py runs before any season and **stops the replay** (no fallback, no warning-and-continue) when any of these fails:
- the stints directory does not exist, or `stints_<s>.parquet` is missing for any season the run reads (y-1 and y-2 for every test season y; also y for the joint model or in-season RAPM);
- a stints file has fewer than 20,000 rows, or its recorded usable-game share is below 0.90;
- team box scores (five seasons back), player box scores (y-2 to y) or schedules are missing;
- the RAPM layer is inactive: a pre-season RAPM fit for the first test season returns fewer than 300 players or a rating spread below 0.05.
Tested on 5 Nov 2026: no directory, an empty directory and a truncated stints file each stop the run with the reason. `BT_SKIP_GUARD=1` exists for debugging only; a run made with it is not a baseline.

## 3. Provenance and reuse
- Every run writes `manifest.json` beside its output: code revision and any uncommitted files, SHA-256 of the replay and model code, all BT_*, NBA_* and NP_* settings (a partial run shows BT_MAXWEEKS), seeds, simulation count, seasons requested and written, stints directory, Python, numpy and pandas versions, SHA-256 and size of every input file, and SHA-256 of every output file.
- `python research/nba_replay_guard.py verify <output dir>` re-hashes inputs, code and outputs. On MATCH the saved baseline may be reused; on any difference it must be regenerated. Regenerating an identical, verified baseline adds nothing.
- Each rule that uses a baseline names its manifest.

## 4. Era-correctness
- Results from a replay with the wrong format (here BT_ERA=0, play-in applied to every season) are evidence only about that simulated format.
- Two arms run with the same wrong format are **not** automatically valid: a different playoff structure can affect two models differently. Conclusions about actual historical futures need an era-correct replay.
- Committed files model/replay/nba_<season>.csv: 2022-2026 reproduce exactly under the current command. 2016-2019 and 2021: status in section 7. 2013-2015: not checked, unverified.

## 5. Roster limitation and sensitivities (bias of unknown direction and size)
- The baseline roster convention knows every player who appears that season and his first team of the year, and none who never appear. It is not what a live forecast knows on a given date. Historical player-based results therefore carry **a bias of unknown direction and size**. No arm here estimates or bounds it.
- A1 (first team within a team's first 10 games, then last team played for) is a different convention with its own error: it drops players who first appear after game 10 (injured stars who return, mid-season debuts). A1 minus A0 (-0.0032 combined) cannot show the direction of the baseline's bias.
- NOLEAK (players absent all season stay on last season's team) is an **absence sensitivity**. It addresses one omission only. It is not a bound.
- Previous-team convention (a player stays on his previous team until he appears for another) is a further **sensitivity**. It misses known transfers until the player appears. Proposed; not built.
- Whenever a challenger changes player or roster logic (any roster step, player rating or minutes layer), run each chosen sensitivity on **both** the baseline and the challenger, and compare the paired gain (challenger minus baseline) under each convention. Report all of them. A challenger whose gain changes sign across conventions is not supported. Which sensitivities are required is written into that challenger's rule before any result.

## 6. Reporting
State the roster convention, era setting, manifest, and the words "bias of unknown direction and size" in every rule that depends on historical player data. A historical pass qualifies only for a forward shadow with the adoption rule written before the first forward score.

## 7. Status of older committed files
(Section filled by amendment 1 below after the full check.)

## Amendment 1 (5 Nov 2026): status of older committed files, checked in full
All five complete files model/replay/nba_2016, 2017, 2018, 2019 and 2021 were regenerated with the current code under `BT_ERA=0` (play-in format and 82 games in every season) and compared with the committed files on every checkpoint and team (24, 24, 25, 25, 20 weeks; 720, 720, 750, 750, 600 rows): maximum absolute difference 0.0 in title, finals, division, No.1 seed, playoffs, second round, conference finals, top six, play-in and mean wins. Under the current command (`BT_ERA=1`) they do not reproduce.
- Label: these five committed files are **"play-in format in every season (BT_ERA=0), verified exact"**. They are not era-correct and are not baselines under this rule.
- 2022-2026 reproduce exactly under the current command.
- 2013-2015 committed files: unverified.
- Earlier comparisons that used these files remain evidence about the simulated format only, per section 4. Any conclusion about actual 2016-2021 futures needs an era-correct replay.

## Amendment 2 (5 Nov 2026, after GPT's review of the rule)
1. **Gain convention.** Section 5's "challenger minus baseline" refers to the pairing, not the sign. Gain is always baseline log loss minus challenger log loss; positive means the challenger improves. The paired gain under a roster convention is the gain computed with both arms run under that convention.
2. **Previous-team sensitivity.** It stays unbuilt until a challenger needs it. Before any score is read for that challenger, its rule must fix (a) the exact construction (how a player's previous team is set at the first checkpoint, what happens to players with no previous team, and when a transfer is recognised), and (b) which comparisons are required (both arms, which conventions, which gain, how reported).
3. **Verification status.** GPT reviewed the rule text only. The guard implementation and the full-file comparisons in Amendment 1 are reported checks by Claude, not independently verified.
4. **Outcome unchanged.** The joint model failed, the live NBA model is unchanged, and no wider-grid rerun is justified. This work improves the reliability of the research; it has not produced a better forecasting model.

## Amendment 3 (5 Nov 2026)
Player box scores contain All-Star and Rising Stars games filed as regular season (team codes such as EAST, WEST, LEB, USA, WORLD). Any roster, minutes or player-value step must keep only rows whose team is one of the 30 NBA teams. Found in the joint test's revised rosters (rule Amendment 4 there); the live replay's own steps already filter to NBA teams or use first-team assignments that the All-Star game cannot change.
