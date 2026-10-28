# NBA award structural bug fixes: review candidate, 28 October 2026

Branch: `nba-award-bugfix-review`. **Not deployed.** `AW_BUGFIXES` defaults to 0, preserving the current site. The rejected `AW_EARLY` shrink layer is not applied and has not been re-run or retuned.

The earlier `nba-award-early-shrink` branch enabled these repairs only for its research replay. This separate branch exposes the same structural repairs as an opt-in candidate for the live award path:

- Replace the eventual-40-team-games loader filter with an explicit NBA-franchise filter, retaining early-season box scores while excluding exhibition teams.
- Apply the 65-game criterion only to MVP/DPOY; count 20+ minute games plus at most two 15-20 minute games. The existing simulated season totals and rounding tolerance stay in place; injury/grievance exceptions are not guessed.
- Average full award distributions over valid simulated award outcomes, rather than losing probability mass on no-eligible-winner draws. Combine duplicate normalised-name mass. No display top-15 renormalisation is added.

The underlying simulation parameters, logit fit, features, pools, priors and seed function are unchanged. There is no new early-season weight or flattening. With the flag off, defaults remain the legacy implementation. Claude/user approval is required before enabling it.

## Today's before/after

[Top-five comparison table](award_bugfix_review/NBA_AWARD_BUGFIX_TOP5.md) · [CSV](award_bugfix_review/nba_award_top5_before_after.csv) · [full JSON and source fingerprints](award_bugfix_review/nba_award_top5_before_after.json)

Frozen input capture: **2026-10-28 09:09:37 UTC**. Source reference: public published `417455e9d1d71326ebd1160559828f1516f749dc`.

Both columns run the existing `nba_site.awards()` path on the same frozen player/team histories, roster, overrides, published team-win prior and deterministic seeds; external downloads are disabled during the comparison. Before uses the flag off, after uses it on. **All four before top-15 name orders reproduce the published page, and every probability agrees to the published four-decimal precision** (maximum difference 0.0000498490). The published reference is included separately in the CSV/JSON.

Changes are substantial: MVP's leader changes from Shai Gilgeous-Alexander 40.7% to Luka Doncic 35.9%; DPOY from Victor Wembanyama 48.5% to Walker Kessler 26.5%; ROY remains Cameron Boozer but moves from 56.5% to 38.1%; Sixth Man remains Ajay Mitchell but moves from 78.9% to 32.4%. These are current forecasts, **not evidence of improved accuracy or profit**.

## Verification

`python -m unittest discover`: **89 tests pass, one existing skip**. New checks cover opt-in/legacy behavior, valid probability mass, award-specific eligibility, published-output identity and absence of the rejected shrink layer. The existing test-only SQLite connection is closed before Windows cleanup, and tests are discoverable with the requested command. No forecasts, decision logs, thresholds or live settings were changed.
