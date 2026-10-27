# NFL in-season futures: v4 against Polymarket, with a flat-$100 paper-bet record. Rule fixed before any results (26 Oct 2026, Sydney)

Asked by the user ("Do it", 26 Oct 2026). TypeSafe chose:
- scoring and paper bets as the next step (97%);
- checkpoints after weeks 4, 9 and 13 (98%);
- the ask plus taker fee as the bet price (74%);
- backing teams only (45%, against all sides 44%);
- division and make-playoffs only (66%).

This is a proxy profit test against an exchange price. It is not bookmaker profit: the user bets at Australian bookmakers, whose prices we don't collect.

## Model and markets
- **Model:** frozen v4, exactly as published. Live 2026 values come from the shiv-archive records; 2024-2025 come from the point-in-time v4 back-test (model/nfl_bt_teams.csv, model "v4 (live)").
- **Markets:**
  - NFL division winner: 8 divisions × 4 teams, one winner each;
  - make-playoffs: 32 teams, yes/no each.
- Conference and Super Bowl are not included.

## Checkpoints
After weeks 4, 9 and 13, the snapshot date is the day after the last regular-season game of that week (UTC):
- **2026 live:** the first shiv-archive record taken at or after 12:00 UTC on that date. The 2026 week-4 checkpoint predates the archive (it starts 10 Oct 2026), so it is recorded as missing, not reconstructed.
- **Backfill 2024-2025:** v4 back-test probabilities at that week. The Polymarket price is the last daily price at or before 23:59 UTC on that date, as in research/market_benchmark.py.

## Prices
- **Live:** the YES ask. Effective cost per $1 payout = ask + 0.03 × ask × (1 - ask), using the recorded fee schedule (taker rate 0.03, exponent 1). If the record's fee schedule differs, its own rate and exponent are used.
- **Backfill:** the daily price + 0.01 (spread allowance) + the same fee. Labelled approximate.
- Missing or zero prices: no bet and no score for that team and checkpoint.

## Paper bets
- Back a team (YES) when v4 probability / effective cost - 1 ≥ 0.10.
- Stake a flat $100. Profit if won = 100 / effective cost - 100; if lost, -100.
- Every qualifying team at every checkpoint is a separate bet, so the same team can be backed at more than one checkpoint.
- Results are settled from final outcomes. Unresolved 2026 bets are listed as pending.

## Scores
- **Accuracy by checkpoint and market:**
  - division: multi-class log loss of the winner, with the market normalised within each division;
  - make-playoffs: Brier score, using the raw yes price, as in the benchmark.
  - Model and market are scored on the same teams.
- **Paper-bet record by season, checkpoint and market:** number of bets, stakes, profit, return on stake, and the probability-weighted expected profit (model) for comparison.
- **Report every refresh:** research/nfl_futures_scorecard.json and research/nfl_futures_paper_bets.csv.

## Reading the result
- Bet counts are small: dozens per season. A season's profit or loss is mostly noise, and several seasons are needed before any conclusion.
- No threshold or rule is changed after seeing results; any change needs a new dated rule.
- No claim of an edge is made from the backfill: those seasons were used in earlier benchmark work.

## First run (26 Oct 2026, Sydney): backfill only; no 2026 checkpoint reached yet
- **2026:** the week-4 checkpoint (6 Oct) predates the archive (first record 10 Oct), so it is missing. Week 9 (about 10 Nov) and week 13 will be scored automatically by .github/workflows/nfl-futures-scorecard.yml (Tuesdays and Wednesdays, futures-scorecard branch).
- **Backfill 2024-2025 paper bets (approximate prices):** 72 bets, $7,200 staked, profit +$7,867 (+109%).
  - 2024: 29 bets, +$150 (+5%).
  - 2025: 43 bets, +$7,717.
- **Concentration:** most of the profit comes from four longshot division winners: CHI 2025 (cost 0.033), NE 2025 (0.042), CAR 2025 (0.051) and LA 2024 (0.067). Without those four the record is about -$600.
- **Model probability-weighted expectation:** +$4,494.
- **Accuracy:**
  - division log loss: model better than the market in 5 of 6 checkpoints;
  - make-playoffs Brier: model better in 3 of 4.
- **Reading:** encouraging but not evidence of an edge. These seasons were already used in benchmark work; the back-test is not the archived live forecast; prices are approximate; and the result rests on a handful of longshots in a high-surprise 2025.

## Amendment (26 Oct 2026, Sydney), written before running: retrospective 2026 week-4 checkpoint
- Asked by the user. v4 was first built and frozen on 9 Oct 2026 (git history), after week 4 (last game 5 Oct). So no live v4 forecast exists for the 2026 week-4 checkpoint.
- **Reconstruction:** pipeline/nfl_backtest.py's method, exactly as for the 2024-2025 backfill:
  - frozen v4 settings;
  - ratings rebuilt from 2026 play-by-play and results through week 4 only, with later results masked;
  - QB and pressure layers off;
  - 4,000 simulations.
  Rows go to research/nfl_futures_2026_w4_retrospective.csv.
- **Prices:** Polymarket daily price history (market-data branch) at the checkpoint date, plus the 1-cent spread allowance and fee, as in the backfill.
- **Kalshi:** not used. Our Kalshi archive covers only some NFL divisions and only from its later start, and Kalshi's historical API is not reachable from this environment.
- **Labelled retrospective:**
  - the code was written after the checkpoint;
  - v4's simulation settings were tuned on 2022-2025, not 2026;
  - the shrinking-uncertainty and recalibration work this week inspected 2013-2025 only.
  Scored and settled like the backfill, but reported separately from the live 2026 record.

### Result of the retrospective 2026 week-4 checkpoint (26 Oct 2026)
- Polymarket prices were found for all 64 team-market rows.
- **Paper bets:** 23 qualify (12 division, 11 make-playoffs), $2,300 staked. Model-expected profit: +$1,526. All pending until the season resolves.
- **Mark-to-market at 25 Oct daily prices** (descriptive only; daily price, not the bid you could sell at): +$469 on $2,300.
  - Biggest movers up: SF, WAS, NYG, PIT division; TB, NYG, PIT make-playoffs.
  - Biggest movers down: LV, MIA, NYJ division; LV, IND make-playoffs.

## Amendment (27 Oct 2026, Sydney), written before any v5 paper-bet results: a v5 record beside v4
- **Why:** the v5-core vs v4-core replay was inconclusive overall (research/NFL_V5_PROMOTION_RULE.md), but v5 was better in season in 10 of 13 seasons. The user bets in season.
  - TypeSafe: track v5 beside v4 and let the user use v5 as his 2026 in-season betting number, labelled as a judgement call on inconclusive evidence (78%; keep v4 22%).
  - TypeSafe also judged v5's 2025 loss mostly variance (87%): a sharper model is punished in a high-surprise season.
  - v4 stays the displayed model; nothing about the v4 record changes.
- **v5 rows**, same markets, checkpoints, price rule, threshold and stake as v4:
  - **2026 live:** v5 probabilities (challenger_v5) from the first forecast-archive season file generated at or after the checkpoint time (12:00 UTC on the day after the week's last game). Prices: the ask plus fee from the same shiv-archive record used for the v4 row of that team, market and checkpoint.
  - **2026 week 4, retrospective:** v5-core (v5like, walk-forward weights, 10,000 simulations), built as in research/nfl_v5_promotion_test.py. Prices: Polymarket daily price as for v4.
  - **Backfill 2024-2025:** v5-core rows from research/nfl_v5_promotion_rows.csv.gz (the two seed sets averaged) at weeks 4, 9 and 13. Prices: as in the v4 backfill.
    - The v4 backfill uses the v4 back-test file, a different construction from the v4-core rows, so the backfill comparison is between constructions, not just models. A v4-core backfill from the same rows is reported beside it for a like-for-like comparison.
- **Reported separately per model:** bets, profit, return and expected profit, and accuracy against the market. No combined record.

### First v5 run (27 Oct 2026)
- **Backfill 2024-25 like-for-like** (core rows, approximate prices):
  - v4-core: 71 bets, +$7,916; without its four largest wins, -$553.
  - v5-core: 66 bets, +$4,464; without its four largest wins, -$2,140.
- v5's sharper probabilities skipped the 2025 week-4 Chicago division bet (v5 3% against cost 3.3%), which won $2,937 for v4. Both records rest on a few 2025 longshots.
- **2026 week-4 retrospective:** v5-core 18 bets (v4 23), all pending.
- **Live v5** from week 9 on, automatically.

## Amendment (27 Oct 2026, Sydney), written before any Kalshi paper bet: Kalshi as a second price source, 2026 live only
- **Why:** asked by the user ("we'll just use Polymarket and Kalshi"). TypeSafe chose this as the next task (33%). Kalshi NFL prices have been kept daily since 27 Oct 2026 (private repo, collected_data/market_history/nfl), with top-of-book sizes.
- **Scope:** checkpoints after weeks 9 and 13 of 2026; division winner and make-playoffs; v4 and v5, reported separately from each other and from the Polymarket record. No backfill exists.
- **Price:** the first daily Kalshi record taken at or after 12:00 UTC on the checkpoint date.
- **Model:** the latest forecast-archive season file generated before that record's fetch time.
  - v4 is the file's teams table; v5 is challenger_v5.
  - Model age (fetch time minus file time) is reported.
- **Bet sizing:**
  - **Fills:** buy YES only, at the ask.
  - **Stake:** $100 is the maximum total outlay including the taker fee. That fee is 0.07 × multiplier × C × P × (1 - P), rounded up to the cent per order; the multiplier is 1 per the July 2026 schedule.
  - **Size:** C = the largest whole number of contracts within the budget and within the displayed ask size.
  - **Edge:** the bet qualifies when model / (total cost / C) - 1 ≥ 0.10.
  - **No bet** without a two-sided quote, with an ask ≤ 0 or ≥ 1, or with C = 0.
  - Whether the quote's spread is ≤ 0.05 is recorded.
- **Settlement:** profit = C × payout - total cost, with payout $1 per winning contract. Unresolved markets stay pending.
- **Team names:** Kalshi city names map to teams ("Los Angeles C/R", "New York G/J" by the letter). Unmatched names are excluded and listed.
- **Output:** private (research/nfl_kalshi_paper_bets.json in the private repo), refreshed by the daily private build. Nothing here feeds a model, and no threshold changes after results.
