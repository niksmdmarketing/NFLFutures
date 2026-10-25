"""Reusable local projections. Lineups are supplied assumptions, never news facts."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import core as C
from freeze import linear
from build import OUT
from conditional_build import DEST,now,sha
import conditional_engine as E

def project(assumptions,model,teams,roster_reference):
    if assumptions['model_id']!=model['model_id']:raise ValueError('Wrong assumption/model version')
    key={(r.game_id,r.team):i for i,r in enumerate(teams.itertuples())}
    means=np.clip(np.exp(linear(teams,model['volume'])),5,70)
    volumes=C.nb_pmf(means,model['volume_dispersion'],100)
    reference={(g['game_id'],t['team']):t for g in roster_reference['games'] for t in g['teams']}
    results=[]
    for game in assumptions['games']:
        if len(game['teams'])!=2 or len({t['team'] for t in game['teams']})!=2:raise ValueError('Need two distinct teams')
        item=dict(game_id=game['game_id'],kickoff_utc=game['kickoff_utc'],teams=[])
        for t in game['teams']:
            k=(game['game_id'],t['team'])
            if k not in key:raise ValueError('Unknown game/team')
            volume=volumes[key[k]];players=[];qb=t.get('qb')
            if k not in reference:raise ValueError('No frozen roster for game/team')
            ref=reference[k]
            alternatives={q['aid']:q['name'] for q in ref.get('qb_alternatives',[])}
            if qb:
                if qb['aid'] not in alternatives:raise ValueError('QB is not a listed roster alternative')
                players.append(dict(aid=qb['aid'],name=alternatives[qb['aid']],stat='pass_attempts',
                    role='ASSUMED starting QB; no confirmation or injury check',
                    conditional_on_participation=True,**E.describe(E.starting_qb(volume,model['starting_role']))))
            receiver_reference={r['aid']:r for r in ref['receivers']}
            if len(t['receivers'])!=len({r['aid'] for r in t['receivers']}):raise ValueError('Duplicate receiver IDs')
            controlled=[]
            for request in t['receivers']:
                if request['aid'] not in receiver_reference:raise ValueError('Receiver not in frozen team roster')
                fixed=receiver_reference[request['aid']]
                if request.get('catch_probability',fixed['catch_probability'])!=fixed['catch_probability']:
                    raise ValueError('Catch ability is frozen; edit target-share role instead')
                if request.get('default_target_share',fixed['default_target_share'])!=fixed['default_target_share']:
                    raise ValueError('Use target_share_override, not a changed fitted role input')
                if request.get('include_projection',fixed.get('include_projection',True)) and fixed['history_status'].startswith('POSITION_PRIOR') and request.get('target_share_override') is None:
                    raise ValueError('Specify a target-share assumption before enabling a new receiver role')
                controlled.append({**fixed,**{name:request[name] for name in ['include_projection','assumed_playing','target_share_override'] if name in request}})
            rows,budget=E.target_budget(controlled)
            for r in rows:
                p=E.receiving(volume,r['effective_target_share'],r['catch_probability'],model['receiving']['concentration'])
                players.append(dict(aid=r['aid'],name=r['name'],position=r['position'],stat='receptions',
                    conditional_on_participation=True,role_target_share=r['effective_target_share'],
                    production_catch_probability=r['catch_probability'],history_status=r['history_status'],
                    target_share_was_overridden=r['explicit_share'],**E.describe(p)))
            missing=[dict(aid=r['aid'],name=r['name'],reason='ROLE_NOT_ENABLED_NOT_INJURY_STATUS') for r in t['receivers'] if not r.get('include_projection',True)]
            item['teams'].append(dict(team=t['team'],expected_team_attempts=float(volume@np.arange(101)),
                target_budget=budget,players=players,role_review_needed=missing))
        results.append(item)
    return results

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--assumptions',type=Path,default=DEST/'assumptions_ready.json')
    cli.add_argument('--player-id');cli.add_argument('--line',type=float);cli.add_argument('--stat',choices=['pass_attempts','receptions'])
    args=cli.parse_args()
    modelpath=DEST/'model.json';model=json.loads(modelpath.read_text());assumptions=json.loads(args.assumptions.read_text())
    rosterpath=DEST/'roster_model_features_ready.json';roster=json.loads(rosterpath.read_text())
    teams=pd.read_parquet(OUT/'teams.parquet');games=project(assumptions,model,teams,roster)
    fingerprint=sha(args.assumptions);run=DEST/'runs'/f"{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')}_{fingerprint[:10]}"
    run.mkdir(parents=True,exist_ok=False)
    inputs=json.loads((OUT/'data_validation.json').read_text())
    output=dict(model_id=model['model_id'],created_at_utc=now(),model_sha256=sha(modelpath),assumptions_sha256=fingerprint,
        source_feature_sha256=sha(OUT/'teams.parquet'),roster_features_sha256=sha(rosterpath),latest_completed_player_game=inputs['latest_player_target_game'],
        experimental=True,automatic_injury_handling=False,independent_forward_eligible=False,market_edge_established=False,
        scope='Conditional QB pass attempts and receptions only. Not game lines or other player props.',games=games,limits=model['limits'])
    queries=[]
    if args.line is not None:
        if not args.player_id:raise ValueError('Supply a player ID for a line query')
        for g in games:
            for t in g['teams']:
                for p in t['players']:
                    if p['aid']==args.player_id and (args.stat is None or p['stat']==args.stat):
                        queries.append(dict(game_id=g['game_id'],team=t['team'],name=p['name'],stat=p['stat'],**E.line_probabilities(p['pmf'],args.line)))
        if not queries:raise ValueError('Player/stat not present in included projections')
    output['line_queries']=queries
    (run/'projections.json').write_text(json.dumps(output,indent=2))
    (run/'assumptions_used.json').write_text(json.dumps(assumptions,indent=2))
    parts=['# NFL conditional projections — experimental','',
        '**Assumptions, not confirmed lineups. No injuries or outs checked. These are not market-validated probabilities.**','',
        'QB attempts assume the named QB starts. Receptions assume the named player participates in the specified role. Early-exit variation is included in the pooled QB workload, but availability is not predicted.',
        '',f"Latest completed player-input game: {inputs['latest_player_target_game']}",'',
        'Role-review players are listed separately and are not called injured. Switching a QB does not change team passing volume. Disabled receivers do not automatically give their targets to teammates.','']
    for g in games:
        parts.extend([f"## {g['game_id']}",'',f"Kickoff UTC: {g['kickoff_utc']}",''])
        for t in g['teams']:
            parts.extend([f"### {t['team']}",'','| Team | Player | Stat | Projected average | Middle 80% range |','|---|---|---|---:|---|'])
            for p in sorted(t['players'],key=lambda p:(p['stat']!='pass_attempts',-p['mean'])):
                parts.append(f"| {t['team']} | {p['name']} | {p['stat']} | {p['mean']:.1f} | {p['interval80'][0]}–{p['interval80'][1]} |")
            parts.extend(['',f"{t['team']}: team attempts {t['expected_team_attempts']:.1f}; unallocated target share {100*t['target_budget']['unallocated_target_share']:.1f}%; {len(t['role_review_needed'])} players need a role assumption.",''])
    (run/'PROJECTIONS.md').write_text('\n'.join(parts),encoding='utf-8')
    print(json.dumps(dict(output=str(run),games=len(games),projected_players=sum(len(t['players']) for g in games for t in g['teams']),queries=queries),indent=2))

if __name__=='__main__':main()
