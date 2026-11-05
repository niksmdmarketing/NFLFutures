# Test power: results (5 Nov 2026)
Rule: research/TEST_POWER_RULE.md (with Amendment 1). Inputs fixed beforehand: research/TEST_POWER_INPUTS.md. Code: research/test_power.py. Numbers: research/test_power_results.json. Gain = baseline log loss - challenger log loss (positive = better). MDE = smallest true combined futures gain detected with 80% power, one-sided 5%; approximate planning estimates only.

## Part A. How big a gain each test can see
Per comparison (sd = spread of the per-season combined gain):

| Comparison | Seasons | sd | MDE (normal) | MDE (t) | Seasons to detect 0.002 / 0.005 |
|---|---|---|---|---|---|
| NHL goalie roster prior | 9 | 0.00035 | 0.0003 | 0.0003 | 1 / 1 |
| NHL goalie canonical | 9 | 0.00030 | 0.0003 | 0.0003 | 1 / 1 |
| NFL non-QB injuries | 4 | 0.0016 | 0.0020 | 0.0027 | 5 / 1 |
| NBA rosters A1 vs A0 | 10 | 0.0030 | 0.0023 | 0.0025 | 14 / 3 |
| NFL efficiency weight | 4 | 0.0050 | 0.0062 | 0.0083 | 39 / 7 |
| NFL state-space | 4 | 0.0067 | 0.0084 | 0.0111 | 71 / 12 |
| NFL v5 promotion | 13 | 0.0082 | 0.0056 | 0.0060 | 104 / 17 |
| NBA player term (corrected) | 11 | 0.0087 | 0.0065 | 0.0070 | 118 / 19 |
| NFL tau fade | 13 | 0.0123 | 0.0085 | 0.0090 | 234 / 38 |
| NFL recalibration | 10 | 0.0207 | 0.0163 | 0.0177 | 665 / 107 |
| NBA joint A2 vs A1 | 10 | 0.0241 | 0.0189 | 0.0205 | 896 / 144 |
| NBA joint vs A1, absence rosters | 10 | 0.0248 | 0.0195 | 0.0212 | 951 / 153 |
| NBA joint A2 vs A0 | 10 | 0.0245 | 0.0192 | 0.0209 | 925 / 148 |
| NBA joint without scalar vs A1 | 10 | 0.0315 | 0.0248 | 0.0269 | 1534 / 246 |

Sport medians (weak summaries; see finding 1): NFL sd 0.0075, MDE(t) at 4 seasons 0.012; NHL sd 0.0003, MDE(t) at 9 seasons 0.0003; NBA sd 0.024, MDE(t) at 10 seasons 0.021.

Approximate probability of passing the three common gates (lower bound > 0, 70% of seasons better, no market below -0.0005) if the true gain were delta, for comparisons with per-market season gains:

| Comparison | delta 0.001 | 0.002 | 0.003 | 0.005 |
|---|---|---|---|---|
| NHL goalie roster prior / canonical | 1.00 | 1.00 | 1.00 | 1.00 |
| NBA rosters A1 vs A0 (mean gate only in brackets) | 0.10 (0.34) | 0.27 (0.77) | 0.69 (1.00) | 0.91 (1.00) |
| NBA joint A2 vs A1 | 0.02 (0.09) | 0.03 (0.11) | 0.03 (0.14) | 0.10 (0.21) |
| NBA joint A2 vs A0 | 0.03 | 0.03 | 0.03 | 0.04 |
| NBA joint without scalar vs A1 | 0.03 | 0.03 | 0.03 | 0.08 |
| NBA joint, absence rosters | 0.05 | 0.06 | 0.08 | 0.10 |

Limits: uniform-shift assumption, seasons treated as independent, past challengers standing in for future ones, NHL "combined" here = mean of its seven markets.

## Findings
1. **Detectability depends mainly on how much a challenger changes the forecasts, not on the sport.** The season-to-season spread of the gain runs from 0.0003 (NHL goalie tweaks) to 0.03 (NBA joint model), a hundredfold range. A small tweak is tested precisely; a big structural change can only show a big win or a big loss. A sport median is a poor planning number. Use the closest past comparison.
2. **Big structural challengers cannot be tested for realistic gains on 10 seasons.** With sd near 0.01-0.03, a true gain of 0.002-0.005 needs 100 to 1,500 seasons. These tests can only reject clear failures, as the NBA joint test did. That is useful, but a pass on such a test would need a large gain.
3. **NFL on 4 seasons is badly under-powered.** MDE(t) 0.003-0.011. The 13-season NFL tests (2013-2025) are about twice as sensitive. NFL futures tests should use 13 seasons as the default.
4. **The full rule needs bigger gains than the mean test.** For the roster-sized change, a true 0.002 gain passes the mean gate 77% of the time but all three gates only 27%; the "70% of seasons better" gate is the binding one. That is by design (it guards against one season carrying a result), but it means a modest real gain usually fails.
5. **Part B (exploratory, nothing adopted): final-wins error tracks futures for large losses, not for small changes.** Within-pair correlation of season gains 0.77-0.85 for the four joint-model pairs, but 0.15 for the roster pair, where wins error improved (t +0.99) while futures got worse (t -3.41). Pooled correlation 0.80 (90% 0.69-0.91, seasons resampled), driven by the big losers. The two t-statistics are of similar size. No evidence that wins error adds power for small improvements; it is a useful diagnostic for big deteriorations only. Arm mean squared error of predicted final wins: A0 27.5, A1 27.1, A2 31.0, A2 without scalar 31.9, A1 absence rosters 27.9, A2 absence rosters 31.5.

## Part C. Seasons available (inventory)
| Sport | Committed replay span | Free data reach | Reachable here | Cost to extend |
|---|---|---|---|---|
| NFL | 2022-2025 files (4); replay code already run 2013-2025 in the tau-fade and v5 tests | nflverse play-by-play from 1999 (public; not re-checked today) | yes (GitHub releases) | low: make 2013-2025 the default; earlier seasons need burn-in years |
| NHL | 2014-2025 ex 2019-2020 (10) | NHL API and MoneyPuck xG from about 2008 (not checked today) | no (NHL API blocked here); GitHub run needed | medium |
| NBA | 2013-2026 (14) | ESPN play-by-play and box scores from 2002 (HTTP 200 checked 5 Nov for 2002-2014) | yes | low: stints rebuild in about 1 minute a season; replays could start about 2005 (stints back to 2003) |
| Football | no committed futures replay | FotMob/openfootball and Transfermarkt; span not checked | not checked | unknown; needs a replay first |
No replay was extended under this rule.

## Part D (standing, as amended)
Every new futures rule states before any result: the gain worth detecting and why; the approximate power at the planned seasons using the closest comparison above (not the sport median); and the limits. Under 80% power is stated, not a veto.

## What this suggests (for owner and GPT; not decided here)
- Default to more seasons where cheap: NFL 2013-2025; NBA possibly back to about 2005, under the standing replay rule.
- Favour challengers that change forecasts modestly and in a targeted way; they can be tested to 0.001-0.003. Big rebuilds can only be screened for large failures.
- Any change to gate design (for example the 70%-of-seasons gate) would be a separate decision with its own rule; nothing changes here.
