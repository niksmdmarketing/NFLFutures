# Test power and a continuous development target. Rule, version 1
Written 5 Nov 2026 (Sydney), before any of the numbers below are computed. Changes are dated amendments; nothing above them is edited. A flawed run is recorded, not hidden. This is a measurement exercise: it changes no model, live or shadow.

## Why
TypeSafe (5 Nov 2026, choice of first data-science improvement): increase test power 78% (confidence 0.73); fix the betting rule 9%; error analysis 7%; simulation structure 5%; ensembles 1%.
Futures give few outcomes (one champion a season, about 30 teams per market) and our tests use 4 to 14 seasons. Several recent tests came back inconclusive at gains of 0.001 to 0.003 log loss. If a test cannot detect the gain a challenger could plausibly deliver, running it spends effort and invites forking paths. We have never measured that limit.

## Questions
1. For each sport, what is the smallest true combined futures gain our usual test can detect (minimum detectable effect, MDE)?
2. For the NBA, does a continuous target (error in predicted final wins) move in the same direction as futures log loss, with more power? If so, it becomes a required development metric for NBA rules. Futures gates remain the decision gates.
3. For each priority sport, how many more seasons could a replay use with free data?

## Part A. Power from existing paired results (all sports with them)
- **Inputs, fixed before any SD is computed:** a script lists every committed results file in research/ and model/replay/ that reports, for a futures comparison, a paired gain per season (combined, or per market from which combined = mean of markets). The list, with the comparison and seasons, is committed before any SD is calculated. No file is dropped after its SD is seen. Files that report only pooled results are listed as excluded with the reason.
- **Per comparison:** sd_c = standard deviation across seasons of the per-season combined gain (gain = baseline log loss - challenger log loss).
- **Per sport:** sd = median of sd_c over that sport's comparisons (the median limits the pull of large, failed challengers). Also report the minimum and maximum.
- **MDE** for S test seasons, 80% power, one-sided 5% (the same tail as our 90%-interval lower-bound gates): MDE = (1.645 + 0.842) x sd / sqrt(S) = 2.487 x sd / sqrt(S). Reported for each sport at its usual S, and the number of seasons needed to detect 0.002 and 0.005.
- Limits stated now: season gains are treated as independent; sd from past challengers stands in for a future challenger's; the season bootstrap we use for gates behaves close to this normal approximation but not exactly.

## Part B. NBA continuous target
- **Target:** at each weekly checkpoint, squared error of each team's predicted final wins (mean_wins, which includes wins already banked) against its actual final regular-season wins. Season value = mean over checkpoints (equal weight) of the mean over teams. Continuous gain = baseline minus challenger (positive = better), as for log loss.
- **Data:** the six arms of the NBA joint test (model/replay/nba_joint/: A0, A1, A2, A2_noscale, A1_noleak, A2_noleak), all era-correct, 10 seasons. Actual wins from the season's regular-season results (research/replay_nba.py labels), 72 games in 2021.
- **Pairs (fixed now):** A1 vs A0, A2 vs A1, A2 vs A0, A2_noscale vs A1, A2_noleak vs A1_noleak. Five pairs x 10 seasons.
- **Per pair:** t_fut = mean season futures gain / (sd / sqrt(10)); t_cont likewise for the continuous gain.
- **Decision, fixed now.** The continuous target becomes a required NBA development metric only if all three hold:
  1. Pearson correlation between season futures gain and season continuous gain over the 50 season-pair points is at least 0.5;
  2. in every pair, t_cont has the same sign as the mean futures gain;
  3. the median over pairs of |t_cont| / |t_fut| is at least 1.5.
  Otherwise it is reported and not adopted.
- **If adopted, its use is limited to:** (a) the power check before a new NBA rule; (b) an extra gate in NBA rules: the challenger's continuous gain may not be significantly negative (90% season-bootstrap upper bound below 0 fails). It never replaces the futures gates and never by itself qualifies a challenger.
- **Disclosure:** the futures gains of these pairs are already known (they were scored for the joint test and the baseline audit). Their continuous gains have not been computed or looked at. The decision thresholds are set before computing them.
- Not covered: a margin-based continuous target (needs saved ratings, which only these arms have); NFL and NHL continuous targets (their committed replays have no expected-wins column; adding one needs a replay change under the standing replay rule and its own amendment).

## Part C. Seasons available (inventory, report only)
For NFL, NHL, NBA and football: current replay span, earliest season with the free data each model needs, whether this workspace can reach the source (NHL API: no; use a GitHub run), and the cost of extending. No replay is extended under this rule. An extension needs its own amendment and must meet research/NBA_REPLAY_STANDING_RULE.md (NBA) or an equivalent baseline check (other sports).

## Part D. Standing requirement for later rules (adopted with this rule)
Every new futures rule states, before any result: the gain it expects and why; the sport's MDE from Part A at the planned number of seasons; and, if the expected gain is below the MDE, either more seasons, a target with more power (where adopted), or an explicit owner decision (via TypeSafe) to run an under-powered test, labelled as such in the result.

## Output
research/test_power.py (inputs list, Part A, Part B), research/TEST_POWER_RESULTS.md (tables and the Part B decision), research/test_power_results.json. Results appended here as a dated section. TypeSafe helps interpret; it does not override the fixed decision in Part B.

## Amendment 1 (5 Nov 2026, after GPT's review, before any number is computed). Where this conflicts with the text above, this governs.
1. **Part A MDE is an approximate planning estimate.** Alongside the normal formula, report a paired one-sample t-based MDE (one-sided 5%, 80% power, df = S - 1, noncentral t). Neither exactly represents the season-bootstrap gates.
2. **Mean-gain power is not rule power.** Our rules also require enough seasons better, no market below a floor and sometimes stage or sensitivity checks. For comparisons that report per-season per-market gains, report an approximate probability of passing the three common gates (90% season-bootstrap lower bound above 0; better in at least 70% of seasons; no market mean below -0.0005) when a uniform true gain delta is added to the comparison's centred season-by-market gains (delta = 0.001, 0.002, 0.003, 0.005; 1,000 resamples of seasons, 1,000 bootstrap draws inside each, seed 1). The uniform-shift assumption is stated as a limit.
3. **Part B is exploratory.** Nothing is adopted and no gate is added. The 50 season-pair points are not independent (shared seasons, models, baselines, outcomes). Report the correlation within each pair (10 seasons each), the pooled correlation with a 90% interval from resampling whole seasons across all pairs together (4,000 draws, seed 1), and t_fut and t_cont for each pair descriptively. The three decision criteria and the 1.5 ratio threshold in Part B are withdrawn.
4. **Part D replaced.** Every new futures rule states, before any result, in a short paragraph: the improvement worth detecting and why; the approximate power at the planned seasons from Part A (comparison-specific where a close analogue exists, else the sport median); and the limitations. A gain below the MDE means less than 80% power under the assumptions; it is not a veto and the run is not blocked. A more sensitive development target may help screen or diagnose candidates; it does not substitute for evidence on futures while futures gates remain mandatory.
5. **Inputs.** Only valid, comparable runs enter Part A: futures comparisons (not games or props); one file per comparison, using the final corrected version where a file is marked first run, before a fix or superseded; exclusions with reasons are committed before any SD is calculated. Comparison-specific sd and MDE are reported alongside each sport's median, minimum and maximum. NBA comparisons scored on the BT_ERA=0 files are included and labelled (they are valid evidence about variability in the simulated format).

## Result (5 Nov 2026)
Run as amended; full tables in research/TEST_POWER_RESULTS.md, numbers in research/test_power_results.json. Main findings: (1) the season-to-season spread of paired gains depends mostly on how much a challenger changes forecasts (sd 0.0003 for NHL goalie tweaks to 0.03 for the NBA joint model), so planning should use the closest past comparison, not a sport median; (2) large structural challengers can only be screened for large losses or gains on 10 seasons; (3) NFL tests on 4 seasons are badly under-powered (MDE 0.003-0.011); 13 seasons roughly halves that; (4) passing all three common gates needs a noticeably larger true gain than the mean gate alone (roster-sized change at 0.002: 27% vs 77%); (5) Part B, exploratory: final-wins error tracks futures for large deteriorations (within-pair correlation 0.77-0.85) but not for the small roster change (0.15, opposite sign); nothing adopted.
