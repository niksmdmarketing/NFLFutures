# NFL props price-test preparation — 6 November 2026

Completed on `codex/nfl-props-price-test`. Model v1.1 and the initial rule were frozen in commit `9434ed1` before any NFL price access. Original model code and parameters remain byte-identical to public revision `370ceb4`.

## Export

As of **2026-11-05 14:56:17 UTC** (6 November in Sydney), all **121** season-2026 regular-season games that had kicked off are represented at both cutoffs.

| Information cutoff | Games exported | Distribution rows | Receipt-proved games | Receipt-proved rows | Supplementary reconstructed games |
|---|---:|---:|---:|---:|---:|
| 60 minutes | 121 | 3,096 | 19 | 496 | 102 |
| 6 hours | 121 | 3,091 | 16 | 417 | 105 |

Total: **6,187** line-agnostic count distributions. Every row has a player name, GSIS id and ESPN id. Each row identifies its horizon, game, team, stat, conditional PMF, appearance probability, cutoff and provenance. Receipt-proved PMFs exactly match their original snapshots. The two horizons share games and are not independent samples.

The **12 January 2026 playoff games** are explicitly marked unsupported: both this frozen model and its receipt scorer are regular-season-only. No postseason forecasts were invented.

## Limits that matter

The 19/16-game receipt cohorts are the genuinely pre-cutoff archived forecasts. The other rows reconstruct earlier games from revised historical statistics and pre-cutoff dated depth charts, with the original news/injury layer unavailable. They are supplementary, not proof of original as-known-then inputs. No reconstructed row is eligible for the rule's primary receipt cohort.

There are no primary receipt observations in the early chronological window. The strict primary gates therefore currently lack the necessary two-window coverage; this is insufficient evidence, not a failed price/profit test. Forecast ages are retained through generation/cutoff timestamps and summarized in `audit.json`.

## Matching and validation

- 33 NFL-prop tests passed, including 13 new preparation tests.
- The full export audit passed: unique keys, PMF validity, count-tail boundaries, cutoff filtering, original receipt-PMF equality, roster timestamps and completion lag.
- All 121 fixtures self-matched; all 6,187 canonical names and 6,187 punctuation/case variants returned their correct ids. No false ids were observed in these source-name checks.
- A complete synthetic CSV-to-export join matched 10/10 fixture/player rows. These are mechanics checks; an actual bookmaker match rate remains unknown until real reference rows arrive.
- The matcher rejects ambiguous names/fixtures, explicit suffix conflicts, ID/name contradictions, unsupported positions and unverified market ids. Provider player keys are not treated as ESPN ids.

## Rules and NBA review

`NFL_PROPS_PRICE_TEST_RULE.md` fixes the common main line, proportional de-vig, 5% edge threshold, exact-entry-line CLV, UTC-date bootstrap, chronological windows and pass/insufficient/fail handling. Its dated pre-price amendment requires an identifiable unpenalized information-test regression: duplicating the market cannot manufacture a positive independent-model coefficient through ridge shrinkage.

`NBA_PROPS_PRICE_TEST_PROPOSED_AMENDMENTS.md` supplies dated proposals only. The NBA work is untouched.

**Schema issue to check before backfilling/scoring:** the existing compact collector collapses by book/market/outcome/player and stores market metadata `handicap`. It does not establish that actual numeric line changes remain attached to entry and closing prices. A Boolean handicap flag is not a line. Require a verified line-aware reference export for same-line de-vig/CLV; the OddsPapi scripts were not changed here.

No OddsPapi key was read, no NFL odds were downloaded or inspected, no paid endpoint was used, and no priced/profitability result was calculated. Every future price remains reference data only.
