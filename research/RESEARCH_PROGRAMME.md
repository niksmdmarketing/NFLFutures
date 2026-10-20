# Research programme after the Sportsphere review (20 Oct 2026)

Agreed with the user and GPT. Site predictions are unchanged by anything here. Sportsphere's weights, thresholds and market-based game-script inputs are not copied. Its public results do not establish superiority. Its own NFL write-up reports an attractive fitted result that turned negative under walk-forward testing. Raw defence-versus-position averages confuse defence with pace and opponent quality. Market-based inputs would break our rule that models are independent of prices.

## Evidence labels (used on the site and in write-ups)
- **Historical improvement:** passed a rule written before results on walk-forward history.
- **Forward testing:** frozen, live forecasts being archived and scored on new games only.
- **Experimental:** built or partly tested; not established.
- **Descriptive:** a summary of data, with no predictive claim.

Calculation checks use fitting data or mathematical identities; forecast-performance checks use held-out or future games. Every forecast and every filter version is archived with a timestamp. The selections actually made at the time are what get scored. A filter found by looking at historical results is evaluated only on data after it was found.

## Current status by model (each "historical improvement" names its baseline and market)
| Model / market | Label |
|---|---|
| NFL v4 game and futures model (frozen for 2026) | Historical improvement over earlier NFL versions on walk-forward game and futures scores; forward testing in 2026 |
| NFL v5 | Experimental (shadow only) |
| AFL model D, games | Historical improvement over the stat-only and player-only versions (AFL three-way rule, game margins); forward testing from 2027 |
| NBA injury (availability) layer, single games | Historical improvement over the team rating without it (game log loss) |
| NBA futures (team rating, pre-season player mix, roster step, playoff rotation) | Historical improvement over earlier futures versions in the replay; the injury layer is not part of that evidence |
| NBA player-term shadow | Experimental (single games passed against the team rating plus injury layer; futures failed); archived shadow |
| NBA minutes model (props stage one) | Historical improvement over the report-aware last-10 baseline (minutes RPS); research only |
| NBA game environment, possession simulation (stage two) | Failed against the live model; experimental |
| NBA player props: rebounds (P+O), assists (P+T), version 2 with M2 minutes | Historical improvement overall over season, last-10, per-minute and minutes-matched baselines (RPS), with a known subgroup weakness (overs too high for players at risk of short minutes); frozen forward test 2026-27; not on site |
| NBA player props: points | Beats every baseline but fails calibration (also with M2 minutes); experimental |
| NBA minutes M2 (short-night component) | Historical improvement over stage one (minutes RPS and calibration); used by prop version 2 |
| NBA minutes M2b (truncation fix) and prop v3 | Promising correction; failed the original adoption gate; 2022-2026 results are development evidence; pre-specified forward test 2026-27 beside v2 (one evaluation at season end) |
| Kalshi NBA price archive | Descriptive (benchmark only, never an input) |

## 1. Simple NBA prop challenger (highest priority; now)
Rule: research/NBA_PROPS_SIMPLE_RULE.md.
- Projected minutes from the frozen stage one, multiplied by shrunk per-minute production.
- Points, rebounds and assists, each with a full distribution that includes the uncertainty in availability and minutes.
- Two modest adjustments, each tested separately:
  - role/teammate absences;
  - opponent, per possession and pace-adjusted.
- Compared with simple baselines on identical player-games and forecast times.
- Combos are excluded until their dependence is modelled.

There is no player-level possession simulation to compare with: stage two failed before a player layer was built. If this challenger passes, any later simulator must beat it on the same games before its complexity is accepted.

## 2. Market archive extension (next; the user's PC collector already runs every 30 minutes)
- Save each frozen forecast next to the Kalshi quote at the forecast time, and the last usable pre-game quote.
- Report:
  - the size and direction of later market movement;
  - quote availability;
  - spreads, liquidity and fees.
- Settlement rules are matched per contract, including void versus settled for players who do not play.
- Market movement is supporting evidence only. It is not proof of accurate probabilities or of profitability.
- Execution comparisons (after GPT's review of AND-1, 20 Oct 2026):
  - **Kalshi at the forecast time:** at the quote actually available (ask for buying), with Kalshi's fees and the bid-ask spread.
  - **Kalshi with friction:** the same with a delayed entry (next 30-minute snapshot) and with one cent worse, to see whether an apparent edge survives ordinary execution.
  - **Single Australian bookmaker and best accessible Australian price:** not possible without paid historical odds. Recorded as a gap; added only if a free, timestamped source appears.
- Closing-price movement is measured on the same contract, threshold and settlement terms:
  - entry quote against the same market's last usable pre-game quote (mid and ask);
  - never best entry against an average close, which would reward price shopping.
- **Ledgers:**
  - The forecast ledger keeps every forecast with: model version, forecast timestamp, player, game, stat, threshold, predicted probability, quote and its timestamp, settlement rule, and final result including voids and pushes.
  - The primary performance ledger keeps one selection per player per game (the 1-hour forecast).
  - Repeated forecasts (6 hours, 1 hour, later snapshots) are kept separately for timing analysis.
  - The forecast ledger and any selected subset are reported separately.

## 3. Role features (after 1)
- **NBA:** ball-handler / scorer / rebounder role, starter or bench, and teammate absences.
  - Each must add to minutes and recent production, under its own rule.
  - The same role change must not be counted twice. Teammate absences already enter through stage one's vacated minutes and through challenger adjustment 1.
- **Later, only if dated historical data exists:**
  - AFL: centre-bounce share, time on ground, role changes, tagging.
  - NFL props: routes, target share, carries, red-zone opportunities.

## 4. Evidence reporting (ongoing)
- Labels as above.
- Version archive for forecasts and filters.
- No retrospective selection.
