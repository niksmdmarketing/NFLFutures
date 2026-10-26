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
