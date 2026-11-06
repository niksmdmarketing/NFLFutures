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

## Amendment 1 (6 Nov 2026, implementation notes before any price data; nothing above edited)
1. **Window-1 forecasts** come from the forward forecaster's own offline replay mode (research/nba_props_window1.py: NBA_PROPS_SEASON=2026, parameters 2026b, official reports archived on the market-data branch, box scores of games finished at least 3 hours earlier). The replay forecasts exactly at the cutoff (60 minutes before tip-off); live forecasts are made 0-45 minutes before the cutoff, so window 1 can see up to 45 minutes more injury news than a live forecast. This favours the model slightly in window 1 and is a stated limit.
2. **Points in window 1** use the season's own walk-forward dispersion fit from the research (research/nba_points_dispersion_results.json, fits 2026: fitted on seasons before 2026), written to model/nba_points_d_params_2026.json, the same form as the live 2027 file. No new fitting.
3. **Window 2 coverage:** the forward archive holds 60-minute forecasts for 121 games up to 5 Nov 2026 (gaps on some days). Only archived games are scored; games without a forecast are not imputed.
4. **Main line ties:** when books split evenly between two lines, Pinnacle's main line is used if it is among them, otherwise the lower line.
5. **Code:** research/nba_props_price_test.py (pieces, self-test on synthetic data passes), research/nba_props_names.py (matching; self-test 99.8% on synthetic name variants of 2025-26 ESPN names), research/nba_props_price_run.py (assembly, mechanics, score). An end-to-end run on fabricated prices (not real data) completed: 60 of 60 fixtures mapped, all names matched.

## Amendment 2 (6 Nov 2026, from GPT's review, before any price data was downloaded or looked at; nothing above edited)
TypeSafe (6 Nov): record all nine of GPT's proposals now, before prices (87%). Where this differs from the text above, this governs.
1. **Same line throughout.** Entry, close and CLV use one numeric line. OddsPapi discovery must show either that each market id fixes its line or that every price update carries its own line; the discovery file reports this (`sample.line_structure`). If lines change inside a stored series, the collector is changed to keep a separate series per line before any backfill is scored, and rows that merged lines are not scored.
2. **Common main line before consensus or best price.** Each book's main line is its half-point pair closest to even (ties: lower line); the common line is the one most books nominate (ties: Pinnacle's, then the lower). Only pairs on that line are combined; each book is de-vigged on its own pair and the fair probabilities averaged.
3. **CLV on the entry line.** The close is the same book set's same-line pairs. If any entry book lacks a valid same-line close, that bet has no CLV (counted and reported; it stays in profit). A close on another line is never used.
4. **Timing.** The forecast must be generated at or before the cutoff (replays: their run time; live: when the forecast finished). The entry quote is the last update at or before the cutoff; an unchanged quote may predate the forecast. An entry quote last changed more than 24 hours before the cutoff is excluded; a close last changed more than 60 minutes before tip-off is treated as missing. The close is strictly before tip-off.
5. **Gates are pass, fail or insufficient.** G2 needs at least 200 bets with CLV **and at least 20 distinct bet dates**. G3 needs at least 50 bets in **each** window; a window with fewer makes G3 insufficient, and an insufficient gate blocks a pass (it is not evidence against the model). A stat passes only if G1, G2 and G3 all pass.
6. **Regression.** Unpenalised maximum-likelihood logistic regression with an intercept and the two logits (clipped to 1e-4..1-1e-4) standardised on the fitting sample. Full rank, each predictor's spread above 1e-8 and condition number below 1e8 are required; rank failure, separation or non-convergence is a failed fit. The whole fit is redone in every date-cluster draw (dates in US Eastern time, all rows of a date together); failed draws are reported and more than 5% failed draws makes G1 insufficient. A model equal to the market cannot pass (tested). The coefficient is on the standardised scale; only its sign and interval matter for G1. The blend is fitted on window 1 and scored unchanged on window 2.
7. **One observation per player, game, stat and common line** for G1 (bets and non-bets); at most one bet per player, game and stat (the side with the larger edge at the best entry price; ties go to the over). Primary rows need **two books** on the common line; one-book lines are counted and reported, not gated.
8. **Voids.** DraftKings, FanDuel and Pinnacle settle player props as void (no action) when the player does not play; their published house rules are checked and quoted in the mechanics report before scoring. A player with no ESPN minutes is void, never an under. Overtime counts (full-game stats, as ESPN reports).
9. **Narrow conclusion.** Positive CLV is about prices relative to the reference close, not proof of settled profit; profit is reported, not gated. All three stats are reported, including failures; the three stats are separate hypotheses. A pass qualifies a stat for a forward paper test only.

Code: research/nba_props_price_test.py (self-test now also checks a market copy is insufficient, stale-quote and late-quote exclusion, and incomplete closes); research/nba_props_price_run.py (gates as above; mechanics adds two-book and complete-close shares).

## Amendment 3 (6 Nov 2026, from GPT's independent code review, before any price row or result was read; nothing above edited)
GPT reviewed commit f9bb002 (research/NBA_AMENDMENT_2_REVIEW_2026-11-06.md). TypeSafe (6 Nov): accept all seven findings (93%). Code changes are GPT's patch as proposed, plus two extra self-test cases.
1. **Both sides inside the window.** An entry pair counts only if both sides were last changed at or before the cutoff, and the older side within 24 hours of it; a close pair only if both sides were last changed strictly before tip-off, and the older side within 60 minutes of it.
2. **Forecast timing evidence is required.** Replays use run_utc, live forecasts forecast_finished_utc, both with a time zone; a record without one stops the run. (Checked before applying: all 364 live records and all replay records have them.)
3. **The 95% name-match requirement is enforced.** Rate = matched priced player-games / all priced player-games (fixture, name). Below 95%, scoring stops and the matcher is fixed first (mechanics, no outcomes).
4. **One row per ESPN player, game and stat.** If two bookmaker name strings resolve to the same player in a game, scoring stops until the aliases are reconciled; nothing is dropped after seeing prices.
5. **A played player with a missing stat stops the run**; it is never settled as an under.
6. **Bootstrap clusters are game dates**: the scheduled tip-off's date in US Eastern time (not the cutoff's).
7. **G1 has no row minimum per window**; its fit checks (rank, spread, condition, convergence, failed draws) decide whether it is assessable. G2 and G3 counts are unchanged.
8. **Settlement (Amendment 2 item 8) is not fully verified** (research/BOOKMAKER_SETTLEMENT_REVIEW_2026-11-06.md). Supported: all three books void a player who does not take the court, a brief appearance gives action, and full-game totals include overtime. Open: the jurisdiction and historical versions of each book's rules for the feed; DraftKings' early-exit rule (an eligible pre-halftime over on a player injured out of the second half can be voided while the under stands); missing or zero ESPN minutes do not by themselves prove a non-appearance. Scoring waits for a dated amendment that settles these from sources, without looking at outcomes or profits.

## Amendment 4 (6 Nov 2026, wording correction from GPT's settlement review, before any price row or result was read; nothing above edited)
Amendment 3 item 8 is narrowed: a brief appearance gives action **except under DraftKings' early-exit rule** (an eligible pre-halftime over on a player who misses the whole second half through injury or illness can be voided while the under stands); that exception is unresolved. A player with missing or zero ESPN minutes is **unknown participation**, not void and not an under, unless non-participation is confirmed by a source other than the minutes column; unknowns are excluded from scoring and counted. Scoring stays blocked until settlement is resolved by a dated amendment.

## Amendment 5 (6 Nov 2026, owner decision, before any price row or result was read; nothing above edited)
Settlement edge cases are **not researched further and not adjusted for** (owner, 6 Nov; TypeSafe split 52% simple exclusion / 47% ignore). Every player with ESPN minutes above zero is settled on his full-game stat, including early injury exits (DraftKings' early-exit refunds and similar are not modelled). Missing or zero minutes stay unknown and excluded, as Amendment 4 says. Closing-line value (G2, G3) does not depend on settlement; the information test (G1) and the reported profit carry small noise from the few refunded bets, stated as a limit. This lifts the settlement block on scoring; the 95% name-match requirement still applies.

## Amendment 6 (6 Nov 2026, challenger "c" registered before any price row or result was read, and before c is built; nothing above edited)
Owner decision (6 Nov), TypeSafe 100%: build an improved challenger on data from before the price window and score it alongside the frozen model. The frozen model (params "b") stays the **primary** hypothesis; nothing about its scoring changes.
1. **What c is.** The frozen model's appearing-conditional distributions (points pts_d_v2, rebounds reb_v2, assists ast_v2) passed through a monotone recalibration of their cumulative probabilities: for stat s and expected-minutes band m (the forecast's own expected minutes given appearing: up to 15, 15 to 25, over 25), calibrated P(X <= k) = g_sm(P_b(X <= k)), with g_sm fitted by isotonic regression of the indicator (actual <= k) on P_b(X <= k) over every k from 0 to the 99.9th percentile of the forecast. This targets the known flaws (confident overs too high, too few scoreless nights, slight points bias) without new inputs. Appearance probabilities are unchanged. No teammate-redistribution change is in c.
2. **Development data.** Replays of the frozen forecaster (same mode as window 1) at 60 minutes before every 2025-26 regular-season tip-off from 21 Oct 2025 to before **12 Jan 2026 00:00 UTC** (the earliest priced game tips 13 Jan), players with ESPN minutes above zero. No price is used. The checks below and the fit use only these games.
3. **Holdout check before freezing.** Fit on games before 15 Dec 2025, check on 15 Dec to 11 Jan: for each stat, c is kept only if its mean log score of the actual value is better than the frozen model's on the holdout; otherwise c equals the frozen model for that stat (identity map). Then the kept maps are refitted on all development games and frozen to model/nba_props_challenger_c.json with its SHA-256 recorded here in a later dated note, before any price row is read.
4. **Scoring.** c is scored on exactly the same priced rows, cutoffs and gates as the frozen model (windows 1 and 2, the same common lines and books). It is a separate, secondary hypothesis: a c pass qualifies c (not b) for a forward paper test, and both results are reported whatever they show. Window-1 and window-2 forecasts of c are the frozen records with the maps applied; no new replay is needed for the priced games.

## Amendment 7 (6 Nov 2026, bug fix found while wiring in challenger c, before any price row or result was read; nothing above edited)
The archived distributions are **unconditional**: the live forecaster stores p_appear x (distribution given appearing) plus 1 - p_appear at zero. The scoring code took the over probability from that stored pmf, which understates it for any player not certain to play, although only players who played are scored (books void the rest). Fixed: the model's over probability is now taken from the appearing-conditional pmf, (stored pmf minus 1 - p_appear at zero) / p_appear, for v2, v3 and c alike (research/nba_props_price_run.py; helper research/nba_props_challenger_c.py `conditional`). The text above that calls the stored fields "distributions given appearing" was wrong about the storage, not about what is scored. Challenger c is scored by the same gates through a shared function, on the same rows.

## Amendment 8 (6 Nov 2026, name fallback registered before any price row or result was read and before the fallback data is collected; nothing above edited)
TypeSafe (6 Nov): pre-register a fallback name match through SportsGameOdds (86%; lowering the bar 10%, deciding later 4%); owner approved.
1. **Why.** OddsPapi history identifies players only by id; names come from live odds, which never see players who have since left the league or the rotation. The 95% match bar could otherwise block the test.
2. **Data.** SportsGameOdds finalized NBA regular-season events with tip-off from 12 Jan to 13 Apr 2026, keeping **identity fields only**: event id, tip time, teams, player id and name, stat (points, rebounds, assists, full game), bookmaker, and that bookmaker's line (closing line, else last line). No price is stored.
3. **Rule.** Used only for an OddsPapi id the live-odds map did not name. Games are paired by tip time (within 15 minutes) and both teams. In a paired game, an SGO player is a candidate for the id when, for the same bookmaker (DraftKings or FanDuel) and stat, the SGO line equals a line OddsPapi quoted for that id with a closing price. The id's match in that game is the candidate with the most agreeing bookmaker-stat pairs, if it has at least two and no other candidate ties it. Across games the id takes the SGO player matched in at least 80% of its matched games, with at least two matched games; otherwise it stays unnamed. Matched names then go through the normal name matcher (research/nba_props_names.py). Fallback matches are counted and reported separately, and the 95% bar counts them.
4. **Use of lines.** Lines are used only to establish who a player is; results and prices are not read by this step.
