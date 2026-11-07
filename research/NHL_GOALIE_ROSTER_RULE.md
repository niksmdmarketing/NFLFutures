# NHL futures: put the starting goalie back into the live roster term. Rule, version 1

Written 4 Nov 2026 (Sydney), before any replay of this variant was run. Amendments are added below with dates; nothing above them is edited.

## Why
- On 15 Oct the roster term switched from points/GSAx values to RAPM skater ratings (model/nhl_player_ratings_2026.csv). The comparison scored +0.0003 (5/10, not significant).
- `nhl_lineup.live_term` calls `game_values_ratings(S, rp)` with no goalie part. The old values included the starting goalie (SCALE_G × his value). So **since 15 Oct the starting goalie is not in the live roster term**, and goalies reach live NHL futures only through the injury list.
- Dropping the goalie was a side effect of the switch. It was never tested on its own.
- Game-level evidence says the starter matters: tonight's starter vs the team's usual goalie, scale 0.438 (se 0.176), t about 2.6 (research/nhl_absence_test.py).
- **Example:** the Hellebuyck trade (23 Oct) adds nothing to New Jersey's roster term.
- TypeSafe was split (leave it 49%, test it 36%, low confidence); the owner asked for the test.
- The in-season goalie value test (research/NHL_GOALIE_INSEASON_RULE.md) failed, but it ran on the older points/GSAx setup, so it does not answer this question.

## Baseline (live)
research/replay_nhl.py with:

`NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_PO_FADE=3 NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0 NHL_LINEUP_VAL=rapm RAPM_LAM=300000 RAPM_KBOX=1`

This is the live roster setup. The 20% regular-season xG share is left out on both sides (measured +0.0001).

## Variant
The same settings plus `NHL_LINEUP_GS=0.438`. Each game's lineup value adds 0.438 × the starting goalie's goals saved above expected per unblocked shot × 40 shots (`game_values_ratings`, goalie ratings from research/nhl_rapm.py: seasons before y, shrunk by 2,500 shots).
- 0.438 is the starter scale already fitted at game level (nhl_absence.SCALE_G), fixed here before results.
- Nothing else changes.

**Sensitivity, reported only:** `NHL_LINEUP_GS=1.0`. It cannot rescue a fail.

## Inputs
- Shift data from branch nhl-shifts-data (stints, shots, players 2014-2026), with xG from research/nhl_xg.py (leave one season out).
- Lineups: data/research/nhl_lineups.
- Seasons: those the replay supports (2014-2018, 2021-2025), 2,000 simulations.

## Scoring
- research/nhl_holdout.py, baseline first.
- Gain per market (playoff, division, best record, round 2, round 3, final, title) and combined (mean), with a 90% bootstrap over seasons.

## Decision
- **Pass:** the combined 90% lower bound is above 0, and no market's mean gain is below −0.0005. Then the live roster term gets the goalie part, first as a shadow next to live NHL futures. Its goalie ratings are built the same way as model/nhl_player_ratings_2026.csv, from seasons before 2026.
- **Fail:** anything else. Live stays as it is.

## Result (4 Nov 2026; 2,000 sims, 10 seasons; inputs rebuilt from nhl-shifts-data with research/nhl_xg.py)
research/nhl_holdout.py, live first. Gain, 90% bootstrap over seasons:
- **NHL_LINEUP_GS = 0.438 (primary):** combined +0.0001 (-0.0000 to +0.0003), better in 7/10 seasons.
  - Round 3 +0.0007 (+0.0003 to +0.0011) and final +0.0006 (+0.0003 to +0.0008).
  - Division -0.0005 (-0.0012 to +0.0001).
- NHL_LINEUP_GS = 1.0 (sensitivity): combined +0.0002 (-0.0001 to +0.0006), 6/10; playoff +0.0006, division -0.0005.

**Decision under this rule: FAIL** (the combined lower bound is not above 0). Live stays as it is. The starter helps the playoff-round markets but costs the division market about as much.

## Amendments
**5 Nov 2026 (Sydney): the result above is superseded.** GPT re-ran this rule on branch codex/nhl-goalie-roster-check-20261105 (5afbbb5; findings in research/NHL_GOALIE_ROSTER_FINDINGS.md there) and found two flaws in the run recorded above:
1. **2014 used the old model.** No earlier RAPM data exists for 2014, so that season silently fell back to the old points/GSAx values in both arms.
2. **The arms were unpaired.** The baseline used freshly fitted skater ratings and the variant read them back from the CSV cache, so the inputs differed by float serialisation.

GPT's corrected run excluded 2014 by a coverage amendment committed before any replay, and used one frozen, byte-identical RAPM cache for both arms. Over 9 seasons:
- combined +0.000317, 90% season bootstrap [+0.000136, +0.000501], better in 7/9;
- all seven market mean gains positive.

That is a **PASS** under this rule.

TypeSafe (96%, confidence 0.94): treat the paired run as the valid result, and build the goalie part as a shadow next to live NHL futures, as the Decision section says.
- **Live from 5 Nov 2026 as a shadow only:** nhl_model publishes g_playoffs / g_div / g_final / g_cup / g_roster, and pipeline/sport_archive.py archives them as g_*.
- **Goalie ratings:** model/nhl_goalie_ratings_2026.csv, from research/nhl_rapm.goalie_ratings(2026), seasons 2023-2025, built 5 Nov 2026.
- **Displayed NHL probabilities are unchanged.** A live switch needs its own forward-scored decision.

**5 Nov 2026, later (correction to the amendment above):** GPT has since corrected its own description: its passing run was **not production-equivalent**. It set `NHL_XG=adj`, which also changes the playoff rating input; the live playoff rating uses shot differential. Claude's failing run omitted the live 20% regular-season xG share and included the 2014 fallback. The two runs used different configurations, so neither result decides the question.
- **Status:** unresolved. Freeze one canonical production-equivalent baseline (inputs, season coverage, cached ratings), then change only the goalie term.
- **The archived g_* shadow keeps collecting** (TypeSafe 99%) as forward evidence only. It is not adopted, deployed or closed.
- Calling GPT's run "the valid PASS" above was wrong; that sentence is withdrawn.

### 5 November 2026 — research records merged
Retained main's complete rule history, including the original fail, adoption note and subsequent configuration correction. GPT's original rule text is preserved separately in NHL_GOALIE_ROSTER_GPT_RULE_20261105.md (LF endings normalized; exact original Git bytes remain at 5afbbb5). Its findings, aggregate results and strict helpers are now research records alongside this rule. No production implementation or displayed forecasts change in this research merge. The different configurations remain unresolved pending a canonical-baseline comparison, as the correction above states.


## Pointer (8 Nov 2026)
The replay baseline string in this rule is superseded by research/NHL_GOALIE_CANONICAL_RULE.md (it carries NHL_RS_SHOT_W=0.2 NHL_RS_XG=raw and the OT knobs). Nothing above edited.
