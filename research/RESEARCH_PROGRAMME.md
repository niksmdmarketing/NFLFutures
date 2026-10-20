# Research programme after the Sportsphere review (20 Oct 2026)

Agreed with the user and GPT. Site predictions are unchanged by anything here. Sportsphere's weights, thresholds and market-based game-script inputs are not copied. Its public results do not establish superiority. Its own NFL write-up reports an attractive fitted result that turned negative under walk-forward testing. Raw defence-versus-position averages confuse defence with pace and opponent quality. Market-based inputs would break our rule that models are independent of prices.

## Evidence labels (used on the site and in write-ups)
- **Historical improvement:** passed a rule written before results on walk-forward history.
- **Forward testing:** frozen, live forecasts being archived and scored on new games only.
- **Experimental:** built or partly tested; not established.
- **Descriptive:** a summary of data, with no predictive claim.

Every forecast and every filter version is archived with a timestamp. The selections actually made at the time are what get scored. A filter found by looking at historical results is evaluated only on data after it was found.

## Current status by model
| Model / market | Label |
|---|---|
| NFL v4 game and futures model (frozen for 2026) | Historical improvement; forward testing in 2026 |
| NFL v5 | Experimental (shadow only) |
| AFL model D | Historical improvement (AFL three-way rule); forward testing from 2027 |
| NBA team model with injury layer (games, futures) | Historical improvement; forward testing |
| NBA player-term shadow | Experimental (single-game pass; futures fail; archived shadow) |
| NBA minutes model (props stage one) | Historical improvement (research only, not on site) |
| NBA game environment, possession simulation (stage two) | Failed its rule; experimental |
| NBA player props | Not built; see 1 |
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
