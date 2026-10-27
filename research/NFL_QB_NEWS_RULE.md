# NFL futures: does point-in-time QB absence information improve the forecast? Rule, version 3, fixed before any gains (27 Oct 2026, Sydney)

Status: **version 3, draft for GPT's final check.** GPT's second review was applied in full (TypeSafe: apply all fixes, then a final GPT check, 99%). Version 3 replaces the version 2 text wherever they differ; see the section at the end.
- **Version 1** (git history) used only GPT's selected list of absences. GPT's review rejected it as primary: the list was selected partly on outcome, and some ranges were invented. TypeSafe chose to rebuild with outcome-independent coverage (95%) rather than run v1 as exploratory.
- Nothing has been run beyond identity checks. No gains have been computed for v1 or v2.

## Why
- **Perfect-starter benchmark** (research/NFL_QB_ORACLE_RULE.md): +0.0063 log loss for v5-core on 2013-2025.
- **The live whole-season shortcut:** about 0.
- **This test** asks how much is reachable with information available at each checkpoint.

## Information cutoff
- Checkpoints after weeks 4, 9 and 13, seasons 2018-2025.
- **Cutoff:** 12:00 UTC on the day after the last regular-season game of week w.
- **Available:** play-by-play and results through week w; the official weekly injury reports (game status) and weekly roster status for weeks ≤ w (nflverse); news reports whose US publication date is on or before the date of the last week-w game.

## Episodes (outcome-independent coverage)
- **Incumbent:** the team's QB with most dropbacks through week w (the reference QB of the benchmark).
- **T1 (official status):** the incumbent did not start the team's latest game(s), consecutively up to week w, and for each of those weeks was listed Out or Doubtful on the official injury report or held roster status RES (IR, PUP, NFI) or SUS. m = the number of such consecutive missed games.
  - Every listed absence counts, whatever its eventual length.
- **T2 (news):** a case in GPT's list (research/qb_news/gpt_qb_reports_2018_2025.csv) whose QB has not started since the absence began, with at least one report published by the cutoff.
  - This adds absences T1 cannot see yet: an injury in the week-w game itself with a published timeline, or the regular starter returning while a backup has become the incumbent.
  - **The list's selection affects only which timelines are available, not which absences count.** Absences with no listed report still enter through T1, with the missing-duration rule below. Its inclusion trigger covered QBs "reported as likely to miss 2+ starts", so explicit timelines are collected largely by a reporting trigger.
- **Merging:** if T1 and T2 refer to the same QB, they merge. If T1 is active for the incumbent, a T2 case for a different QB of the same team is ignored.

## Duration
**Primary: bounded statements only.** These come from research/qb_news/qb_reports_coded.csv, column bounded:
- season-ending;
- a stated range or single figure in weeks or months, but not "at least" or "minimum";
- a fixed suspension;
- "sit for the remaining N games".

How they are applied:
- **Anchor:** the report's publication date. The future games falling within lo to hi weeks of it (months × 4.35), or the stated number of games minus team games already played since the report.
- **Already out:** if the starter is still out at the cutoff, the stated range is conditioned on that. The remaining support starts at the next game.
- **Exhausted range:** a range already exhausted while he is still out is treated as missing information.
- **Withdrawal:** a later unbounded statement of a duration kind withdraws an earlier bounded estimate, which then becomes missing information. These kinds are week to week, multiple weeks, IR, PUP, "out until", and lower bounds. "Ruled out", questionable, day to day and no-timeline statements do not withdraw it, since they concern one game or carry no duration.
- **Cleared to play** (latest report): no further absence is assumed. Nothing else (start or bench) is assumed.

**Missing duration (no bounded report, or withdrawn or exhausted):** use earlier seasons' absence runs (research/qb_news/absence_runs.py).
- A run is a consecutive stretch in which an incumbent missed starts while listed Out, Doubtful, RES or SUS. Seasons 2013 to Y-1 only (walk-forward), conditioned on runs at least as long as the m games already missed.
- Remaining absence = sampled run length - m.
- Runs ending at the season's last game are kept at their observed length; they are censored, which is disclosed.

**Sampling:** for each team with an active episode, each simulated season draws one remaining absence R.
- **Within a bounded range:** uniform over the integer games in [a, b], a stated simplifying assumption.
- **Missing duration:** one sampled run.
- The incumbent's replacement starts the first R remaining games and the episode's QB the rest.
- Draws come from a separate generator seeded by season, week and team, so they are identical across seed sets, cores and λ. The simulator's own draws are unchanged (simulate option adj_sims).

**Sensitivity: version 1's full wording mapping** (lower-bound extensions, IR and PUP minimum + 2, week to week = 2-4, short and vague wording), with the same missing-duration rule otherwise. It is labelled as model assumptions.

## QBs and values
- **QB values and reference:** frozen at the cutoff (ratings.qb_values on pre-cutoff play-by-play). QBs without enough data get the frozen low-sample value.
- **Replacement QB (frozen fallback without announcements):** in order of preference:
  1. the starter of the team's latest game, if the incumbent missed it;
  2. otherwise, the non-episode QB with most dropbacks in the game where the absence began;
  3. otherwise, the team's other QB with most dropbacks this season.

  Contemporaneous starter announcements are not in the data. This is disclosed.
- **Shift in each game:** scale × λ × (value of that game's QB - reference value), home minus away, added to the simulated margin. Playoffs get no QB adjustment.
- **Not modelled:** a replacement's own later injury, trades and benchings. The team rating already reflects the QBs who played before the cutoff; the "starter minus reference" form is common to all arms, and possible double counting is disclosed.

## Arms (v5-core primary, v4-core diagnostic; λ = 0.5 primary, 1.0 sensitivity; same seeds as the benchmark)
- **none:** no adjustment. The identity check must match the benchmark's none rows for 2018-2025 exactly.
- **shortcut:** the live whole-season logic at the same information: the current replacement for every remaining game, for each active episode.
- **news (primary):** episodes, bounded durations or missing-duration runs, and sampled return paths.
- **news_mapping:** the sensitivity above.
- **oracle:** the benchmark's per-game arm, rescored on 2018-2025.

## Scoring
- Mean team-level binary log loss for division winner and make-playoffs after weeks 4, 9 and 13.
  - Six cells, equally weighted within a season, then seasons equally weighted (8 seasons).
  - Probabilities averaged over seed sets A and B and clipped to [0.001, 0.999].
- **Gains** (positive = second arm better): none - news (primary), shortcut - news, none - shortcut, none - news_mapping, and none - oracle. The capture share is news gain / oracle gain on the same sample and scoring.
- **Bootstrap:** paired whole seasons, 8 clusters, 10,000 draws, seed 20261028, one-sided 90% lower and upper bounds (10th and 90th percentiles).
- **Seed sets:** each gate is evaluated on seed sets A and B separately; any disagreement makes the result inconclusive.
- **Also reported:** results by market, checkpoint and season; episodes by trigger; duration sources (report code or empirical); and Monte Carlo noise.

## Decision (v5-core, λ = 0.5, primary none - news)
- **Pass:** lower bound > 0, gain ≥ 0.001, and neither market negative. Implement and archive a live shadow input; displayed v5 stays unchanged pending forward evaluation.
- **Fail:** upper bound < 0.001. This specified mapping fails; this is not generalised to all news-based QB inputs.
- **Otherwise inconclusive.** news_mapping, λ = 1.0 and v4 cannot rescue a failed primary. No retuning and rerunning under this rule.

## Disclosed limits
- **Sample:** eight seasons.
- **Timelines:**
  - they cover GPT's list only; other absences use the empirical runs;
  - "earliest report" means earliest located;
  - publication dates are US dates;
  - the anchor is the publication date, not the surgery or placement date.
- **Status data:** official status data only reach into the week of the cutoff.
- **Exposure:** version 1's coding and the oracle results were seen before this version.

## Version 3 changes (27 Oct 2026, after GPT's second review; these replace version 2 where they differ)
1. **Coverage, from official status only.** News never adds an episode.
   - **Incumbent:** fixed when the absence begins, as the team's dropback leader before that game (week 1: the previous season's leader), and kept until the run ends. A run ends when he starts again or is no longer listed; the latter is a medical return.
   - **Listed** now also includes Questionable together with roster INA (inactive) for that week: a confirmed injury absence from a completed game. INA alone (a healthy scratch) does not count.
   - **Dropped:** the version-2 news triggers (T2).
     - An injury in the week-w game enters at the next checkpoint, once it shows up in official status.
     - A long-injured starter whose backup now leads in dropbacks stays the episode's QB through the fixed incumbent.
2. **Censoring:**
   - **Survival model:** missing durations come from a discrete survival (Kaplan-Meier) model of earlier seasons' runs (2013 to Y-1). Runs reaching season end are right-censored.
   - **Sampling:** given m games already missed, each further game is a return with hazard h(l), where l = total missed; otherwise he misses it.
   - **Sparse tail:** where fewer than 10 runs are at risk, one pooled constant hazard applies from there on.
   - **Unresolved draws** stay out through the forecast horizon.
3. **Eligibility floors (hard constraints, every arm and every draw):**
   - **Placement:** a QB on roster RES at the latest week was placed at the start of that RES streak.
   - **Floors:**
     - 2020-21: at least 3 team games from placement;
     - 2022-25: at least 4;
     - 2018-19: no return within 8 weeks of placement (designation).
   - Every sampled return respects the floor: R = max(R, remaining floor).
   - **Not separated:** reserve sub-types (IR, PUP, NFI) are not distinguished, so the IR minimum applies to all RES. Earlier seasons' runs pool different IR regimes; the floor is applied at sampling, and this is disclosed.
4. **Timing:**
   - **News deadline:** reports whose US publication date is on or before the date of the last week-w game. This is a conservative, reproducible deadline before the 12:00 UTC cutoff.
   - **Anchor:** the timeline's reference point is not in the data, so the publication date is used as the disclosed fallback. Weeks and months stay calendar intervals before being mapped onto scheduled games.
5. **Revisions:**
   - A later bounded report replaces an earlier bounded one.
   - Unbounded later statements (week to week, IR, ruled out…) update status or eligibility and do not replace the bounded timeline. IR acts through the floor.
   - **Cleared to play** (the latest relevant report) means no further medical absence. It does not mean he starts; the replay assumes a healthy incumbent starts, which is disclosed.
   - Revisions flagged as ambiguous before results: none beyond those listed in the coded file.
6. **New arm "empirical":** the survival model plus floors, with no news. The comparisons:
   - empirical vs none: the duration model alone;
   - news vs empirical: the extra value of collecting bounded timelines;
   - news vs none: the primary.

   The capture share against the oracle is descriptive only.
7. **Decision unchanged:** primary v5-core, λ = 0.5, none - news; pass = live shadow input only; seed-set disagreement = inconclusive.
