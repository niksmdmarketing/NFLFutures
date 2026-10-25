"""End-to-end scenario checks, output validation and private handoff."""
import copy,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from conditional_build import DEST,OUT,now,sha
from conditional_project import project

def main():
    target=DEST/'VERIFIED_HANDOFF.json'
    if target.exists():raise FileExistsError(target)
    src=Path(__file__).parent;m=json.loads((DEST/'build_manifest_complete.json').read_text())
    assert sha(src/'CONDITIONAL_RULE.md')==m['rule_sha256']
    assert all(sha(src/n)==v for n,v in m['code_sha256'].items())
    model=json.loads((DEST/'model.json').read_text());a=json.loads((DEST/'assumptions_ready.json').read_text())
    roster=json.loads((DEST/'roster_model_features_ready.json').read_text());teams=pd.read_parquet(OUT/'teams.parquet')
    original=project(a,model,teams,roster)
    # Removing a player changes no other receiver's existing role or production.
    off=copy.deepcopy(a);t=off['games'][0]['teams'][0]
    selected=next(r for r in t['receivers'] if r.get('include_projection',True));removed_id=selected['aid'];selected['assumed_playing']=False
    without=project(off,model,teams,roster)
    baseplayers={p['aid']:p for p in original[0]['teams'][0]['players']}
    changed={p['aid']:p for p in without[0]['teams'][0]['players']}
    assert removed_id not in changed
    for aid,p in changed.items():np.testing.assert_allclose(p['pmf'],baseplayers[aid]['pmf'])
    # New named QB receives the starting-role distribution, not backup history.
    switched=copy.deepcopy(a);t=switched['games'][0]['teams'][0]
    alternative=next(q for q in t['qb_alternatives'] if q['aid']!=t['qb']['aid']);t['qb']={**alternative,'role':'explicit_assumed_starting_QB'}
    swapped=project(switched,model,teams,roster);q=swapped[0]['teams'][0]['players'][0]
    assert q['aid']==alternative['aid'];np.testing.assert_allclose(q['pmf'],original[0]['teams'][0]['players'][0]['pmf'])
    # A role assumption must not quietly change fitted catch ability.
    bad=copy.deepcopy(a);bad['games'][0]['teams'][0]['receivers'][0]['catch_probability']=.1234567
    try:project(bad,model,teams,roster)
    except ValueError:pass
    else:raise AssertionError('Fitted ability edit was accepted')
    latest=sorted((DEST/'runs').glob('*/projections.json'))[-1];output=json.loads(latest.read_text())
    n=0;review=0;qb=0
    for game in output['games']:
        for team in game['teams']:
            review+=len(team['role_review_needed']);receptions=0.
            for p in team['players']:
                pmf=np.array(p['pmf']);assert np.isfinite(pmf).all() and (pmf>=0).all() and np.isclose(pmf.sum(),1)
                assert abs(p['mean']-pmf@np.arange(len(pmf)))<1e-8
                assert abs(sum(p['illustrative_line'][k] for k in ['over','under','push'])-1)<1e-8
                assert 'offensive_involvement_probability' not in p
                if p['stat']=='receptions':receptions+=p['mean']
                else:qb+=1
                n+=1
            assert receptions<=team['expected_team_attempts']+1e-8
    summary=dict(games=len(output['games']),players=n,qb_projections=qb,reception_projections=n-qb,role_review_rows=review)
    readme=f'''# NFL conditional projection model — first working version

Built 24 October 2026 Sydney. Experimental and local; no site or live model changes.

## What you can use now

- QB pass-attempt projections, assuming the selected QB starts.
- Receptions, assuming each included player participates in the specified target role.
- Projected averages, medians, middle-80% ranges and full outcome probabilities.
- Over/under/push probabilities for a line you supply. Example lines in JSON are illustrative, not bookmaker quotes.
- Editable QB choices, receiver inclusion and target-share assumptions; abilities remain frozen.

The current output covers **{summary['games']} games, {qb} QB projections and {n-qb} reception projections**. Another {review} game/player roles need review before inclusion; these players are not marked injured or rated as zero ability.

**No injury or availability checks have been applied. Default lineups are assumptions and can include unavailable players. This does not demonstrate a betting edge.**

## Open these files

- Current readable projections: [{latest.parent.joinpath('PROJECTIONS.md').name}]({latest.parent.joinpath('PROJECTIONS.md').as_posix()})
- Full distributions: [{latest.name}]({latest.as_posix()})
- Editable assumptions: [assumptions_ready.json]({(DEST/'assumptions_ready.json').as_posix()})
- Frozen model parameters: [model.json]({(DEST/'model.json').as_posix()})

Use `assumptions_ready.json`, not the earlier raw seed `assumptions.json`. The ready file has default target shares normalised once so removing a receiver does not mechanically increase teammates' forecasts.

## Logic

Team pass volume comes from the existing independent team/opponent model. QB workload is learned from 3,221 historical first-identifiable-QB-dropback cases in 2020–2025, using their eventual full-game attempt shares. It therefore includes short workloads after the first QB appears, rather than guaranteeing that a starting QB finishes as the main passer. This proxy is not a verified official-starter archive, and has not independently established pregame accuracy.

Receiver target share describes opportunity; catch probability describes production. Their fitted parts remain separate. No new teammate-absence adjustment is used because that experiment failed. Disabling someone leaves an unallocated target bucket; deliberate redistribution requires explicit target-share edits.

In this version, two QBs on the same team get the same pooled starting-role distribution if separately assumed to start. That is intentional: backup workload no longer follows them into a starting-role scenario. QB-specific style/ability effects on team passing volume have not been validated and are not invented here.

Initial role estimates use recent team history. New receivers have a visible position-prior fallback but are excluded from default projections until a target-share assumption is supplied. The model does not claim their role is known. Default target shares are budgeted across included players, with a residual bucket; distributions remain individual marginals, not a joint possession simulator.

## Running scenarios

From the isolated source checkout, with the existing numerical dependencies available:

`python research/nfl_games_props/conditional_project.py --assumptions <your-assumptions.json>`

Optional line query:

`python research/nfl_games_props/conditional_project.py --player-id <GSIS-ID> --stat receptions --line 4.5`

Outputs go into new create-only folders under `runs/`; prior runs are never overwritten. Select a QB using an ID in that team's alternatives. For receivers, change `assumed_playing`, `include_projection` or `target_share_override`; do not change fitted `catch_probability` or `default_target_share`. New roles require an explicit share before inclusion. A role override can deliberately change the remaining budget; disabling alone never redistributes.

No DNP-zero mixture or settlement assumption is included. Probabilities are conditional on the supplied participation/role scenario. Integer lines report pushes separately. The QB distribution can still allow a short night after starting; it does not predict whether the player dresses or starts.

## Verification and status

24 unit tests pass. End-to-end checks verify PMF normalisation, probability sums, expected receiver totals below team attempts, selected-QB replacement, frozen catch ability, and unchanged teammate forecasts after disabling a receiver. Build hashes and prior artifacts are preserved. The fitted-data proxy is not a new historical accuracy result; prior conditional-role/depth pilot limitations still apply.

The current snapshot uses player inputs through {output['latest_completed_player_game']}. It is not independently forward-archived or market-validated. Game moneylines/spreads/totals and other props are not part of this tool. The live futures model and site remain untouched.

`CONDITIONAL_MODEL_CODE_ONLY.zip` contains source, rules and tests, not raw data or fitted outputs. Keep this output folder private. Next work can focus on checking these projections or additional prop types; automatic in/out selection is deliberately deferred.
'''
    (DEST/'README.md').write_text(readme,encoding='utf-8')
    package=DEST/'CONDITIONAL_MODEL_CODE_ONLY.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.iterdir()):
            if p.is_file() and p.suffix in ('.py','.md'):z.write(p,'research/nfl_games_props/'+p.name)
    result=dict(verified_at=now(),summary=summary,unit_tests_passed=24,scenario_checks_passed=True,
        probabilities_normalised=True,ability_and_role_separated=True,latest_run=str(latest.parent),
        model_sha256=sha(DEST/'model.json'),assumptions_sha256=sha(DEST/'assumptions_ready.json'),
        projection_sha256=sha(latest),code_package_sha256=sha(package),readme_sha256=sha(DEST/'README.md'),
        source_sha256={p.name:sha(p) for p in src.iterdir() if p.is_file() and p.suffix in ('.py','.md')},
        live_model_unchanged=True,published=False,market_edge_established=False)
    with target.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(readme=str(DEST/'README.md'),summary=summary,verified=True),indent=2))

if __name__=='__main__':main()
