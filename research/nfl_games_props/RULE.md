# Independent NFL games and opportunity-props foundation, 23 October 2026

Written before fitting/scoring. Local experimental prototype; no live futures,
NBA, website, archive schedule, repository publication or betting changes.

## Sources and what is borrowed

- Open Source Football, Ben Dominguez, 2021: lagged passing/rushing EPA, split
  offence/defence, pre-game logistic baseline. Independent implementation of the
  ideas, not a copy of tutorial code or its cross-validation procedure:
  https://opensourcefootball.com/posts/2021-01-21-nfl-game-prediction-using-logistic-regression/
- FiveThirtyEight NFL Elo: adapted fixed K20, HFA65, two-thirds season carryover,
  margin-of-victory update. Regular-season-only benchmark, not a claim to exactly
  reproduce every historical initialisation/QB version. MIT attribution retained:
  https://github.com/fivethirtyeight/nfl-elo-game
- nflverse data/definitions plus established count/conditional-allocation
  distributions. These are building blocks, NOT a third turnkey NFL prop model.
  https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html

## Timing/data restrictions

Only earlier games with kickoff + 6 hours BEFORE target kickoff - 1 hour update
state. Team state and player candidate lists never come from the target box,
actual starter or final-season roster. Historical files are revised modern
vintages, not independently archived original publication versions: call this a
lagged retrospective test, not perfect point-in-time replay.
Do not use current-season FTN participation (published after season), current
weather observations for historical forecasts, closing lines, target-game QB IDs,
actual future snaps or eventual target totals as forecast inputs.

Use local existing pbp 2009–2026, schedules/results, weekly player stats and snap
counts. Hash actual inputs, audit coverage and ID matches. No names-only matching.
Completed results are labels only. Future previews use only currently held data
and must disclose its latest completed-game dates and input provenance.

## Game models

Evaluate 2018–2025 regular seasons, refitting only on prior seasons (features
2010 onward). Fixed settings, no grid search. Three references:
1. Adapted Elo, no fitted market inputs.
2. OSF-inspired logistic on eight lagged EPA components, regularised, train-only
   standardisation. Recency half-life five team games, at most twenty observations
   from current/prior season; league-neutral fallback. Not exact tutorial clone.
3. Ridge margin and total means on those same components, plus separate discrete
   empirical residual distributions from earlier out-of-season predictions.
   Margins and totals are separate forecasts, NOT a coherent score simulator.
   Report home/away/tie margin probabilities and conditional non-tie win score.

Score winner log loss/Brier (actual ties separate), margin RMSE/RPS, total RMSE/RPS,
calibration and per-season results. Compare simple prior-only league-score and
team-form baselines. Compare archived v4 reconstructions on exact shared rows
where available; identify that subset/version rather than pretending it is the
entire latest live QB/injury pipeline. Closing spreads/totals only score benchmarks.

## First prop scope: attempts and receptions

Team pass-attempt volume predicted from prior team/opponent attempts, pace and
game-strength features, using a fixed regularised Poisson mean and fitted NB
dispersion. Baseline prior team average. No realised game script as an input.

Player candidates: prior known QB/WR/TE/RB/FB with recent team offensive activity;
remove known moves only after an earlier observation. No unseen debut forecast
and no claim of complete rosters. Record actual excluded first appearances as
coverage diagnostics only, NEVER use them to select prediction candidates.

Use snap-count positive offence snaps for appearance labels, mapped by checked
PFR-to-GSIS IDs. A missing player is DNP only in a complete, reconciled team snap
file; otherwise unknown. Appearance model uses pre-game role/history, not injury
news that has not been replay-validated. Report this missing injury layer.

Conditional on appearance, allocate team attempts to QB attempts, or to receiver
targets then catches. Shrink shares/catch rates towards position priors using
fixed pseudo-counts; fit one beta-binomial concentration per stat on earlier
seasons. Counts cannot exceed team attempts. Marginalise over uncertain team
attempts, and separately store conditional and DNP-zero distributions. The latter
is not automatically a bookmaker's DNP settlement convention.

Props train 2018 onward, evaluate 2021–2025. Compare same-appearance-probability
conditional season-average and recent-form NB baselines. Score RPS and log score,
randomised PIT including zeros/tails, per-year results, prior high-volume subgroup
(QB expected attempts >=10; receiving expected receptions >=2), and appearance
log loss. Formula lines fixed from lagged baseline means, not selected afterwards.

## Decision

Pre-fit data correction: six historical rows had official attempts/targets but
zero offensive snaps (including special-team contexts). Official positive
production establishes involvement even when the offensive snap label is zero;
use it as an appearance LABEL, never as a pre-game input/candidate selector. This
is not a statement about any book's participation/void rules. First validation
failure and stale local schedule are recorded; no performance had been fitted.

This run establishes reproducible foundations, not adoption. A candidate is
promising only if overall paired RPS gain has a positive season-block bootstrap
lower bound, is better in >=4 of 5 prop seasons (>=6 of 8 game seasons), and does
not conceal important calibration/role-group losses. Report every model/stat,
including failures. No tuning on failed test results, no profit claim without
historical obtainable prices/settlement/costs. Live promotion requires a separate
review and prospective archive. All outputs and raw data remain local/private.

## Baseline implementation correction after first run (disclosed)

The initial `avg` control was the average over appearances in the last eight TEAM
games, not the specified whole season average. Keep initial results and scores.
Add the correctly lagged whole-current-season average across player teams,
falling back to prior season only when current-season history is absent. Fit its
NB dispersion on earlier seasons. Re-score this additional control without
changing/refitting ANY candidate forecasts. Also report high-volume subgroup PIT
and opportunity-distribution concentration bounds. No decay/shrinkage search or
claim these already inspected years are a new clean holdout.

## Amendment (26 Oct 2026): publication on the public site
The Decision section above said outputs remain local/private. On 25-26 Oct the experimental QB pass-attempt and reception forecasts were published on the public site (NFL > Forecast > Player props; pull requests #1 and #2) without a dated record of that change; this amendment records it.
- **Decision** (TypeSafe 74%, given that the protected site cannot change before the GitHub minutes reset): keep the page public.
- **Labelling:**
  - experimental;
  - independent model probabilities, not bookmaker lines or betting advice;
  - "market edge established: false";
  - the historical evidence as stated on the page;
  - the injury-status adjustments shown as uncalibrated assumptions (research/nfl_games_props/STATUS_CALIBRATION_RULE.md).
- **Inputs:** the page publishes only this project's own forecasts, from open nflverse inputs. FiveThirtyEight Elo is credited under its MIT licence (THIRD_PARTY_NOTICES.md).
- **Not changed:** the forecasting method, parameters and the forward archive.
- **Promotion:** live promotion beyond "experimental" still requires the separate forward review in the Decision section.
