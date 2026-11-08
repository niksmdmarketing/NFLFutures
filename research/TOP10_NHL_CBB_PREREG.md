# Pre-registration: top-10 back-test edges

Written before any result exists. No results here. Discovery 2007-2019, evaluation 2020+.

---

## 1. Parsing

**The layout is not what the column names suggest.** Verified on the SportsbookReviewsOnline college-football file (same publisher, same family): in the pairs I checked, the **favourite's row carries the spread and the underdog's row carries the total**, and `ML` is per-row. Example — Georgia Tech +8500 / Clemson −23000: the underdog row holds 59.5 (total) and the favourite row holds 33 (spread). A naive `Open = spread` read is wrong on half the rows and would give you totals as spreads on every underdog.

So, before anything else: **print 20 paired rows and confirm, per file, which column holds the spread and which the total.** Do not assume; do not infer from the header.

**Pairing.** Each visitor row is immediately followed by its home row. Assert `VH` alternates V,H,V,H through the whole file and stop on the first violation — a single dropped or extra row silently misaligns every later game. `Rot` is not reliably consecutive (college file shows 291/292 then 309801/309802), so never pair by `Rot + 1`.

**Failure modes, ranked by damage:**

1. **VH alternation break** — one missing row pairs a team with an unrelated game. Everything downstream is wrong. Assert, don't repair.
2. **Spread/total swap** (above). Silent, halves the sample.
3. **Neutral site.** Confirm what `VH` says on an N game: both rows `N`, or V and H retained? If `VH` still says V/H at a neutral site, you will apply home advantage the model also applied, and neutral-site games will look clean when they aren't. Check a known Ireland or Bahamas game.
4. **`NL` / blank moneyline.** Drop **both** rows of the pair. Dropping one breaks the pair and the alternation.
5. **Venue flipping.** Some games list the actual home team as the visitor (rare, mostly neutral). Cross-check a handful against a known schedule.
6. **Date-year.** `mmdd` with no year; the season crosses the new year. Rule: month ≥ 08 → season start year, else season end year; **state the cutoff and list the games within ±10 days of it**. January bowl games and early-September openers are where this goes wrong.
7. **Duplicates/postponements.** A postponed game appears twice with different dates. Deduplicate on (unordered team pair, season) keeping the later date; log every drop.
8. **Team names.** `MiamiOhio`, `BuffaloU`, `CincinnatiU` — suffixes vary by season and by file. Build the map once, then assert 100% coverage; a silent `NaN` join is the classic version of this.

---

## 2. De-vig, and what the bias does

`decimal = 1 + ML/100` if `ML > 0`, else `1 + 100/|ML|`; `p_raw = 1/decimal`. Two-way overround `S = p1 + p2`; multiplicative de-vig is `p = p_raw / S`.

**Direction, checked:** multiplicative de-vig gives a **longshot a higher** fair probability than Shin's method does, because Shin shifts probability from longshots to favourites. A higher market probability means a **smaller** measured edge for a model that likes the dog. So:

- Multiplicative is the **conservative** choice for detecting an inflated underdog edge.
- Switching to Shin will make the +69% underdog edge **larger**, not smaller.

Therefore a big-dog edge found under multiplicative de-vig is **not** a de-vig artefact, and that conclusion should be stated before the run so it cannot be claimed afterwards either way.

Two consequences to pre-register: report the top-10 under **both** methods (the *selection* changes, not just the values), and require the finding to survive the conservative one.

---

## 3. Cohort splits and the one number each

| Cohort | The number | Legitimate if | Weakness if | Bug if |
|---|---|---|---|---|
| Early season (first 15% of games) | share of top-10 in that window, vs 15% baseline | over-represented **and** held-out reproduces | rating prior too weak early | concentrated in one season or one week |
| Neutral site (both sports) | mean `p_model − p_market` over **all** N games, not just top-10 | ≈ 0 | home edge misapplied → non-zero | exactly a constant offset |
| Back-to-back / short rest (NHL) | mean edge B2B minus non-B2B | ≈ 0 (model has no rest term, so this should vanish) | — | large, sign-consistent |
| Low-major vs high-major (CBB) | mean edge by tier, plus each tier's overround | market thin (high overround) **and** slope ≈ 1 | model better-informed, still calibrated | tier correlates with a name-map failure |
| Big underdogs (CBB, `p_market < 0.20`) | mean edge and calibration slope *within* the region | slope ≈ 1, edge from market thickness | **slope > 1** → overconfident, not better | probability clipped or floored |

**The single discriminator between "bug" and "calibration" is shape, not size.** Plot `p_model` against `p_market` in the top tail:

- **Smooth and monotone, steeper than identity** → overconfidence at extremes. A one-parameter temperature fixes it; it is a calibration defect, not a bug.
- **Discontinuous, clustered, or quantised** (many games at an identical `p_model`, edges grouped by one date, one team, one conference) → bug, most likely parsing.

Run that plot before the diagnosis, because it decides which of the remaining three sections even applies.

---

## 4. Falsification

Stop, and record why, on the first of these that holds:

1. **The top-10 does not reproduce on 2020+** — same cohorts, same direction. One held-out failure ends the direction.
2. **`D`'s 90% interval includes 0, or the half-width exceeds 0.20** → insufficient at this sample; the mirrored-tail test cannot see the effect and the top-10 is descriptive only.
3. **The tail relation is smooth and a single temperature fitted on 2007-2019 removes it on 2020+.** Then it is calibration, not a bug. Stop bug-hunting; pre-register the temperature instead.
4. **All ten edges fall in a cohort already on the known-weakness list** (big underdogs, early season). Stop diagnosing; schedule the known fix.
5. **The effect disappears under Shin de-vig** (or under the other method) — then it was a de-vig artefact and should never have been reported.

**One caveat on `D` itself, before it is used to falsify anything.** `D > 0` can arise with *zero* systematic bias, because the mirrored tails are not exchangeable when the model's error variance depends on the probability — and it will, since underdogs are both rarer and harder. Add a placebo: shuffle the model's deviation from the market **within market-probability bands**, recompute `D`, and require the observed `D` to sit outside that distribution before calling anything overconfident. Without it, a heterskedastic but unbiased model will look overconfident in the tails and send you hunting a bug that is not there.
