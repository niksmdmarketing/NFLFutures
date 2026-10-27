"""One pre-registered props game-script test: research/nfl_games_props/GAME_SCRIPT_RULE.md. No tuning, no deployment.
Candidate: team pass-attempt volume features + elo_gap^2. Usage: python game_script_test.py   (needs build.py outputs in OUT)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import core as C
from build import BASE, OUT, player_inputs
from conditional_audit import appearances, control_means, budget_rates, score_pmf, metrics, sha, KEY, RECEIVERS
from run import model, make_priors, app_model, logscore
from receiver_allocation_test import conditional_scales

DEST = BASE / 'outputs/nfl_game_script_20261027'
HERE = Path(__file__).resolve().parent
MATCHUP = BASE / 'outputs/nfl_matchup_20261026/paired_scores.parquet'
FEATS = {'baseline': C.VOLUME_FEATURES, 'quadratic': C.VOLUME_FEATURES + ['elo_gap2']}


def season_boot(gains, seed=20261027, draws=10000):
    g = np.asarray(gains, float)
    rng = np.random.default_rng(seed)
    return float(np.quantile(g[rng.integers(0, len(g), (draws, len(g)))].mean(1), .10))


def pit_deciles(p):
    return [float(x) for x in np.histogram(np.clip(p, 0, 1 - 1e-12), bins=10, range=(0, 1))[0] / len(p)]


def main():
    DEST.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    g = pd.read_parquet(OUT / 'games.parquet')
    teams = pd.read_parquet(OUT / 'teams.parquet')
    teams['elo_gap2'] = teams.elo_gap ** 2
    players = pd.read_parquet(OUT / 'players.parquet')
    st, sn, complete, _ = player_inputs(g)
    rh = appearances(st, sn, g)
    recv = players[players.position.isin(RECEIVERS) & players.season.between(2018, 2025)].copy().reset_index(drop=True)
    recv = recv.join(control_means(recv, rh, 'receptions', 2.))
    team_rows, rec_pieces, qb_rows, folds = [], [], [], {}
    for year in range(2021, 2026):
        tr = teams[teams.season.between(2018, year - 1) & teams.actual_team_att.gt(0)]
        te = teams[teams.season.eq(year)].reset_index(drop=True)
        vols, info = {}, {}
        for arm, F in FEATS.items():
            vm = model('volume').fit(tr[F], tr.actual_team_att)
            disp = C.fit_nb(tr.actual_team_att, np.clip(vm.predict(tr[F]), 5, 70))
            mu = np.clip(vm.predict(te[F]), 5, 70)
            vols[arm] = C.nb_pmf(mu, disp, 100)
            grid = np.linspace(-1.5, 1.5, 13)
            X = pd.DataFrame([tr[C.VOLUME_FEATURES].mean()] * len(grid))
            X['elo_gap'] = grid
            X['elo_gap2'] = grid ** 2
            info[arm] = dict(dispersion=float(disp), grid=[round(float(v), 2) for v in np.clip(vm.predict(X[F]), 5, 70)])
        # team-attempt scores (identical rows across arms)
        ok = te.actual_team_att.gt(0).to_numpy()
        y = te.actual_team_att.to_numpy()[ok].astype(int)
        u = np.random.default_rng(20261023 + year).random(ok.sum())
        absg = te.elo_gap.abs().to_numpy()[ok]
        cut_hi = float(tr.elo_gap.abs().quantile(2 / 3))
        q1, q2 = np.quantile(tr.elo_gap, [1 / 3, 2 / 3])
        signed = np.where(te.elo_gap.to_numpy()[ok] <= q1, 'underdog', np.where(te.elo_gap.to_numpy()[ok] >= q2, 'favourite', 'middle'))
        for arm in FEATS:
            p = vols[arm][ok]
            team_rows.append(pd.DataFrame(dict(season=year, game_id=te.game_id.to_numpy()[ok], team=te.team.to_numpy()[ok], arm=arm,
                                               rps=C.rps(p, y), log=logscore(p, y), pit=C.pit(p, y, u), mean=(p * np.arange(p.shape[1])).sum(1), y=y,
                                               top_abs=absg >= cut_hi, signed=signed)))
        # receptions (matchup test's baseline construction; only the volume differs)
        vid = {(r.game_id, r.team): i for i, r in enumerate(te.itertuples())}
        train = players[players.season.between(2018, year - 1) & players.app.notna() & players.actual_team_att.notna()]
        appearance = app_model(train)
        pri = make_priors(train)
        ra = train[train.position.isin(RECEIVERS) & train.app.eq(1)].reset_index(drop=True)
        conc = C.fit_concentration(ra.receptions, ra.actual_team_att, C.rates(ra, pri, 'receptions'))
        allz = recv[recv.season.eq(year)].copy().reset_index(drop=True)
        prob = np.clip(appearance.predict_proba(allz[C.APP_FEATURES])[:, 1], 1e-3, 1 - 1e-3)
        _, _, raw_target, catch = budget_rates(allz, pri)
        base_scale, _ = conditional_scales(allz, raw_target, prob)
        allz['base_rate'] = raw_target * base_scale * catch
        z = allz[allz.app.eq(1) & allz.actual_team_att.notna()].reset_index(drop=True)
        idx = np.array([vid[(r.game_id, r.team)] for r in z.itertuples()])
        rng = np.random.default_rng(20261023)
        for start in range(0, len(z), 500):
            x = z.iloc[start:start + 500]; sl = slice(start, start + len(x)); uu = rng.random(len(x))
            for arm in FEATS:
                rec_pieces.append(score_pmf(x, C.allocation_pmf(vols[arm][idx[sl]], x.base_rate.to_numpy(), conc, 40), arm, 'receptions', uu))
        # downstream QB pass attempts (descriptive): expected starters' share of team attempts, fitted on training QB rows
        qtr = train[(train.is_qb == 1) & train.app.eq(1) & train.actual_team_att.gt(0)]
        share = float((qtr.attempts / qtr.actual_team_att).clip(0, 1).mean())
        qconc = C.fit_concentration(qtr.attempts.clip(upper=qtr.actual_team_att), qtr.actual_team_att, np.full(len(qtr), share))
        qte = players[(players.season == year) & (players.is_qb == 1) & players.app.eq(1) & players.actual_team_att.notna()].reset_index(drop=True)
        qi = np.array([vid.get((r.game_id, r.team), -1) for r in qte.itertuples()])
        qte, qi = qte[qi >= 0].reset_index(drop=True), qi[qi >= 0]
        yq = qte.attempts.fillna(0).to_numpy().astype(int)
        for arm in FEATS:
            pq = C.allocation_pmf(vols[arm][qi], np.full(len(qte), share), qconc, 100)
            qb_rows.append(pd.DataFrame(dict(season=year, arm=arm, rps=C.rps(pq, yq), log=logscore(pq, yq))))
        folds[str(year)] = dict(volume=info, top_abs_gap_cut=cut_hi, qb_share=share, qb_concentration=float(qconc), rows_team=int(ok.sum()), rows_receivers=len(z))
        print('fold', year, {a: info[a]['grid'] for a in FEATS}, flush=True)
    T = pd.concat(team_rows, ignore_index=True)
    R = pd.concat(rec_pieces, ignore_index=True)
    Q = pd.concat(qb_rows, ignore_index=True)
    T.to_parquet(DEST / 'team_scores.parquet', index=False)
    R.to_parquet(DEST / 'receptions_scores.parquet', index=False)
    # identity: baseline receptions scores = matchup test baseline rows
    ref = pd.read_parquet(MATCHUP)
    ref = ref[ref.model.eq('baseline')][KEY + ['rps']]
    b = R[R.model.eq('baseline')]
    m = b.merge(ref, on=KEY, suffixes=('', '_ref'))
    ident = dict(baseline_rows=len(b), reference_rows=len(ref), matched=len(m), max_abs_rps_diff=float(np.abs(m.rps - m.rps_ref).max()) if len(m) else None)
    ident['ok'] = bool(len(m) == len(b) == len(ref) and ident['max_abs_rps_diff'] < 1e-9)
    print('identity', ident, flush=True)
    if not ident['ok']:
        (DEST / 'results.json').write_text(json.dumps(dict(identity=ident, stopped=True), indent=2))
        return
    seasons = list(range(2021, 2026))
    sm = T.groupby(['season', 'arm']).rps.mean().unstack()
    gains = (sm['baseline'] - sm['quadratic']).loc[seasons].to_numpy()
    agg = float(gains.mean())
    lower = season_boot(gains)
    loso = {str(s): float(np.delete(gains, i).mean()) for i, s in enumerate(seasons)}
    tb, tq = T[T.arm.eq('baseline')], T[T.arm.eq('quadratic')]
    pit = {a: pit_deciles(T[T.arm.eq(a)].pit) for a in FEATS}
    top = {a: float(T[T.arm.eq(a) & T.top_abs].rps.mean()) for a in FEATS}
    signed = {s: {a: float(T[T.arm.eq(a) & T.signed.eq(s)].rps.mean()) for a in FEATS} for s in ('underdog', 'middle', 'favourite')}
    by_season_pit = {str(s): {a: pit_deciles(T[T.arm.eq(a) & T.season.eq(s)].pit) for a in FEATS} | dict(n=int((tb.season == s).sum())) for s in seasons}
    rb, rq = metrics(R[R.model.eq('baseline')]), metrics(R[R.model.eq('quadratic')])
    rec_rel = float(rq['rps'] / rb['rps'] - 1)
    gates = {'1_team_rps_gain_lower90_and_4of5': bool(agg > 0 and lower > 0 and (gains > 0).sum() >= 4),
             '2_team_log_not_worse': bool(tq.log.mean() <= tb.log.mean()),
             '3_pooled_pit_0.07_0.13': bool(all(.07 <= v <= .13 for v in pit['quadratic'])),
             '4_receptions_rps_not_0.1pct_worse_and_log_not_worse': bool(rec_rel <= .001 and rq['log_score'] <= rb['log_score']),
             '5_top_abs_gap_tercile_not_worse': bool(top['quadratic'] <= top['baseline'])}
    res = dict(rule='research/nfl_games_props/GAME_SCRIPT_RULE.md', started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               identity=ident, folds=folds,
               team=dict(season_gains={str(s): float(v) for s, v in zip(seasons, gains)}, aggregate_gain=agg, lower90=lower, seasons_better=int((gains > 0).sum()),
                         leave_one_out=loso, rps=dict(baseline=float(tb.rps.mean()), quadratic=float(tq.rps.mean())),
                         log=dict(baseline=float(tb.log.mean()), quadratic=float(tq.log.mean())),
                         mean_error=dict(baseline=float((tb['mean'] - tb.y).mean()), quadratic=float((tq['mean'] - tq.y).mean())),
                         pit_pooled=pit, pit_by_season=by_season_pit, top_abs_gap_tercile=top, signed_terciles=signed),
               receptions=dict(baseline=rb, quadratic=rq, relative_rps_change=rec_rel),
               qb_pass_attempts_descriptive={a: dict(rps=float(Q[Q.arm.eq(a)].rps.mean()), log=float(Q[Q.arm.eq(a)].log.mean()), n=int((Q.arm == a).sum())) for a in FEATS},
               gates=gates, passes=all(gates.values()), market_edge_established=False,
               inputs={n: sha(OUT / n) for n in ('games.parquet', 'teams.parquet', 'players.parquet')}, code_sha256=sha(__file__), rule_sha256=sha(HERE / 'GAME_SCRIPT_RULE.md'))
    (DEST / 'results.json').write_text(json.dumps(res, indent=2))
    (HERE / 'game_script_results.json').write_text(json.dumps(res, indent=2))
    print(json.dumps({k: res[k] for k in ('gates', 'passes')} | {'team': {k: res['team'][k] for k in ('season_gains', 'aggregate_gain', 'lower90', 'rps', 'log', 'top_abs_gap_tercile')},
                      'receptions_rel': rec_rel, 'qb': res['qb_pass_attempts_descriptive']}, indent=2))


if __name__ == '__main__':
    main()
