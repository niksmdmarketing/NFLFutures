# NFL props against prices — frozen rule, version 1

Written 6 November 2026, Australia/Sydney, before any NFL OddsPapi data is downloaded, opened or scored by this work. Append dated amendments; preserve this text. Prices are reference data only and never forecast inputs. No paid requests or collector changes.

## Choice fixed before prices

Use **nfl-player-props-v1.1-experimental**, with the existing `model/nfl_player_props_v1.json`, `pipeline/nfl_props.py` and `pipeline/nfl_props_v11.py` at public revision `370ceb4`. It is the displayed version and avoids adding v1.2's matchup layer to a price test. No parameter, availability rule, allocation rule or distribution is refitted. Record full code and parameter SHA256 hashes in the export manifest before generating rows. Do not choose between v1.1 and v1.2 using prices or results.

Supported stats: QB **pass attempts** and WR/TE/RB/FB **receptions**, conditional on appearing. No passing yards, receiving yards, rushing props, touchdowns or combined markets. The frozen implementation and receipt scorer support regular-season games only. January 2026 playoffs are explicitly outside scope; extending postseason support requires a different rule. January 2026 regular-season games belong to NFL season 2025, part of this model's training period, and are not substituted as a holdout.

## Coverage and provenance

Audit every NFL season-2026 regular-season game kicked off by the export's fixed `as_of_utc`, with separate 60-minute (primary) and 360-minute (sensitivity) rows. Both horizons use kickoff minus the horizon, not the time a historical price last changed.

1. **Receipt-proved cohort (primary):** select the exact snapshot using the existing receipt scorer: latest independently server-received immutable snapshot before the horizon cutoff, generated no later than the receipt; verify archive branch, ancestry and content hash. Keep generation, receipt and cutoff times and age at cutoff. No commit-time substitute, interpolation, or new retrospective forecast-age exclusion. Export the original PMF unchanged.
2. **Reconstruction cohort (supplementary):** for games without such an archive, run the frozen functions using only depth snapshots dated no later than cutoff and earlier regular-season statistics/snaps from games whose scheduled kickoff plus six hours is strictly before cutoff. Apply the same team-volume timing. Never use target-game appearances, actual starters, future roster memberships or current injury designations. Record revised source vintages and missing historical availability. These rows are lagged reconstructions, not independently proved as-known-then forecasts and cannot replace missing primary evidence.

Export one row per horizon/player/game/stat, containing the full line-agnostic conditional PMF, separate appearance probability, GSIS id, ESPN id when known, name, team, opponent, scheduled kickoff, cutoff, model id, source tier, input cutoffs and source hashes. Tail endpoints are pooled by the frozen model (70 attempts; 30 receptions); prices whose line touches or exceeds the pooled endpoint are ineligible. Do not turn DNP probability into a losing-zero distribution for a void-on-DNP market. A game-level coverage file accounts for every requested game/horizon, including exclusions and missing inputs. Outcomes live separately from forecasts.

## Price schema and identity, checked before outcomes

Read the existing private OddsPapi exports only after this rule is committed. Books: DraftKings, FanDuel, Pinnacle. Freeze a market-id crosswalk from market metadata, without outcomes: full-game two-way pass attempts or receptions only, including overtime only where settlement scope agrees with the statistical labels. Match fixtures by canonical home/away teams and scheduled UTC kickoff within 15 minutes; ambiguous matches fail closed. Match players by checked GSIS/ESPN id or unique normalized full name within the two pre-game teams and eligible position. Preserve suffixes first; a suffix-free fallback requires a single eligible id. No fuzzy surname, postgame-roster, or result-informed matching. Log unresolved/ambiguous names; fix mechanics by dated amendment before scoring. Report coverage without treating an absent model candidate as zero probability.

Every historical update must retain its **actual numeric line** and side. A market-level `handicap` flag is not a line. If a compact export merged updates across changing lines, the rows cannot establish an entry line or same-line close and are ineligible until a corrected reference export exists. Report this blocker; do not modify the collector in this work or infer lines from odds/outcomes.

## Entry, main line, de-vig and selection

At each fixed horizon choose the last quote observed at or before cutoff. A previously posted, unchanged price may predate forecast generation; the required ordering is forecast generation/receipt **and** quote observation no later than the decision cutoff. Do not require the forecast to predate the quote's last-change timestamp. The close is the last strictly pre-kickoff quote, never an in-play update. Exclude entries older than 24 hours at cutoff, and closes older than 60 minutes at kickoff; report these prespecified exclusions and quote ages.

Half-point main lines only: one common line per player/game/stat/horizon. Require an over/under pair at the same line, same book and market scope at entry. Among each book's valid lines choose the pair minimizing the absolute difference between the two implied probabilities; ties use lower numeric line. Among the three nominated lines choose the most frequently nominated line; ties use Pinnacle's nominated line if tied, otherwise the lower line. Only quotes at that common line can be compared or combined. The entry consensus is the arithmetic mean of each book's proportional de-vigged over probability, `q_over=(1/O_over)/(1/O_over+1/O_under)`. Require two books for primary comparisons; Pinnacle-only is a reported sensitivity. No synthetic opposite side and no mixing lines across books.

Select at most one wager per player/game/stat/horizon at the common line: choose the highest model expected return `p_side * executable_decimal_odds - 1` across eligible sides and books. Break ties by Pinnacle, DraftKings, FanDuel, then over before under. **5%** is primary; 3% and 10% are descriptive sensitivities. One unit flat stake. No threshold chosen after seeing results. No American-odds or implied-probability values silently treated as decimal odds.

## Settlement and closing value

Require documented book/market participation and settlement scope, frozen before scoring. Unknown rules are excluded. DNP/voids are not losses or realized under results. Use the existing receipt scorer's confirmed appearances and separate complete outcome feeds; retain unknown appearances separately. Half-point lines have no pushes. An integer-line extension needs a new rule including push refunds.

For each selected wager, reconstruct the **entry line's** closing over/under pair and de-vig each book separately at that exact line. Primary closing consensus uses the same entry book set, with complete same-line closing pairs for all of them. Closing main-line probabilities cannot replace a missing entry-line close. `CLV = q_close(side, entry_line) * entry_odds - 1`. Report missing closes and predefine eligible complete-case coverage; never drop a losing outcome to obtain a closing pair. Sensitivities: own-book CLV and Pinnacle same-line close. This CLV is a price-quality proxy, not realized profit or proof that closing probabilities are true.

## Information test, bootstrap and windows

One over-outcome observation per common main line/player/game/stat, including non-bets. Per stat, fit an intercept plus `logit(q_market)` and `logit(p_model)`; clip probabilities only for fitting to `[1e-6,1-1e-6]`. Fix L2 penalty 1, no cross-validation or feature/penalty search; standardize both predictors using the fitting sample. Report separation, failed fits and coefficient identifiability. Bootstrap the whole fit by **UTC game date** (2,000 draws, seed 1), preserving all games/players/books/lines on a sampled date together. Failed or single-class draws are reported; over 5% failures makes the interval insufficient. Use 5th/95th percentile bounds. CLV bootstrap resamples the same date clusters; calculate the pooled mean over wagers in each draw, preserving variable bet counts. Never bootstrap price updates or each bookmaker copy as independent bets. Require at least 20 distinct primary bet dates for an inferential pass; otherwise insufficient.

Freeze season-2026 window A as regular-season weeks 1–4 and window B as weeks 5 onward through `as_of_utc` (fixed before reading price coverage). These are chronological NFL windows, not the NBA January/current-season split. Evaluate receipt-proved forecasts as primary; reconstructive cohorts and any combination are supplementary and labelled. When primary coverage is absent in an earlier window, its gate is **insufficient**, not silently rescued with hindsight-reconstructed rows.

Fit a blend on window A only, score it on B without refitting. Report market-only, model-only and blend log loss/Brier/calibration; no pooled in-sample blend performance claim. Report independent/date-cluster counts, per-book matched coverage, exclusions, overs/unders and each cohort/horizon. Profit/ROI is descriptive and includes settlement; no profitability gate is inferred from CLV.

## Gates per stat, primary 60-minute receipt-proved cohort

- **G1:** pooled model logit coefficient has a 90% bootstrap lower bound above zero and its point estimate is positive separately in A and B.
- **G2:** mean 5%+ selected-bet CLV has a 90% bootstrap lower bound above zero, at least 200 bets, and at least 20 UTC bet dates.
- **G3:** mean primary CLV is positive in both chronological windows, each containing at least 50 bets. Missing windows or inadequate counts are insufficient and prevent advancement; they do not prove model failure.
- All gates must be assessable and pass. Price schema, IDs, quote timing, scope and receipt validity must pass mechanics before outcomes are inspected. Each stat is a distinct hypothesis; report both, including failures. The small two-stat screen qualifies only a new forward paper test, never real-money deployment.

Any assessed gate failure is recorded. No fitting a different prop model, alternative cohort, threshold or horizon to rescue a failure. No NFL priced results are produced by the export/matching task. A later scoring run must first freeze valid price coverage and settlement rules.

## Dated amendment 1 — 6 November 2026, before any price access

Two clarifications from implementation review; no priced test has run:

- In G1, replace the fixed L2 fit with **unpenalized maximum-likelihood logistic regression**, retaining the intercept, the two train-standardized logits, clipping and complete refit in every bootstrap draw. Require a full-rank design, each predictor's standard deviation above `1e-8` and standardized design condition number below `1e8`. Separation, non-convergence or failed rank checks are failed draws, subject to the existing 5% rule. Exact/near duplicate model/market predictors make the information test insufficient; do not use a penalized solver to manufacture identifiable positive coefficients by splitting the market signal between duplicates. No penalty fallback or solver tuning. G1/G2/G3 thresholds, model forecasts and cohorts are unchanged.
- References to an 'executable' price mean the recorded bookmaker reference quote for this historical test. Fills, account access and limits have not been proved. Neither positive quote-based CLV nor the subsequent paper test is a record of executable profit.
