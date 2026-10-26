# NFL futures: should v5 replace v4 as the displayed model from 2027? DRAFT rule for review before any code or results (27 Oct 2026, Sydney)

Status: **draft, sent to GPT for review.** Nothing has been run. Asked by the user; TypeSafe ranked it the most useful next improvement (58%).

## Why
- v5 has run as an archived live shadow since October 2026. Compared with v4 it has:
  - recency-weighted ratings (pipeline/nfl_engine.py: half-life 4 weeks, team-effect shrinkage 60);
  - less rating uncertainty (tau 4.0 / sigma 12.0 vs 5.0 / 11.37);
  - a playoff home edge of 4.0 vs 1.8;
  - in season, a QB-availability correction of last season's prior.
- Its adoption evidence ("+0.0032 mean log loss, 11 of 13 seasons") came from replays that simulated 2013-2019 with the wrong playoff format (7 seeds, one bye). That evidence must be redone before any promotion.
- In the corrected replay, v5like is closer to calibrated in season (e.g. division at week 4: slope 1.18 vs 1.31; make-playoffs at week 4: 1.14 vs 1.28).

## Arms
Both built as in research/nfl_futures_diagnosis.py:
- **v4wf:** v4 components with walk-forward weights; scale 0.89, tau 5.0, sigma 11.37, home edge 1.8, playoff home edge 1.8.
- **v5like:** engine ratings (recency 4, shrinkage 60) with walk-forward weights fitted on seasons before Y; scale 0.89, tau 4.0, sigma 12.0, home edge 1.8, playoff home edge 4.0.

Both arms use:
- the correct playoff format by season, neutral sites with no home edge, the sweep option off;
- 10,000 simulations, the same seed per season and checkpoint;
- no QB, pressure or QB-prior layers (not reconstructable in the replay; a disclosed scope limit).

## Historical test
- Seasons 2013-2025. Checkpoints: pre-season and after weeks 4, 9, 13 and 16.
- **Primary cells:** division winner (multi-class log loss of the winner) and make-playoffs (binary log loss) after weeks 4, 9 and 13: six cells, as in the paper-bet rule.
- **Secondary cells:** pre-season and week 16 for both markets; No. 1 seed, conference and Super Bowl at every checkpoint.
- Probabilities clipped to [0.001, 0.999]. Per season the six primary cells are averaged equally; seasons averaged equally.
- Gain = v4 loss - v5 loss (positive = v5 better).
- Season bootstrap of whole paired seasons, 10,000 draws, seed 20261026; one-sided 90% lower bound.
- Calibration slopes and intercepts reported per cell.

## Forward check (2026 season, both models' archived live forecasts)
- At the first archived forecast after weeks 9 and 13 of 2026, score division and make-playoffs once the regular season ends. Both models' live forecasts are already saved at every refresh (forecast-archive).
- These include the live QB and pressure layers, so this is the only check of the full models.

## Gates (all must hold to promote v5)
1. Primary gain: one-sided 90% lower bound > 0 and better in at least 8 of 13 seasons.
2. Positive gain separately for division and for make-playoffs.
3. Positive primary gain in 2020-25 (an exposed subgroup).
4. No secondary cell worse than v4 by more than 0.003 mean log loss.
5. **Forward 2026:** v5's mean loss over the four live cells (two markets × weeks 9 and 13) no worse than v4's by more than 0.01. One season cannot confirm an improvement; this only guards against a clear live failure.

## Decision
- **Pass:** v5 becomes the displayed model from the 2027 pre-season, with v4 kept as an archived shadow. The 2026 live record of both stays published.
- **Fail:** v4 stays the displayed model for 2027; v5 stays a shadow. No change to the settings in response.
- A historical pass is not a profit claim. The betting number changes only with the displayed model.

## Disclosed exposure
- v5's settings were chosen on replays covering 2013-2025, partly with the format bug.
- The corrected replay's v5like calibration slopes were inspected this week; its log-loss comparison with v4 has not been computed.
- v5's live weights were fitted on 2010-2025, which is why the replay uses walk-forward weights.

## Questions for review
1. Is promotion on historical gates plus a one-season non-regression check appropriate, or should promotion wait for two forward seasons?
2. Is it acceptable that the replay arms omit the QB, pressure and QB-prior layers, given that the forward check includes them?
3. Is the 0.003 secondary tolerance (wider than the 0.002 used earlier) reasonable for more cells?
4. Should the existing 3,000-simulation corrected rows be used, or a fresh 10,000-simulation run at weeks 4, 9 and 13 (as proposed)?
