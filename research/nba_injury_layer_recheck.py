"""Declared reanalysis of saved corrected-ID rows; no simulations or live writes."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def score(d):
    expected = {(year, checkpoint, team, variant) for year in range(2013, 2027)
                for checkpoint in (.2, .4, .6, .8) for team in d.team.unique()
                for variant in ('without', 'with')}
    observed = set(d[['season', 'check', 'team', 'variant']].itertuples(index=False, name=None))
    if len(d.team.unique()) != 30 or observed != expected or len(d) != len(expected):
        raise ValueError('Incomplete or duplicate paired predictions')
    if d.groupby('season').n_out.max().le(0).any():
        raise ValueError('A season has no matched injury episodes')
    frames = []
    for market in ('title', 'conf', 'playoff'):
        p = d['p_' + market].clip(.002, .998)
        y = d['y_' + market]
        loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        frames.append(d[['season', 'check', 'team', 'variant']].assign(market=market, loss=loss))
    losses = pd.concat(frames)
    scores = losses.groupby(['season', 'market', 'variant']).loss.mean().unstack('variant')
    gains = (scores['without'] - scores['with']).unstack('market')
    combined = gains.mean(axis=1)
    samples = np.random.default_rng(20261029).choice(combined.to_numpy(), size=(10000, len(combined))).mean(axis=1)
    interval90 = np.quantile(samples, [.05, .95]).tolist()
    interval95 = np.quantile(samples, [.025, .975]).tolist()
    market_gains = gains.mean()
    better_equal = int((combined >= 0).sum())
    gates = {'positive_mean_and_ci90': bool(combined.mean() > 0 and interval90[0] > 0),
             'no_market_worse_by_more_than_0_002': bool((market_gains >= -.002).all()),
             'at_least_60_percent_seasons': better_equal >= math.ceil(.6 * len(combined))}
    return {'kind': 'Known-data development reanalysis, not independent validation',
            'all_gates_pass': all(gates.values()), 'gates': gates,
            'combined_gain': float(combined.mean()), 'ci90': interval90,
            'better_or_equal_seasons': better_equal, 'required_seasons': math.ceil(.6 * len(combined)),
            'seasons': len(combined), 'per_market_gain': market_gains.to_dict(),
            'zero_market_deterioration': bool((market_gains >= 0).all()),
            'original_integrity_check': {'ci95': interval95, 'better_seasons': int((combined > 0).sum()),
                'original_gates_pass': bool(interval95[0] > 0 and (market_gains >= 0).all() and (combined > 0).sum() >= 10)},
            'live_futures_changed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rows', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    result = score(pd.read_csv(a.rows))
    result['saved_rows_sha256'] = hashlib.sha256(a.rows.read_bytes()).hexdigest()
    with a.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
