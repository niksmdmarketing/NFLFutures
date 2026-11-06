# NBA props Amendments 5–8: independent code review

Reviewed public commit **`679409641761d5827ffaf1368e4c693fac3caf0a`**, branch `claude/nba-props-price-test`, on 6 November 2026 (Australia/Sydney). The branch was not edited.

No real odds rows, box-score rows, forecasts, fitted challenger artifact, check results or price-test results were opened. Review used source code, fabricated cases and one private SportsGameOdds identity-file **header only**. That header contains identity/line fields and no price/outcome columns. Its schema and source commit are in `identity_schema.json`. No identity matching was run on actual records.

## Findings

Locations below refer to the reviewed commit, not the proposed files. These are code paths and synthetic counterexamples; they do not establish that a particular archived record is affected.

1. **[P1] Invalid appearance mixtures are silently converted to confident probabilities.** `research/nba_props_challenger_c.py:40–46`. Subtracting nonappearance mass, clipping negative mass and normalizing can conceal an impossible stored distribution. In a fabricated example, stored `[0.7, 0.3]` with `p_appear=0.2` becomes conditional `[0, 1]`, although positive-count mass alone exceeds appearance probability. At zero appearance, the helper returns an all-zero array, which later becomes a missing model probability. Validate the mixture, reject undefined conditioning, and recover the positive-count tail by division to avoid cancellation near zero. The proposed strict validator deliberately requires a separate policy for lossy archive rounding; see the methods note.

2. **[P1] The fallback reads numeric prices despite its identity-only contract.** `research/nba_props_sgo_names.py:92–93`, also `:35`. Both CSV loads request all columns. The OddsPapi file includes entry, opening and closing price values; only closing-price presence is subsequently used. There is no evidence that price magnitudes influence the votes, but the reader crosses the stated no-price boundary. The patch reads explicit identity columns and a Boolean `has_close_quote` flag. A separate private-collector patch adds that metadata when reducing API responses. Existing exports require that metadata before the patched fallback can run. A close timestamp alone does not prove a price was present, since the collector assigns time independently of `price` being non-null.

3. **[P1] Development records are not restricted to the registered replay/model.** `research/nba_props_challenger_c.py:57–66`. A `_60_` filename and an eligible cutoff suffice: `params_id`, `horizon_min`, replay status and simulated generation time are unchecked. A later-cutoff record from a different model/non-replay can replace the frozen replay. The default upper tip bound is correct, but the lower development date is not explicit and callers can extend the `end` parameter. The patch requires frozen-b 60-minute replays with timing evidence, enforces the registered dates and regular season, caps `end`, and keeps the latest eligible cutoff.

4. **[P2] Terminal correction makes the transform depend on the last array position.** `research/nba_props_challenger_c.py:116–119`. All CDF entries are interpolated, then only the final one is set to 1. If several entries have the same CDF value 1, they can receive different mapped values. A fabricated point mass `[1,0,0]` with a map ending at 0.8 acquires roughly 20% mass in the last bin. The resulting distribution is still a valid monotone CDF, but it does not implement a single `g(F(k))` for identical arguments. Anchor `g(1)=1` consistently before interpolation. Record the boundary convention before refreezing.

5. **[P2] Missing minutes select the high-minutes calibration band.** `research/nba_props_challenger_c.py:33–37`; upstream missingness at `research/nba_props_price_run.py:82–83`. `band_of(NaN)` falls through to band 2. A missing minutes distribution can therefore receive an over-25-minutes recalibration. Valid boundaries are correct: 15 belongs to band 0, 25 to band 1. The patch validates minutes inputs and uses a shared one-based expected-minutes calculation. An identity stat needs no band lookup.

6. **[P2] The holdout log score is capped, which can change keep versus identity.** `research/nba_props_challenger_c.py:137`. `max(probability, 1e-9)` is not the literal mean log probability of the actual value. A fabricated two-observation case reverses the keep decision under that cap. The attached patch uses the literal log score, with zero probability giving negative infinity. Alternatively, retaining the capped score needs an explicit dated method amendment before deciding which stats to keep. The synthetic self-test is adjusted to use observations within its fabricated finite support.

7. **[P2] Freeze trusts a saved decision from an unverified cohort.** `research/nba_props_challenger_c.py:176–179`. `freeze(dirs)` loads a prior check JSON, then loads/refits the supplied directories without binding that check to those records, split or implementation. A stale check can decide which maps survive. The patch recomputes the holdout decision from the same freshly loaded cohort used for the final refit. It never uses the old result file to select maps.

8. **[P2] Scoring does not enforce identical candidate rows.** `research/nba_props_price_run.py:239`, called separately at `:280–281`. `_evaluate` drops missing model probabilities independently. A malformed/unavailable challenger probability can yield different observation counts while both evaluations continue. The patch stops if challenger probabilities are unavailable on the frozen model's primary rows, and `_evaluate` rejects invalid probabilities rather than changing the cohort. Bet selections may legitimately differ between models; the shared candidate rows, lines, books and gate definitions must agree.

9. **[P2] Missing/zero-minute participation is excluded but not counted.** `research/nba_props_price_run.py:182`. This correctly implements Amendment 5's exclusion but loses the unknown-participation counts required by Amendment 4 and retained by Amendment 5. The patch reports unknown player-games and player/stat lines separately. It preserves settlement on positive-minute full-game stats, including early exits, as the owner decided.

10. **[P2] Name aliases can manufacture the two required agreeing pairs.** `research/nba_props_sgo_names.py:73–76`. Candidates are a set of `(player_id, name)` tuples, then each tuple increments the ID's vote count. Two name variants for one ID can count twice for a single bookmaker/stat pair. A synthetic case with only one real pair per game passes the existing two-pair rule. Deduplicate by player ID within each bookmaker/stat pair.

11. **[P2] Duplicate fixtures can manufacture the two required games.** `research/nba_props_sgo_names.py:49–51`, `:81–86`. Two OddsPapi fixture IDs may both pair to the same SGO event. Each then contributes a separate match toward `MIN_GAMES`. A synthetic single-event case passes. The patch rejects ambiguous many-to-one pairings so the two-game minimum refers to distinct games.

12. **[P2] Rounding accepts lines that are not equal.** `research/nba_props_sgo_names.py:38`, `:58`. Rounding both sources to one decimal makes distinct values such as fabricated 0.54 and 0.50 compare equal. Amendment 8 specifies equality, not a tolerance. The patch compares numeric lines directly. Half-point lines remain exactly representable.

13. **[P2] Stored row names override authoritative live names.** `research/nba_props_price_run.py:143–144`. The `{**sgo, **nmap}` merge correctly prioritizes live names over SGO, but a non-null raw `player_name` then overrides the merged map. The patch resolves by key from the live/fallback maps first. It also treats blank/null live-map entries as unnamed, so they can use the registered fallback.

## Checks that agree with the amendments

| Requested check | Conclusion |
|---|---|
| Monotonicity / valid CDF | For valid inputs, isotonic knots, clipped cumulative maximum, terminal correction and the convex floor mix produce nonnegative unit-mass distributions. Finding 4 concerns the pointwise map/boundary convention. |
| Expected-minutes support | Producer stores minutes on support **1,2,…**. The calculation divides by their mass, so it remains the forecast's expected minutes conditional on appearing. Valid 15/25 boundaries are correct. |
| Development end | Default `tip < 2026-01-12 00:00 UTC` is correct and excludes a Jan-12 tip even if its cutoff is Jan 11. Source validation needs finding 3. |
| Latest cutoff | Selection compares eligible cutoff timestamps, includes exactly tip-minus-60, and chooses the latest cutoff. This part is correct. |
| Holdout split | Uses **tip time**, before 15 Dec for fitting and from 15 Dec through 11 Jan for checking. Correct subject to loader provenance. |
| Keep / identity / refit | Strict improvement keeps a stat; ties/non-improvement give empty stat maps, which apply identity. Kept maps are refitted on all development data. Findings 6–7 qualify the score/handoff. |
| v2 / v3 / c conditioning | Both v2 and v3 call `conditional`; c applies recalibration to the conditional v2 PMF. The normal valid-mixture path is correct. Finding 1 covers infeasible/undefined inputs. |
| Common scoring gates | `_evaluate` supplies the same G1/G2/G3 definitions, thresholds and date/bootstrap methods. Finding 8 adds the missing row invariant. |
| Missing challenger file | Current code stops before fitting/scoring, but only after assembly has read prices/outcomes. The patch stops before that I/O. This is an earlier guard, not a claim the original silently scored b alone. |
| Game pairing | Both canonical teams and an inclusive 15-minute tolerance are checked; a locally ambiguous SGO match is skipped. Finding 11 adds the reverse uniqueness check. |
| Game-level tie | The top candidate must have at least two votes and strictly exceed the next candidate. Correct after finding 10's vote-unit fix. |
| Across-game rule | At least two matched games and at least 80% agreement, including exactly 80%, are correct after finding 11. Ambiguous/unmatched games do not enter that denominator, as written. |
| Live map versus fallback map | Dictionary merge order is correct; finding 13 concerns the later raw-row override and unusable live entries. |

## The 0.1% floor and other method details

**The floor is mathematically acceptable, and should be recorded.** A mixture of 99.9% calibrated PMF and 0.1% frozen conditional PMF preserves validity and monotonicity and gives positive support wherever the frozen PMF is positive. It changes both the holdout decision and final predictions, so it belongs in the dated method registration and frozen artifact. Appearance probability remains unchanged when reattaching the nonappearance mass.

Also record the **200-CDF-pair per-band minimum with identity fallback**, and resolve the **1e-9 evaluation cap**. These are not present in Amendment 6's text. Use an ex-ante method decision rather than choosing whichever treatment keeps a challenger after inspecting performance.

The forecast producer rounds **p_appear to 6 decimals and count-PMF entries to 7 decimals** (`research/nba_props_live.py:508,513–514`). Consequently some stored arrays may have normalization or mixture discrepancies caused by serialization. Exact conditioning is not recoverable in every rounded record, especially near zero appearance. The proposed strict validation permits only machine roundoff and can stop those archives. A separately recorded, precision-based tolerance/reconstruction/exclusion policy is required before relaxing it. This review inspected no actual archive PMFs and therefore makes no claim about affected counts.

## Patch package and validation

- `nba_amendments_5_8_fixes.patch`: proposed public-source fixes, based exactly on the reviewed commit.
- `private_collector_quote_presence.patch`: optional supporting metadata change, based on the private collector source commit in `identity_schema.json`. It affects newly produced rows; existing exports will still need the Boolean field. No collector was modified or run here.
- `METHOD_REGISTRATION.md`: method decisions and data-preparation dependencies to record before refreezing or scoring.
- `test_proposed.py` and `proposed/`: portable synthetic regression checks and source copies.

**23 synthetic regression tests passed**, covering conditional edge cases, CDF validity, minutes boundaries, development timing/source filters, holdout split/ties, fresh-cohort freeze, paired scoring, early missing-file failure, unknown participation counts, vote/game uniqueness, exact lines, the 80% boundary, live priority, and whitelisted identity I/O. The proposed challenger and SGO self-tests also passed. Both patches passed `git apply --check` against their reviewed source snapshots; proposed Python sources compile.

No real fit, freeze, mechanics, name-fallback run or price scoring was performed. The frozen artifact's contents, actual development coverage and any actual pass/fail results remain unverified. Changes to c's endpoint/log-score treatment require a dated amendment and a new freeze/hash before price scoring.
