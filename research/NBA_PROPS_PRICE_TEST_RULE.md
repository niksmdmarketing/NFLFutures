# NBA player props against market prices. Rule, version 1
Written 6 Nov 2026 (Melbourne), before any price data has been downloaded or looked at. Changes are dated amendments below; nothing above them is edited. A flawed run is recorded, not hidden. Prices are never a model input.

## Question
Do the frozen NBA props forecasts carry information the market price does not, and do bets selected by them beat the closing price? This is the first test of the props models against prices. Passing qualifies a stat for a forward paper test only; no money is staked on this result.

## Why now
- TypeSafe (6 Nov 2026): writing this rule before any price data arrives is the first overnight task (91%).
- The props models have only been tested for accuracy (2022-2026), never against prices. Player props are softer and more numerous than futures, which is why they are tested first.

## Model (frozen; nothing refitted for this test)
- Forward-test identifier "b" (research/NBA_MINUTES_M2B_RULE.md): minutes M2; rebounds and assists v2; points with the passed dispersion form (research/NBA_POINTS_DISPERSION_RULE.md). **v2-b is primary**; v3-b (M2b minutes) is reported only.
- Information time: **60 minutes before tip-off** (primary), using the official injury report available then. 6 hours is reported only.
- Window 1, **1 Jan 2026 to the end of the 2025-26 regular season**: forecasts produced from the frozen 2026 parameter file (model/nba_props_live_params_2026b.json) with the same functions as the live forecaster (research/nba_props_live_core.py), from point-in-time inputs. These seasons were used to develop the model's structure (accuracy only), so window 1 is development evidence.
- Window 2, **2026-27 regular season to the backfill date**: the archived live forecasts (forecast-archive branch, nba/props_forward/), corrected identifier only, from its activation time. Fully forward.
- Playoffs and play-in are excluded.

## Prices
- OddsPapi historical odds (collected_data/oddspapi_nba/ in the private repository), books DraftKings, FanDuel and Pinnacle; player points, rebounds and assists over/under. Alternate and milestone markets excluded.
- **Entry price:** the last price at or before 60 minutes before tip-off (the model's information time). **Close:** the last price before tip-off.
- **Main line:** for a player, stat and book at entry time, the line whose over and under prices are closest to even. Only half-point lines (no pushes). Both sides must be quoted at the same line.
- **Market fair probability:** each book's two prices de-vigged multiplicatively (each implied probability divided by their sum). The consensus is the mean over books quoting the same line. Pinnacle alone is reported.

## Outcomes
- ESPN box scores. A player who does not play is void and excluded (books void such bets). The model's probability of the over is conditional on appearing.
- Name matching: bookmaker player names to ESPN athlete ids by normalised name within the two teams of the game. If under 95% of priced player-games match, the matcher is fixed (mechanics only, without looking at outcomes) before scoring. Unmatched counts are reported.

## Tests
1. **Information test (all priced lines, not only bets), per stat:** logistic regression of the outcome (over) on logit(consensus fair probability at entry) and logit(model probability). The coefficient on the model term with a 90% interval from resampling game dates (2,000 draws, seed 1). Also log loss of market, model and the fitted blend (blend fitted on window 1, applied to window 2).
2. **Bets:** for each player-game and stat, at most one side: the side with the higher edge, edge = model probability x best entry price across the three books - 1. **Primary threshold 5%**; 3% and 10% reported.
3. **Closing-line value of those bets:** consensus fair probability at close of the bet side x entry price - 1. Mean with a 90% interval from resampling game dates.
4. **Profit:** flat 1 unit at the entry price, reported, not gated (too noisy over this sample).

## Gates, per stat (all must hold for that stat)
- **G1:** model coefficient in test 1 has a 90% lower bound above 0 (window 1 and 2 pooled), and is positive in each window separately.
- **G2:** mean closing-line value of primary-threshold bets has a 90% lower bound above 0, with at least 200 bets.
- **G3:** G2's mean is positive in each window with at least 50 bets; a window with fewer is reported as insufficient and does not fail the stat.

## Decision
- A stat that passes moves to a forward paper test: daily collection of current prices within the plan's quota, the same selection, its own adoption rule written before the first forward score. No real money before that forward test passes.
- A stat that fails is recorded. The model is not adjusted to chase prices; a new idea needs its own rule.
- TypeSafe helps interpret; it does not override the gates.

## Reported, not gated
v3-b; 6-hour horizon; Pinnacle-only fair prices; by month; by over and under; by line size; low-minute-risk group (as in the M2b rule); players whose team had a role-changing absence announced on the day; hit rate; edge calibration (realised against claimed edge, by edge band).

## Limits stated now
- Prices from three US books, not the Australian books the owner bets at.
- OddsPapi history starts in January 2026, so the sample is one half-season plus the current season so far.
- Window 1 overlaps the seasons used to build the model (accuracy only; never prices).
- Known model weaknesses stay on the label: confident points overs about 4 points too high; scoreless fringe nights under-predicted.
- The 60-minute price may be missing for some lines (books post late or pull lines); coverage is reported in the mechanics check before scoring.

## Mechanics check before scoring (no outcomes or profits looked at)
Price coverage at entry by book and stat; share of half-point main lines; match rate; that no price after the entry time is used for entry; that forecasts are dated before their entry price time; and that window 1 forecasts reproduce the frozen functions on a sample (as research/nba_props_live_core.py verify).
