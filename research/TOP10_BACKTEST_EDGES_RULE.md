# Top-10 backtest edges: are they legitimate? Rule written 8 Nov 2026, before any edge was listed

Owner's aim: find the 10 largest backtest edges, diagnose why the model's win probability is so high, fix any bug or weakness, and repeat until the 10 largest edges are all legitimate. Paper only; prices are never model inputs.

## Population and edge
- Data: NFL regular-season games 2014-2025 (play-by-play for the two prior seasons is held from 2012), point-in-time pre-game home-win probability from the frozen v4 engine as in research/nfl_match_market.py (ratings from earlier weeks only), against the de-margined closing moneyline from the nflverse lines (spread converted when no moneyline). Weeks 2 and later.
- Edge = p_model(side) - p_market(side) for the side the model prefers, any game, either side. Top 10 by edge, ties broken by game id. Listed once, after this rule.
- Scope limit: this is one sport at game level, the only place both a point-in-time model probability and a real closing price are held locally for a dozen seasons. NBA, NHL, AFL and NBL game-level files need the Sportsbook Reviews / AusSportsBetting archives, which are not in this workspace. Futures backtests have no historical market price. Stated now so the result is not read as covering them.

## What "legitimate" means
An edge is LEGITIMATE only if all four hold:
1. Inputs: every input to the model probability was available before kick-off (checked per input: rating week cut-off, starter source, schedule, rest).
2. Reproduction: the probability can be rebuilt by hand from the stated inputs and matches to 0.1pp.
3. Mechanism: a named model feature, working as designed, explains the gap to the market (for example a quarterback change the market had not priced), and the feature is not an artefact (wrong team, wrong player, stale or missing data, a unit error).
4. Cohort check: among the top 1% of edges by size (not just the ten), the model's side has not done worse than the market's price implies: model log loss no worse than market log loss on that cohort by more than its season-clustered 90% interval. If worse, the mechanism is a MODEL WEAKNESS even when 1-3 hold.
Otherwise the edge is a BUG (fails 1, 2, or the artefact part of 3) or a WEAKNESS (fails 4 only).
Outcomes of the ten games are not used to judge legitimacy: ten results say nothing.

## Fixes
- A BUG is fixed in the engine (or the test harness, if the bug is there), the whole population is rebuilt, and the top 10 is relisted.
- A WEAKNESS is fixed only by a change that is validated on seasons not used to choose it (fit on 2014-2019, score 2020-2025, and the reverse), improves cohort and overall log loss, and passes the Amendment 1 no-harm style check on games it should not move. A weakness with no validated fix is documented, not patched.
- Each round is dated. Nothing earlier is edited.

## Stopping
Stop when a full relist of the top 10 finds no BUG and every WEAKNESS is either fixed and validated or documented with its cohort evidence. Maximum 5 rounds; if the cap is reached the unresolved edges are listed as open, not called legitimate.

## Review
DeepSeek reviews this rule before the first listing and each round's diagnoses after. Claude re-computes every number DeepSeek quotes. The legitimacy call for each edge is the four checks above; no reviewer or tool overrides them.

## Amendment 1 (8 Nov 2026, after DeepSeek's review, before any edge was listed; replaces check 4 and the held-out path above)
DeepSeek could not see the file (its checkout read the wrong branch; fixed) and reviewed the summary. Points accepted: the top-tail cohort check as written fires for any noisy model, because selecting the largest model-above-market gaps picks rows where the model's own error is positive; the 1% cohort (about 29 games) is too small to say anything; the held-out seasons were not independent of the selection; the question presumed its answer; "edge" and the de-vig method were not stated.
1. Edge is a probability difference, not a return: p_model(side) - p_market(side), no bookmaker margin. The market probability is the home moneyline pair de-margined proportionally (match_vs_market.devig), or the spread through the same normal curve the earlier test used when no moneyline exists. Games missing the model probability or a close are dropped and counted. A game with equal probabilities has no edge and is skipped.
2. Check 4 becomes the mirrored-tail test. Cohort A: the top 5% of games by model-above-market gap (about 145). Cohort B: the top 5% by market-above-model gap (the mirror). For each, the model-minus-market log loss per game. Legitimacy asks whether A is worse than B: the difference D = LL_A - LL_B, season-clustered 90% interval. A model that is merely noisier than the market is worse in both tails and gives D near 0; a model that is overconfident specifically where it disagrees upward gives D above 0. Reported with the cohort sd, the within-season correlation, the all-games model-minus-market gap, and the model-probability distribution of the top ten against all games. Top 1% is reported alongside; the 5% pair is primary. Decision: D interval above 0 = WEAKNESS (upward disagreement is overconfident); containing 0 = no evidence of one, said as 'not shown', and if the half-width exceeds 0.20 it is INSUFFICIENT, never 'legitimate'.
3. Selection and fixing are split by season before anything is listed: discovery 2014-2019 (the top ten and any fix are chosen here), evaluation 2020-2025 (fixes are scored here once; 2020, a 16-game season without a preseason, is reported with and without). Inputs in checks 1-3 are verified on all seasons.
4. Bug fixes and weakness fixes are separate paths, as in FOUR_AGENT_PLAN.md: a bug fix goes through the correctness path (dated, no-harm measured on games it should not change); a weakness fix needs the evaluation-season gain.
5. Look budget: at most 5 rounds, one look per round per item, each recorded; the count of rounds goes in the family count. A round that changes the engine restarts the listing; an item judged once is not re-judged on the same seasons.
6. Alternative hypotheses stated before listing, each with what separates it: (a) model too high (an input error or an overconfident feature): separated by checks 1-3 and the mirrored tail; (b) market error: the model is right and the close is off, separated only by the outcome-cohort test, so not claimed from ten games; (c) stale close or mismatched definition (line moved after the recorded close, wrong team code, neutral-site flag, ties): separated by comparing the stored close with the spread and moneyline and by checking the outcome definition; (d) the starter used is known in hindsight: separated by the starter-source check in check 1.
