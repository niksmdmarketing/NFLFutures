"""Paired unchanged/corrected replays. All row-level output stays private."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import contextlib
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def worker(model, cache, output, variant):
    for key in list(os.environ):
        if key.startswith('AW_'):
            del os.environ[key]
    os.environ['AW_SIMS'] = '300'
    sys.path.insert(0, str(model / 'research'))
    sys.path.insert(0, str(model / 'pipeline'))
    import nba_awards_replay as replay
    import nba_award_sim as sim
    from nba_site import AM_norm
    from trends_awards import NBA_AW
    sim.DATA = str(cache)
    output.mkdir()
    original = sim.simulate
    counters = {}
    with gzip.open(output / 'candidate_probabilities.jsonl.gz', 'xt', encoding='utf-8') as detail:
        def capture(*args, **kwargs):
            pm = original(*args, **kwargs)
            award, year = args[3], int(args[7])
            key = (year, award)
            if kwargs.get('pre', False):
                checkpoint = -1
            else:
                checkpoint = counters.get(key, 0)
                counters[key] = checkpoint + 1
            detail.write(json.dumps({'season': year, 'award': award, 'ck': checkpoint,
                                     'winner': AM_norm(NBA_AW[award][year]), 'p': pm}) + '\n')
            return pm
        sim.simulate = replay.simulate = capture
        with (output / 'progress.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
            result = replay.replay(2010, 2026)
        result.to_csv(output / 'replay.csv', index=False)
    record = {'variant': variant,
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=model, text=True).strip(),
              'rows': len(result), 'seasons': sorted(int(x) for x in result.season.unique()),
              'simulations': sim.SIMS,
              'source_hashes': {p: hashlib.sha256((model / p).read_bytes()).hexdigest()
                                for p in ('pipeline/nba_award_sim.py', 'research/nba_awards_replay.py', 'pipeline/award_model.py')}}
    (output / 'manifest.json').write_text(json.dumps(record, indent=2))
    return record


def summarize(output):
    import numpy as np
    import pandas as pd
    def read(variant):
        with gzip.open(output / variant / 'candidate_probabilities.jsonl.gz', 'rt', encoding='utf-8') as f:
            records = [json.loads(line) for line in f]
        return {(r['season'], r['award'], r['ck']): r for r in records}
    old, new = read('baseline'), read('fixed')
    if set(old) != set(new):
        raise ValueError('Unpaired race checkpoints')
    rows, bins = [], []
    edges = np.array([0, .05, .1, .2, .4, .6, .8, 1.0000001])
    for key in sorted(old):
        a, b = old[key], new[key]
        if a['winner'] != b['winner']:
            raise ValueError('Winner identity mismatch')
        winner = a['winner']
        union = set(a['p']) | set(b['p']) | {winner}
        for variant, r in [('baseline', a), ('fixed', b)]:
            probs = r['p']
            values = np.array([probs.get(name, 0.) for name in union], float)
            if not np.isfinite(values).all() or (values < 0).any() or (values > 1.000001).any():
                raise ValueError('Invalid probabilities')
            favourite = max(probs, key=probs.get) if probs else None
            pw = probs.get(winner, 0.)
            rows.append({'season': key[0], 'award': key[1], 'ck': key[2], 'variant': variant,
                         'nll': -np.log(max(pw, .002)),
                         'brier': sum(probs.get(n, 0.) ** 2 for n in union) - 2 * pw + 1,
                         'mass': sum(probs.values()), 'fav': max(probs.values()) if probs else 0.,
                         'fav_won': int(favourite == winner), 'winner_zero': int(pw == 0)})
            for name in union:
                prob = probs.get(name, 0.)
                bins.append({'award': key[1], 'variant': variant, 'bin': min(int(np.searchsorted(edges, prob, side='right') - 1), 6),
                             'prob': prob, 'actual': int(name == winner)})
    frame = pd.DataFrame(rows)
    frame.to_csv(output / 'paired_scores.csv.gz', index=False)
    result = {'seasons': list(range(2010, 2027)), 'simulations': 300, 'live_deployed': False,
              'metrics': {}, 'post_2024': {}, 'interpretation': 'Paired bug correction, not an untouched holdout or a profitability test'}
    for target, subset in [('metrics', frame[frame.ck >= 0]), ('post_2024', frame[(frame.ck >= 0) & (frame.season >= 2024)])]:
        for award, group in subset.groupby('award'):
            season = group.groupby(['season', 'variant']).nll.mean().unstack()
            gain = season.baseline - season.fixed
            samples = np.random.default_rng(20261104).choice(gain.to_numpy(), size=(10000, len(gain))).mean(axis=1)
            variants = {}
            for variant, q in group.groupby('variant'):
                variants[variant] = {'mean_winner_log_loss': float(q.nll.mean()), 'field_brier': float(q.brier.mean()),
                                     'mean_probability_mass': float(q.mass.mean()), 'mass_deficit_forecasts': int((q.mass < .999999).sum()),
                                     'favourite_confidence': float(q.fav.mean()), 'favourite_win_frequency': float(q.fav_won.mean()),
                                     'zero_probability_winners': int(q.winner_zero.sum()), 'checkpoints': len(q)}
            result[target][award] = {'variants': variants, 'equal_season_log_loss_gain': float(gain.mean()),
                                     'gain_ci90_season_bootstrap': np.quantile(samples, [.05, .95]).tolist(),
                                     'seasons_better': int((gain > 1e-12).sum()), 'seasons_equal': int((gain.abs() <= 1e-12).sum()),
                                     'season_gains': {str(y): float(v) for y, v in gain.items()}}
    reliability = pd.DataFrame(bins).groupby(['award', 'variant', 'bin']).agg(n=('prob', 'size'), predicted=('prob', 'mean'), actual=('actual', 'mean')).reset_index()
    result['descriptive_candidate_reliability'] = reliability.to_dict('records')
    (output / 'results.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--fixed', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    for var in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[var] = '1'
    a.output.mkdir(parents=True, exist_ok=False)
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, model.resolve(), a.inputs.resolve(), a.output.resolve() / variant, variant)
                   for model, variant in [(a.baseline, 'baseline'), (a.fixed, 'fixed')]]
        records = [f.result() for f in futures]
    (a.output / 'manifests.json').write_text(json.dumps(records, indent=2))
    result = summarize(a.output)
    print(json.dumps({'finished': True, 'metrics': {k: v['equal_season_log_loss_gain'] for k, v in result['metrics'].items()}}))
