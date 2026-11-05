# NHL futures: starting goalie in the roster term, canonical production-equivalent comparison. Rule, version 1

Written 5 Nov 2026 (Sydney), before any replay under this configuration was run. Amendments are added below with dates; nothing above them is edited.

## Why
- research/NHL_GOALIE_ROSTER_RULE.md is unresolved. Claude's run (fail) and GPT's run (pass, research/NHL_GOALIE_ROSTER_FINDINGS.md) used different configurations, and neither matched production:
    - Claude's left out the live 20% regular-season xG share and included a 2014 fallback to the old model.
    - GPT's set NHL_XG=adj, which also changed the playoff rating input (live uses shots).
    - Both ran without the overtime fix that went live on 4 Nov.
- Agreed next step (GPT review; TypeSafe 64% as the first reweighting to test; owner asked 5 Nov): freeze one production-equivalent baseline, then change only the goalie term.

## Baseline = live NHL futures as of 5 Nov 2026, as far as history allows
research/replay_nhl.py (through research/nhl_goalie_roster_replay.py, which fails if RAPM inputs are missing) with:

`BT_SIMS=2000 NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_RS_SHOT_W=0.2 NHL_RS_XG=raw NHL_PO_FADE=3 NHL_OT_FIX=1 NHL_OT_EDGE=0.5 NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0 NHL_LINEUP_VAL=rapm RAPM_LAM=300000 RAPM_KBOX=1 NHL_LINEUP_GS=0`

How each setting maps to live (pipeline/nhl_model.py, nhl_lineup.py):
- **Regular-season rating:** 80% goals and 20% MoneyPuck xG differential (XG_SHARE 0.2). The new NHL_RS_XG=raw switch makes the replay use MoneyPuck game xG for that share, as live uses the team table's MoneyPuck xG.
- **Playoff rating:** shot differential x league shooting % (shot_rates), with no xG (NHL_SHOT_W=1, NHL_XG unset).
- **Playoff fade:** 3.0 (PO_FADE).
- **Overtime:** the fix with OT winner edge 0.5 (OT_EDGE).
- **Roster term:** lineup RAPM skater ratings over the last 5 games vs the season, with no last-season part (live_term: n=5, pre=False). Goalie scale 0 (live has no goalie part).
- **Pre-season uncertainty:** TAU_PRE 1.5, the module default, as live.

**Not replayable, so identical (absent) in both arms:** the injury layer (no dated injury history), and live's injured-player add-back in the roster term.

## Variant
The same command with `NHL_LINEUP_GS=0.438`, the starter scale already fitted at game level (nhl_absence.SCALE_G and nhl_lineup.GOALIE_GS). Nothing else changes. No sensitivity runs.

## Inputs, frozen and shared
- **Shift data, stints, shots and leave-one-season-out shot xG:** /home/claude/shiftbr. **Lineups:** data/research/nhl_lineups. **MoneyPuck team games:** data/research/mp.
- **RAPM skater ratings:** written once to a new cache directory before either arm runs. Both arms then read the same files, and their SHA-256 hashes are recorded.
- **Goalie ratings:** research/nhl_rapm.goalie_ratings (seasons before y, shrunk by 2,500 shots). The wrapper records identities, and the scorer requires both arms to match.

## Seasons
2015-2018 and 2021-2025 (9 seasons). 2014 is excluded because no earlier RAPM data exists. The other seasons are excluded because the replay does not support them (alignment or format).

## Scoring
research/nhl_goalie_roster_score.py (GPT's strict paired scorer: same keys, outcomes and rating identities), using research/nhl_holdout.py, baseline first.
- Markets: playoff, division, Presidents' Trophy, round 2, round 3, final, title.
- Gain per market and combined (mean of markets), with a 90% bootstrap over seasons (4,000 draws, seed 1).

## Decision
- **Pass:** the combined 90% lower bound is above 0, and no market's mean gain is below -0.0005.
    - The goalie part is then cleared for a live decision. The owner and TypeSafe decide after seeing the full result.
    - The archived g_* shadow keeps collecting either way.
- **Fail:** anything else. Live is unchanged; the question is closed for this implementation (scale 0.438, recent-lineup term). The g_* shadow keeps collecting through 2026 for the record only.

## Limits, stated now
- 0.438 was fitted at game level on overlapping seasons, and the shot-xG builder uses leave-one-season-out calibration that includes later seasons. This is development evidence, not untouched validation.
- The term compares recent lineups with the season's, so a goalie who arrived before the season and played every game adds nothing (for example, Hellebuyck at New Jersey). That is a separate question.
