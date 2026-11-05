# NFL extended futures baseline, 2013-2025 (5 Nov 2026)
Research infrastructure under the plan recorded in research/TEST_POWER_RULE.md (Amendment 2). Not evidence for a better model. Gates in later rules are unchanged.

## What it is
Weekly point-in-time replay of the live NFL futures model (v4 + final-week rest), seasons 2013-2025, one row per team per checkpoint (pre-season, then after every regular-season week). Output: model/replay/nfl_ext/nfl_<season>.csv with manifest.json.

Command: `BT_COEF=wf BT_REST=1 BT_OUTDIR=model/replay/nfl_ext python research/replay_nfl.py 2013 2025` (BT_SIMS 4000 default, simulation seed 7).

## Settings and why
- **Walk-forward rating weights (BT_COEF=wf):** season y uses weights fitted on 2010 to y-1 only (model/replay/nfl_wf_coef.json). The live v4 weights were fitted on 2010-2021, so without this the seasons before 2022 would be in sample.
- **Final-week rest (BT_REST=1, 17.891 points):** live since 5 Nov 2026, so the baseline includes it. Its value was estimated on games from 2004 onward and checked leave-season-out on 2020-2025.
- **Era playoff format:** 6 seeds to 2019, 7 from 2020. research/replay_nfl.py passed no format before 5 Nov 2026 and so simulated 7 seeds for every season; fixed the same day (no effect on 2020 onward). Earlier NFL tests on 2013-2025 used their own scripts, which already passed the era format.
- **Not out of sample:** pseudo-counts, ridge strength, rating scale 0.89, tau 5.0, sigma 11.37 and home edge 1.8 were chosen on overlapping seasons (2010-2021 and 2022-2025). Walk-forward weights do not remove that exposure. QB and injury layers are off (no weekly history).

## Point-in-time timing (code check)
At checkpoint w: ratings use this season's play-by-play with week <= w and the whole of last season; schedule results after week w are masked before simulation; outcomes come from final standings and the Super Bowl only for scoring.

## Input check (research/nfl_extended_check.py, passed)
Every season 2013-2025: 256 regular-season games and 17 weeks to 2020, 272 and 18 from 2021 (2022: 271, the cancelled BUF-CIN game); every result present; play-by-play covers 100% of regular-season games for the season and the one before; 32 teams, 8 division winners, 12 seeds to 2019 and 14 from 2020 in the standings; Super Bowl result present; walk-forward weights present for every season and stated as fitted on earlier seasons only.

## Reproduction of committed files
The committed model/replay/nfl_2022.csv (fixed v4 weights, no rest) does not reproduce exactly with the current code and data under the default settings: max difference 0.014 (make playoffs), 0.011 (division). The repository history before 5 Nov 2026 is squashed, so the settings and data versions behind those files cannot be recovered; nflverse data revisions are a likely cause. They are labelled "not reproducible; settings unknown" and are not baselines.

## Use in later rules
Every NFL futures rule reports both windows, chosen before scoring: recent 2022-2025 and extended 2013-2025. Older seasons may represent different conditions (pre-2021 16-game seasons, 6-seed format, rule and style changes). Reuse this baseline only when `python research/nfl_extended_manifest.py verify` reports MATCH; otherwise regenerate.
