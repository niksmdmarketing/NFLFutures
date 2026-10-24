"""Local, independently identified coverage/fast-memory tools; never edits M2/M2b."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
import nba_minutes_test as M
import nba_props_live_core as C

MODEL_ID = 'fast-minutes-hl2-dev1'
COVERAGE_ID = 'roster-coverage-conditional-dev1'


def fast_inputs(targets, history):
    """Strictly prior appearances; same-tip duplicate candidates share state.

    History must include only observed past games at capture time in live use.
    This function additionally excludes current/future outcomes per target.
    """
    t = targets.copy()
    h = history.copy()
    h['tip'] = pd.to_datetime(h.tip, utc=True)
    t['tip'] = pd.to_datetime(t.tip, utc=True)
    h = h[h.minutes > 0].copy()
    if h.duplicated(['season', 'aid', 'tip']).any():
        raise ValueError('Ambiguous multiple appearances at one timestamp')
    if not np.isfinite(h.minutes.to_numpy(float)).all():
        raise ValueError('Non-finite minutes history')
    groups = {}
    for (s, a), x in h.groupby(['season', 'aid']):
        x = x.sort_values('tip')
        groups[(int(s), int(a))] = (x.tip.dt.as_unit('ns').astype('int64').to_numpy(),
            x.minutes.ewm(halflife=2, adjust=True).mean().to_numpy())
    # Cache once per target time, not once per team candidate.
    cache = {}
    means, counts = [], []
    for row in t.itertuples():
        key = (int(row.season), int(row.aid), row.tip)
        if key not in cache:
            g = groups.get(key[:2])
            n = 0 if g is None else int(np.searchsorted(g[0], row.tip.value, side='left'))
            value = float(g[1][n-1]) if n else np.nan
            cache[key] = (value, n)
        value, n = cache[key]
        means.append(value); counts.append(n)
    t['fast_n'] = counts
    t['fast_mean'] = means
    t['fast_used'] = (t.fast_n >= 3) & t.fast_mean.notna()
    t['fast_input'] = t.fast_mean.where(t.fast_used, t['ewm'].where(t['ewm'] > 0, 12.0))
    return t


def fast_mean_matrix(z):
    # Preserve the ORIGINAL newcomer indicator: filling an unseen player's mean
    # with 12 is not evidence that he has appeared. Only memory-valued columns move.
    x = C.x_mean2(z)
    x[:, 1] = z.fast_input
    x[:, 3] = z.vac_same1 * z.fast_input / 36
    x[:, 4] = z.vac_other1 * z.fast_input / 36
    return x


def _normal(z, params, matrix):
    mu = np.clip(matrix @ np.asarray(params['bm']), 1, 48)
    sd = C.sd_eval(params['sd'], mu)
    threshold = .6 * z.mu1.to_numpy()
    loc, scale = C._match(mu, sd, np.maximum(np.ceil(threshold), 1)-.5)
    k = np.arange(1, 54)[None, :]
    p = norm.cdf((k+.5-loc[:,None])/scale[:,None])-norm.cdf((k-.5-loc[:,None])/scale[:,None])
    p = np.where(k >= threshold[:,None], np.clip(p,1e-12,None), 0)
    total=p.sum(1,keepdims=True)
    p=p/np.where(total>0,total,1)
    p[total[:,0]<=0,-1]=1
    return p


def fast_minutes(z, frozen, candidate):
    """Change only normal-night mean/spread; original short component retained."""
    if candidate['model_id'] != MODEL_ID:
        raise ValueError('Wrong challenger identity')
    q, pi = C.q_m2(z, frozen['m2'], True)
    f = copy.deepcopy(frozen['m2'])
    f.update(bm=candidate['bm'], sd=candidate['sd'])
    baseline_normal = _normal(z, frozen['m2'], C.x_mean2(z))
    new_normal = _normal(z, f, fast_mean_matrix(z))
    new = q + (1-pi[:,None])*(new_normal-baseline_normal)
    new = np.maximum(new,0)
    threshold = .6 * z.mu1.to_numpy()
    short = np.arange(1, 54)[None, :] < threshold[:, None]
    if not np.allclose(q[short], new[short], atol=1e-12, rtol=0):
        raise ValueError('Short-night probabilities changed')
    if not np.isfinite(new).all() or (new < 0).any() or not np.allclose(new.sum(1), 1):
        raise ValueError('Invalid minutes PMF')
    return new


def fallback_x(z):
    pm = z.prev_mpg.fillna(0).to_numpy(float)
    return np.column_stack([np.ones(len(z)), z.prev_mpg.notna().astype(float), pm, (z.gi < 3).astype(float)])


def fit_conditional_fallback(rows, season):
    """Box-selected appearances only: NEVER estimates probability of appearing."""
    x = rows[(rows.season < season) & (rows.season >= 2017) & (rows.fallback == 1) & (rows.minutes > 0)]
    if len(x) < 100:
        raise ValueError('Insufficient prior fallback appearances')
    b = np.linalg.lstsq(fallback_x(x), x.minutes.to_numpy(float), rcond=None)[0]
    mu = np.clip(fallback_x(x) @ b, 1, 48)
    sd = C.sd_coef(mu, x.minutes.to_numpy(float))
    return dict(model_id=COVERAGE_ID, season=int(season), fit_rows=len(x),
                bm=b.tolist(), sd=sd, baseline_mean=float(x.minutes.mean()),
                baseline_sd=float(x.minutes.std(ddof=0)),
                appearance_probability_validated=False,
                limitation='Outcome-box-selected cohort; conditional minutes evidence only')


def conditional_fallback(z, params):
    mu = np.clip(fallback_x(z) @ np.asarray(params['bm']), 1, 48)
    return M.disc_normal(mu, C.sd_eval(params['sd'], mu))


def coverage_sidecar(forecast, roster, history, params, roster_available_by_utc):
    """Account for every known roster ID, without inventing P(appear)/props.

    Roster columns: team, aid, name. History: season, aid, tip, minutes.
    No names-only joins or final-box candidate selection.
    """
    cutoff = pd.Timestamp(forecast['cutoff_utc'])
    if cutoff.tzinfo is None:
        raise ValueError('Cutoff lacks timezone')
    retrieved = pd.Timestamp(roster_available_by_utc)
    if retrieved.tzinfo is None or retrieved > cutoff:
        raise ValueError('Roster not known before cutoff')
    ros = roster.copy()
    if ros.aid.isna().any() or ros.duplicated('aid').any():
        raise ValueError('Ambiguous roster identity')
    if any(int(a) != a or int(a) <= 0 for a in ros.aid):
        raise ValueError('Invalid roster ID')
    if int(params['season']) != int(forecast['season']):
        raise ValueError('Wrong fallback season')
    h = history.copy()
    h['tip'] = pd.to_datetime(h.tip, utc=True)
    if h.tip.isna().any() or not np.isfinite(h.minutes.to_numpy(float)).all():
        raise ValueError('Invalid history timestamp or minutes')
    h = h[(h.tip < cutoff) & (h.minutes > 0)]
    if h.duplicated(['season', 'aid', 'tip']).any():
        raise ValueError('Ambiguous history')
    existing = {(p['team'], int(p['aid'])) for p in forecast['players']}
    extras = []
    for row in ros.itertuples():
        if (row.team, int(row.aid)) in existing:
            continue
        gi = forecast.get('team_games_played', {}).get(row.team)
        if gi is None or int(gi) != gi or gi < 0:
            raise ValueError('Known pre-game team game count is required')
        prior = h[(h.aid == row.aid) & (h.season == int(forecast['season']) - 1)]
        z = pd.DataFrame([dict(prev_mpg=float(prior.minutes.mean()) if len(prior) else np.nan,
                               gi=gi)])
        q = conditional_fallback(z, params)[0]
        extras.append(dict(aid=int(row.aid), team=row.team, name=row.name,
                           reason='not_in_frozen_candidate_population',
                           history_source='previous_season' if len(prior) else 'pooled_unseen_prior',
                           p_appear=None, unconditional_props=None,
                           conditional_minutes=q.tolist(),
                           conditional_expected_minutes=float(q @ np.arange(1, 54)),
                           status='experimental_conditional_only_not_market_ready'))
    counts = {}
    for team, group in ros.groupby('team'):
        ids = set(group.aid.astype(int))
        main = {a for t, a in existing if t == team} & ids
        ext = {p['aid'] for p in extras if p['team'] == team}
        assert not main & ext and main | ext == ids
        counts[team] = dict(roster=len(ids), primary=len(main), extension=len(ext))
    return dict(model_id=COVERAGE_ID, game_id=forecast['game_id'], cutoff_utc=str(cutoff),
                roster_available_by_utc=str(retrieved), primary_unchanged=True,
                eligible_for_primary_test=False, coverage=counts, players=extras,
                warning='Coverage accounting is complete; validated unconditional forecasts are not.')


def write_immutable(path, record):
    b = json.dumps(record, sort_keys=True, allow_nan=False).encode()
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(b)
    return hashlib.sha256(b).hexdigest()
