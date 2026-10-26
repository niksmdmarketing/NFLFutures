# NFL in-season futures: v4 against a market-implied ("synthetic market") forecast, 2013-2025. DRAFT rule for review before any code or results (26 Oct 2026, Sydney)

Status: **draft, sent to GPT for review.** Nothing has been run. Research only; no betting or model change follows automatically.

## Why
- Real futures prices (Polymarket) exist only from the 2024 season. In the 2024-2025 paper-bet backfill (research/NFL_FUTURES_PAPER_BET_RULE.md), four longshot wins carry the profit.
- To test over more seasons, this builds a market-based forecast from free closing game spreads and asks whether v4 adds information beyond the game-line market for division winner and make-playoffs.
- TypeSafe preferred this (43%) to waiting for live 2026 (40%) and chose the settings below.

## Synthetic market
At checkpoint w (after all week-w results) in season Y:
- **Spreads:** nflverse closing spread_line (positive = home favoured), regular season only (TypeSafe 96%).
  - Season Y, weeks 1..w: weight 1.
  - Season Y-1, all weeks: weight 1/3 (TypeSafe 60%).
  - No recency decay within a season (TypeSafe 64%).
  - No lines for games after week w are used.
- **Ratings:** weighted least squares, spread = r_home - r_away + h · (not neutral site), with ridge penalty 1 × Σ r² (one game-equivalent) on the team ratings and h unpenalised. Ratings are centred to mean 0 and taken in points, with no extra scaling.
- **Simulation:** the frozen v4 simulator (pipeline/simulate.py) with the market ratings.
  - Same settings as the v4 arm: tau 5.0, sigma 11.37, home edge 1.8, neutral sites no edge, correct playoff format (6 seeds to 2019, 7 from 2020), sweep option off.
  - 10,000 simulations, the same seed for both arms at each season and checkpoint. Only the ratings differ.

## v4 arm
- v4 with walk-forward rating weights, built exactly as the v4wf arm of research/nfl_futures_diagnosis.py (ratings from play-by-play and results through week w, scale 0.89). No QB or pressure layers.
- Checkpoints after weeks 4, 9 and 13 (the paper-bet checkpoints). Seasons 2013-2025.

## Scores
- **Cells:** division (multi-class log loss of the winner) and make-playoffs (Brier), at weeks 4, 9 and 13: six cells.
- **Per season:** the six cells' differences averaged equally. Gain = synthetic-market loss - v4 loss (positive = v4 better). Seasons averaged equally.
- **Bootstrap:** whole seasons, 10,000 draws, seed 20261026; one-sided 90% lower bound.
- **Paper bets against the synthetic market**, same rule as the Polymarket backfill:
  - back a team when v4 / (q + 0.01 + 0.03 · (q + 0.01) · (1 - q - 0.01)) - 1 ≥ 0.10, flat $100, where q is the synthetic market probability;
  - report profit, return on stake, wins and expected profit by season and in total;
  - report the season-bootstrap 90% interval of total return, and the result without the four largest wins.
- **Proxy validation, 2024-2025:** at the same checkpoints, compare synthetic-market probabilities with Polymarket daily prices (mean absolute difference and correlation), and score both on outcomes.

## Reading (fixed now)
- **v4 better:** primary gain with 90% lower bound > 0 and better in at least 8 of 13 seasons. Evidence that v4 carries information beyond the game-line market for these futures. It supports continuing the live 2026 Polymarket test; it is not proof of profit.
- **Not better:** v4 does not beat a market built from game lines. Real futures markets are slower and higher-margin than game lines, so this does not rule out an edge against them. But it would suggest the 2024-2025 Polymarket profit is more likely luck or Polymarket-specific, and that any edge must come from futures prices lagging the game-line market, not from better ratings.
- No change to v4, the betting rule or the threshold follows from either outcome without a separate decision.

## Disclosed exposure
- v4's simulation settings were tuned on 2022-2025.
- The 2013-2025 v4 replay was inspected this week (calibration work).
- The 2024-2025 Polymarket results are known.

## Questions for review
1. Is the market-rating fit (previous season at one-third weight, no decay, ridge 1) reasonable, or should the fit be validated (e.g. its own game-margin accuracy) before use?
2. Using the same tau and sigma for both arms isolates the ratings, but the market ratings may need a different uncertainty. Is a single shared simulator right?
3. Is home edge 1.8 for both arms right, or should the market arm use its fitted h?
4. Is the 8-of-13 plus lower-bound reading appropriate?
5. Should a 50/50 blend (v4 and market) be scored as a diagnostic of added information?
