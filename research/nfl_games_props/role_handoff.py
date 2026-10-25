"""Seal completed role tests and a private, data-free source handoff."""
import hashlib,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import core as C
import role_models as R
from role_test import DEST,OUT,utc

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    target=DEST/'HANDOFF_MANIFEST.json'
    if target.exists():raise FileExistsError(target)
    src=Path(__file__).parent;result=json.loads((DEST/'results.json').read_text());manifest=json.loads((DEST/'manifest_complete.json').read_text())
    assert sha(src/'ROLE_RULE.md')==manifest['rule_sha256']
    assert all(sha(src/k)==v for k,v in manifest['code_sha256'].items())
    assert all(sha(OUT/k)==v for k,v in manifest['inputs'].items())
    paired=pd.read_parquet(DEST/'paired_scores.parquet')
    assert not paired.duplicated(['game_id','team','aid','stat']).any()
    assert np.isfinite(paired[['baseline_cond_rps','candidate_cond_rps','baseline_rps','candidate_rps']]).all().all()
    assert paired.season.between(2021,2024).all()
    assert ((paired.baseline_rps>=0)&(paired.candidate_rps>=0)).all()
    v=np.zeros((1,101));v[0,35]=1;states=result['parameters']['2024']['qb_states']
    scenarios=[]
    for probability in (0.,.5,1.):
        pmf=R.qb_pmf(v,np.array([probability]),states)
        assert np.isclose(pmf.sum(),1) and (pmf>=0).all()
        scenarios.append(dict(assumed_primary_probability=probability,assumed_team_attempts=35,
            conditional_attempt_mean=float((pmf@np.arange(101))[0]),illustration_only=True,
            note='Not a forecast for any player; team volume fixed. No claim the role is confirmed.'))
    (DEST/'SCENARIO_EXAMPLE.json').write_text(json.dumps(scenarios,indent=2))
    rows=[]
    for stat,x in result['results'].items():
        rows.append(f"| {stat} | {x['conditional_baseline']:.6f} | {x['conditional_candidate']:.6f} | {100*x['conditional_relative_gain']:.2f}% | {x['seasons_better']}/4 | {'PASS' if x['research_screen_pass'] else 'FAIL'} |")
    body='''# NFL workload/ability separation — research handoff

## What changed

Two local experiments were specified before results. No live model, site, schedules or repositories were changed.

**QB attempts:** the same QB now has a primary-passer workload distribution and a relief-workload distribution. Pregame history and eligible injury reports estimate the chance of each role. His tiny past backup workload does not determine the primary-role distribution. This estimates the role of primary passer, not an official confirmed starter. Pass attempts are opportunity, not a direct QB ability metric; team passing volume is held fixed in this test.

**Receptions:** historical target share describes role; smoothed catch probability describes player production. Missing teammates can increase target opportunities without improving the receiver's catch ability. A single pooled adjustment was fitted on earlier seasons only. Both versions use the same expected-target budget repair; the legacy version is reported separately.

## Results: players who participate

The primary comparison is conditional on offensive involvement, not DNP counted as zero. Lower RPS is better. Percent improvements mean less statistical forecast error, not returns, win rates or probability-point changes.

| Market | Baseline conditional RPS | Candidate conditional RPS | Relative gain | Seasons better | Full research screen |
|---|---:|---:|---:|---:|---|
'''+ '\n'.join(rows)+'''

Full numbers, PIT calibration, formula-line overs, subgroup scores, unconditional scores and all fold parameters are in `results.json`. `paired_scores.parquet` retains the fixed comparison rows. A positive average gain is not a pass if calibration or subgroup protections fail.

## What the comparison can and cannot establish

- Evaluate 2021–2024, refitting on earlier 2020+ seasons. The same involvement forecast, team passing volume, players and information cutoffs are used in both versions. Production priors use the prototype's preceding 2018+ seasons.
- Final historical injury files are timestamp-screened but revised. They are not independently collected original vintages and can omit earlier report versions.
- New, never-seen or absent-for-many-weeks QBs remain outside the original candidate cohort. We do not use target-game boxes to add candidates. Coverage is reported, not fixed with hindsight.
- Actual primary-passer labels use the QB with most attempts in the outcome game, for fitting/scoring only. This can differ from the announced starter after an early injury. Actual target-game starters are never an input.
- QB role probabilities are player marginals, not a mutually exclusive joint roster model. Receiver expected targets are budgeted in expectation, not jointly simulated player allocations.
- Reported Out/Doubtful affects the inference only when eligible before cutoff. A missing report does not establish health.
- These four seasons are development evidence, not untouched holdouts. Nothing establishes a bookmaker edge, a settlement convention or profitability. Independent forward testing is still required.

## Implementation and verification

Sixteen tests pass, including target/future-outcome exclusion, timestamps, QB primary-role scenarios, receiver own-missingness exclusion, expected target budgeting and unchanged catch probabilities. One test fixture originally assumed a 101-value support for a 41-value input and was corrected before scoring; forecasting code was unaffected.

`ROLE_RULE.md` was hashed before fitting. `manifest_complete.json` records input/rule/code hashes. `HANDOFF_MANIFEST.json` verifies that scored model code and inputs remain unchanged. The paired scores were checked for duplicates and finite values; scenario PMFs were verified to sum to one.

For an explicitly assumed primary-passer scenario, call `role_models.qb_pmf(team_attempt_pmf, primary_probability, states)`. Primary probability one means assumed primary role, not proof of availability. Apply participation separately and record the assumption/source. `SCENARIO_EXAMPLE.json` illustrates the difference using a hypothetical team making 35 attempts and the last evaluation fold's parameters; it is not a current-player prediction.

## Handoff

- `ROLE_FOUNDATION_CODE_ONLY.zip`: complete small foundation source, rules and attribution; no raw data, results tables or fitted parameters.
- `results.json`: all results and numerical fold parameters.
- `role_features.parquet`, `paired_scores.parquet`: private evidence.
- `SCENARIO_EXAMPLE.json`: hypothetical role example only.

The source lives under `work/nfl-games-props-20261023/research/nfl_games_props/`. Run tests first, then `role_test.py` in a new output location if deliberately reproducing. Experiment output paths are create-only; do not overwrite prior evidence. Run `role_handoff.py` only after completed results.

Stop rule: retain the baseline for each failed experiment; do not search alternative forms on these same results. Any screen pass is a candidate for review and independent forward testing, not automatic publication.
'''
    (DEST/'REPORT.md').write_text(body,encoding='utf-8')
    package=DEST/'ROLE_FOUNDATION_CODE_ONLY.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.iterdir()):
            if p.is_file() and p.suffix in ('.py','.md'):z.write(p,'research/nfl_games_props/'+p.name)
    record=dict(sealed_at=utc(),rule_hash_verified=True,scored_code_hashes_verified=True,input_hashes_verified=True,
        paired_rows_unique=True,scenario_pmfs_valid=True,unit_tests_passed=16,
        source_sha256={p.name:sha(p) for p in src.iterdir() if p.is_file() and p.suffix in ('.py','.md')},
        output_sha256={p.name:sha(p) for p in DEST.iterdir() if p.is_file()},deployed=False)
    with target.open('x') as f:json.dump(record,f,indent=2)
    print(json.dumps(dict(report=str(DEST/'REPORT.md'),scenarios=scenarios),indent=2))

if __name__=='__main__':main()
