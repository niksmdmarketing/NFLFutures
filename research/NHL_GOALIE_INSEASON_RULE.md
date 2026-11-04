# NHL futures: update goalie values during the season. Rule, version 1

Written 4 Nov 2026 (Sydney), before any replay of this variant was run. Amendments are added below with dates; nothing above them is edited.

## Why
- Goalie values (nhl_absence.values: goals saved above expected per 60, from the two previous seasons, shrunk at 30 hours) are **frozen at the start of the season**. They drive the starting-goalie part of the lineup/roster term and the injury layer.
- A goalie's form this season never reaches them. Example (4 Nov 2026): after the Hellebuyck trade, New Jersey's roster term moved +0.005 goals a game, because the frozen values rate Jake Allen (0.16) almost as highly as Hellebuyck (0.19).
- **Expected gain is small.** The team rating already counts this season's goals against, so a goalie's form is partly in it. Updated values matter only when a team's goalie mix changes (injury, trade, platoon). Earlier goalie ideas failed:
  - goalie player ratings before the season (correlation 0.01-0.08);
  - a playoff-goalie edge.
- TypeSafe picked this test (53%, low confidence 0.3); the owner asked for it.

## Variant (`NHL_G_UPD=30` in research/replay_nhl.py)
At each weekly checkpoint, every goalie's value becomes

  v = (H0 × v_start + h × r) / (H0 + h), with H0 = 30 hours,

where:
- v_start is the frozen start-of-season value;
- h is his hours in net this season before the checkpoint;
- r is his goals saved above expected per 60 this season before the checkpoint.

**Per game:**
- goals saved above expected = his team's MoneyPuck expected goals against (all situations) × his share of the team's goalie ice time − goals he allowed;
- data: research lineups (data/research/nhl_lineups/goalies_YYYY) and MoneyPuck team games (data/research/mp/team_games.csv.gz).

**Recomputed with the updated values:** this season's game lineup values (`nhl_lineup.game_values`), and so the roster term. Nothing else changes; skater values stay frozen.

**Not in the replay:** the injury layer (no historical injury lists), so a live version would also use the updated values there. That part is not tested.

## Baseline
The live settings as reproduced on 15 Oct 2026:

`NHL_SHOT_W=1 NHL_SHOT_PO=1 NHL_PO_FADE=3 NHL_LINEUP_C=1 NHL_LINEUP_N=5 NHL_LINEUP_PRE=0`

with player values from nhl_absence (points per 60 / goals saved per 60). The variant adds only `NHL_G_UPD=30`, so the comparison is like for like.

Two live parts are left out:
- **RAPM lineup values:** they need a long rebuild of the shift inputs, and their measured gain over these values was +0.0003.
- **The 20% regular-season xG share:** measured gain +0.0001.

Seasons are those the replay supports (2014-2018, 2021-2025), with 2,000 simulations.

## Scoring
- research/nhl_holdout.py (baseline directory first).
- Gain = baseline log loss − variant log loss, per market (playoff, division, best record, round 2, round 3, final, title) and combined (mean of the markets).
- 90% bootstrap over seasons.

## Decision
- **Pass:** the combined gain's 90% lower bound is above 0, and no market's mean gain is below −0.0005. A pass means building the live version, with updated values in both the roster term and the injury layer, first as a shadow next to live NHL futures.
- **Fail:** anything else. Goalie values stay frozen.
- No re-tuning of H0 under this version. H0 = 15 and 60 are run and reported as sensitivity only; they cannot rescue a fail.

## Result (4 Nov 2026, run after this rule was committed to the working tree; 2,000 sims, 10 seasons)
research/nhl_holdout.py, baseline first. Gain over baseline, 90% bootstrap over seasons:
- **H0 = 30 (primary):** combined +0.0002 (-0.0002 to +0.0006), better in 5/10 seasons. Best record -0.0003, the worst market.
- H0 = 15 (sensitivity): combined +0.0003 (-0.0000 to +0.0006), 5/10.
- H0 = 60 (sensitivity): combined +0.0001 (-0.0001 to +0.0004), 5/10.

**Decision under this rule: FAIL** (the lower bound is not above 0). Goalie values stay frozen. The sensitivities cannot rescue it.

## Amendments
(none)
