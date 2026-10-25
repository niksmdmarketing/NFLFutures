# NFL live team-volume input alignment audit — 26 October 2026 Sydney

Written before the paired replay. The frozen NFL and NBA models, parameter files, live forecast path, archive, website and workflows must remain unchanged. This is a local historical challenger audit only; no adoption or prospective archive write is authorized by this rule.

## Question

The live team-state join appears to attach a team's own pass attempts to its `allowed` field, and the forecast reads that same team's `allowed` value for `opp_att`. The historical training definition uses the opponent team's lagged `allowed` value. Test this single feature correction. Keep every other feature and parameter fixed within each paired comparison.

## Data and chronology

Use the already-built, strictly lagged `teams.parquet` from the NFL foundation run, seasons 2021–2025. Outcomes are `actual_team_att`; each game/team row is scored exactly once. The underlying data vintage is revised current nflverse data, and the original foundation audit notes this as a historical-vintage limitation. Do not rebuild or alter that foundation.

For the primary diagnostic, fit a fresh Poisson log-link team-attempt mean model and negative-binomial dispersion on seasons 2018 through year-1, using the historical aligned feature definitions. Neutralize `own_pass_off`, `opp_pass_def`, and `elo_gap` to the frozen model's training means for both train and test rows, because the live feed imputes those unavailable inputs at those same means. Predict each held-out row twice: (A) corrected opponent `allowed` (`opp_att` as stored in the historical panel), and (B) the observed live join's behavior (`opp_att = own_att`). All other inputs are identical. Do not refit or tune between the paired predictions.

Also report a separate frozen-parameter replay using the unchanged `model/nfl_player_props_v1.json` parameters, clearly labelled descriptive because those parameters were trained through 2025 and therefore are not an independent historical validation.

## Scores and decision

Primary score: discrete team-attempt RPS on the full negative-binomial PMF, support 0–100 with tail mass retained. Secondary diagnostics: log score, mean error, randomised PIT deciles, and results for each season. Report paired RPS gain (live-join score minus corrected score), relative RPS reduction, and a five-season cluster bootstrap 95% lower bound using seed 20261023.

This audit can establish that the correction improves historical distribution forecasts under the stated replay. It cannot establish market edge, prospective gain, or a reason to change a frozen model. A forward challenger may be created only after a separate user-approved implementation decision and must remain alongside the frozen baseline.

## Integrity

Read only the frozen foundation inputs and model parameters. Save rule copy, SHA-256 hashes, paired row scores and report to a new create-only output folder. Fail if the output folder exists or any protected input hash changes. No odds or market data.
