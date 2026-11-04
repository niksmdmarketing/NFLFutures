# NBA injury recheck and requested statuses — 4 November 2026

**Gate result: fail. No live futures or owner overrides changed.**

The corrected original replay was already completed on 29 October. It covered
2013–2026, 14 seasons, four in-season checkpoints, with matches in every season.
The original rule/runner were committed before its results. No expensive duplicate
replay was necessary; today's rule was committed at `5e22c36` before rescoring its
saved paired predictions. Previously seen outcomes remain development evidence.

| Requested gate family | Result |
| --- | --- |
| Positive gain with 90% season interval above zero | Fail: +0.000798; interval −0.000111 to +0.001799 |
| No market loss beyond the stated bound | Pass: all three markets improved on average, including the stricter zero-loss bound |
| At least 60% of seasons better/equal | Fail: 8/14; required 9/14 |

The 0.002 market bound was declared explicitly for binary futures log loss, rather
than transplanting the award rule's 0.05 winner-log-loss allowance. This choice
does not affect the verdict because all three market gains are positive.
Reproducing the original 95% interval and 10/14 gates gives the original fail.
Saved prediction SHA-256: `f8945ef1e3391233454b3d0b2a8f05eee1314641866331b47720421c593c0ecd`.
Only aggregate results go in this public research branch; ESPN rows stay private.

## Interpretation limit

This was an original-code replication: team-only ratings, synthetic undated
absences, old historical playoff/season-length mistakes, and bubble season retained.
It cannot validate switching the complete **dated** live shadow on. Historical
ESPN dated return estimates do not exist in our archive before October 2026.
The exact directly affected publication and derived claims are listed in the rule;
which original seasons actually lost joins cannot be recovered from unarchived
input versions. The six known zero-join seasons from a later exploratory run must
not be substituted for that missing history.

The research report generator still had the `.0` mismatch on current public main.
This review branch corrects it and adds a float/text-ID regression test. No
production rating/availability calculation is changed. It is not merged.

## Butler / return timing

Checked current production code at `332f1a7`:
- `_roster_adjustment` converts season minutes and player impact into one strength
  adjustment. It does not allocate a player to games on a calendar. At one cutoff
  that component is used throughout remaining games; ratings also contain team
  results and other components, so do not equate the complete forecast with minutes alone.
- Live futures call `_simulate(schedule, ratings, n_sims)` without availability.
  The dated plan is supplied separately to the archived shadow.
- `nba_avail.plan` supplies `cost_out = value * (1 - baseline)` while out.
  `draw_adjustments` draws a recovery day around the estimated return and switches
  to `cost_back`. That return cost is normally zero absent game-day information:
  it goes back to baseline rather than explicitly reallocating all 1,185 minutes
  or guaranteeing a fully healthy contribution after January.

Thus Claude's constant-roster-term observation is right. Claims that the shadow
literally reschedules minutes, or proves the baseline too weak after January, go
beyond the implementation. A January return does not justify a zero full-season
minutes override. Total season minutes alone also do not determine season wins:
the timing changes opponents faced and can affect seeding/playoffs as well.

## Forward collector status (actual records, not configuration)

The 29 October smoke bundle was verified previously: 108 linked input/output files,
three fixed seeds, 20,000 simulations each, independent GitHub receipt. Smoke is
excluded from adoption.

On 4 November, the private `nba-forward-archive` tree contains the smoke manifest
but **no `runs/YYYY-MM-DD/manifest.json` genuine daily bundles**. The eight most
recent scheduled runs all failed. Inspected run `41701753894` started 3 November
19:16 UTC, well after noon. It was in check mode: generation was skipped and the
missing-cutoff watchdog failed. This is not evidence of a newly failing simulation.
The collection windows were missed; there is currently no qualified daily forward
sample. Do not call the collector operational based on the successful smoke.

Misses must remain misses. A dependable in-window trigger is needed; simply
rerunning after cutoff or moving the old cutoff would not fix the test. No frozen
parameters, cutoff, seed, workflow or scheduler was changed by this recheck.

## Award-simulator repair status

The user supplied the two exact bugs during this audit, and both are present at
inspected main `332f1a7`: the loader drops teams below 40 games, and the 65-game
eligibility test is incorrectly applied to ROY and Sixth Man (`6MOY`). The older
`d9933f1` roster/override change did not repair those issues. The award replay
imports this same simulator, so its ROY/Sixth Man results used the incorrect gate.
The full-season historical loader can mask the early-season loader failure.
Fixes and a paired 2010–2026 award replay are being handled on a separate branch;
do not mark them deployed or complete based on this injury report.

## TypeSafe

Requested a decision review with the full evidence. The advertised TypeSafe call
was unavailable at invocation; plugin discovery was unavailable too. No new TypeSafe
percentage or endorsement is claimed. The deterministic gate verdict does not
depend on a decision-tool vote.
