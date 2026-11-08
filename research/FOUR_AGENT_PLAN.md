# Four-agent plan v3 (Claude, DeepSeek, GPT, TypeSafe) — written 8 Nov 2026

Paper only: no real money is staked by any agent. Aim: the most profitable models we can build, shown on forward paper tests. Outcomes are described as "evidence of a possible edge", never as a guarantee. Prices are for comparison and never model inputs.

## Roles
- Claude: builds and runs everything; verifies every number and direction the others claim; saves config string, commit and input hashes with every result.
- DeepSeek: cheap adversary on rules and results (goes first).
- GPT: independent second opinion; breaks ties on substance; reviews code diffs; sees disputes and the biggest decisions only.
- TypeSafe: applies agreed priorities when choosing between options (choice questions, real options as criteria keys). Option set and probabilities recorded verbatim. It never decides whether a test passes; the written rule does.

## Loop (one idea at a time)
1. Claude writes the hypothesis (with the date it was formed; the evaluation window cannot start before it) and the pass / fail / insufficient rule before running anything. The rule names the primary measure, interval method (clustered by event or period), minimum detectable effect, planned sample, and the number of ideas already tried in its family.
2. DeepSeek and GPT review the rule separately, blind to each other.
3. Claude fixes the holes; TypeSafe sets priority if there is a real choice.
4. Claude runs it once.
5. DeepSeek checks the result against the rule; GPT on dispute or a big decision.
6. A pass goes to a locked forward paper test: every prediction, available price and timestamp logged before the event, with the model version.
7. An edge claim needs a second independent forward window.

## Standing rules
- Review packet (two pages, no packet no review): rule, config string, commit, result with intervals and n, one question in one sentence, pass/fail/insufficient definitions, the prediction.
- Provenance gate: a result without config, commit and input hashes is not a result; every calibration block carries a config stamp.
- Power floor: a null below the minimum detectable effect is "insufficient", never "no effect". Insufficient means closed without adoption at the planned sample; a fresh test is needed to revisit, and the re-run counts as a new look in a family whose count has already incremented.
- Two preamble questions on every control: would a perfect model return a different number? would flipping the knob move this statistic?
- Price firewall: prices stay out of features, tuning and candidate selection. Longshot calibration is fitted on outcomes only. The sharp quote in the prop margin sample measures the margin only and never filters which props the model considers.
- Closing-line value is supporting evidence only. The rule defines the closing price, how margin is removed, limits and voided bets.
- Reviews at three gates only: rule, result, adoption.
- Multiple testing: Holm at 5% for adoption-capable decisions, counted at the portfolio level (sport x market together); Benjamini-Hochberg for exploratory sweeps, with promising results confirmed on fresh data. The count is cumulative and includes abandoned variants.

## Added in v3 after the DeepSeek and GPT replies
1. Model versions. An edge claim attaches to one frozen model version. Predictions are logged with the version and scored per version. Pooling across versions is allowed only if the change passed the no-harm measurement: on fixed snapshots, max |p_new - p_old| / se < 3.5 (same construction as assert_live_equivalent, old against new; paired draws where the seed allows). Open: whether the tolerance survives a change to BT_SIMS.
2. Minimum return. The adoption gate needs the lower bound of the interval to exceed a stated minimum return, chosen against the cost of operating the bets and written in before the run, not just "excludes zero". Open: whether the chosen level is high enough to matter.
3. Look budget. An interim read may abandon a test for futility; it may never pass one. Alpha is split (for example 0.005 interim, 0.048 final), fixed in each rule.
4. The 13 Nov first read of the selection test is descriptive: scorer validated on known-answer data first; limits and voids defined before the first void; it reports whether logging works and how far the sample is from target. Sigma for the minimum detectable effect is measured from price drift on fixture sets already held (AU prices from 27 Oct, PropLine from 6 Nov), not assumed.
5. Correctness fixes have their own path: a known, quantified defect (for example the AFL finals home edge 3.0 against 7.0) goes live if pre-registered, passes the no-harm measurement where it should not change outputs, or is validated against outcomes where it should, dated, and labelled in the version string. Profit tests are for changes that claim to improve returns.
6. The old 0.002 log-loss filter is replaced: drop a change only if it moves neither log loss nor the decision-relevant calibration statistic (tail calibration included).
7. Prop prices: no AU player-prop price history exists. Collect about 30 Sportsbet/TAB prices by hand, with a sharp quote at the same line and time. This measures the margin (at a per-row sd of 2pp, 30 rows gives about +/-0.7pp at 95%), not profit.

## Priorities
1. Selection paper test (first read 13 Nov, descriptive).
2. Player-prop price test, after the margin sample.
3. Longshot calibration for NHL and NBA titles.
4. NBA overrides season-end scoring (n_title archived); stamp the NBA, AFL and NBL calibration blocks.

## Amendment 1 (8 Nov 2026, after DeepSeek's check of v3; supersedes the wording of v3 items 1 and 3 where they differ)
1. No-harm is a measurement, not a gate on max z. Both runs use the same N (the canonical BT_SIMS = 2,000), because z grows as 1/sqrt(N) for a fixed difference (a 2.1pp gap is z about 2.2 at N = 2,000 and about 7.0 at N = 20,000), so a fixed 3.5 cannot hold across N. The check covers the bulk range p in [0.05, 0.95] only, uses se = sqrt(p(1-p)(1/N_old + 1/N_new)) (independent form; conservative if draws are paired), and reports the max and the whole distribution of z. What is compared is the sd of z against its no-change value (1.24 in the earlier old-against-new check), and nothing branches on the max. The reference object is named in each use (in-session live arm, or a named archived snapshot) and the pairing status is recorded in knobs.json.
2. Look budget. 0.005 + 0.048 overspent 0.05, and a futility-only interim cannot pass anything, so it spends no pass-side alpha: the final look keeps the full 0.05. A futility stop risks false abandonment, which is beta; each rule states the conditional power at its futility boundary, and that boundary is tied to the same minimum return as the pass gate (one floor, not two).
3. Sigma from price drift is an upper bound on pure noise (it includes information arriving), so it is used as such. The 30-row margin sample supports one pooled margin figure only (sd 2pp gives a standard error of about 0.37pp), not a split by sport or book.
