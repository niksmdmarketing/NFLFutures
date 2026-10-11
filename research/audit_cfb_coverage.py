"""Read-only comparison of completed schedules with advanced archives and summary denominators."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import cfb_site as C


def audit(year):
    def read(kind):
        return pd.read_csv(C.CACHE / f'{C.FILES[kind][1]}_{year}.csv', low_memory=False)
    refs, schedule, summary, advanced = [read(k) for k in ['teams', 'schedule', 'summary', 'advanced']]
    fbs = C.fbs_ids(refs)
    names = {C.key(r.team_id): r.display_name for r in refs.itertuples()}
    games = C.game_rows(schedule, fbs, names)
    advanced['team_id'] = advanced.pos_team_id.map(C.key)
    advanced['gid'] = advanced.game_id.map(C.key)
    joined = games.merge(advanced[['team_id', 'gid']].assign(covered=True), on=['team_id', 'gid'], how='left', validate='one_to_one')
    summary['team_id'] = summary.team_id.map(C.key)
    counts = games.groupby('team_id').gid.nunique().rename('record_gp').to_frame()
    counts['archive_gp'] = joined[joined.covered.eq(True)].groupby('team_id').gid.nunique()
    counts = counts.fillna(0).join(summary.set_index('team_id')[['playsgame_off_n', 'plays_off', 'playsgame_off']])
    final = schedule[schedule.status.eq('STATUS_FINAL')].copy()
    fbs_game_ids = set(final.loc[final.home_id.map(C.key).isin(fbs) & final.away_id.map(C.key).isin(fbs), 'game_id'].map(C.key))
    counts['fbs_covered_gp'] = joined[joined.covered.eq(True) & joined.gid.isin(fbs_game_ids)].groupby('team_id').gid.nunique()
    counts['fbs_covered_gp'] = counts.fbs_covered_gp.fillna(0)
    missing = joined[~joined.covered.eq(True)]
    summary_sets = []
    for t in counts.index:
        n = counts.loc[t, 'playsgame_off_n']
        summary_sets.append({'team': names[t], 'record_gp': int(counts.loc[t, 'record_gp']), 'archive_gp': int(counts.loc[t, 'archive_gp']), 'summary_gp': int(n) if pd.notna(n) else None})
    return {'season': year, 'teams': len(counts), 'record_vs_summary_mismatches': int(counts.record_gp.ne(counts.playsgame_off_n).sum()),
            'record_vs_archive_mismatches': int(counts.record_gp.ne(counts.archive_gp).sum()),
            'archive_vs_summary_mismatches': int(counts.archive_gp.ne(counts.playsgame_off_n).sum()),
            'covered_fbs_vs_fbs_vs_summary_mismatches': int(counts.fbs_covered_gp.ne(counts.playsgame_off_n).sum()),
            'summary_games': int(counts.playsgame_off_n.sum()),
            'covered_non_fbs_opponent_team_games': int((joined.covered.eq(True) & ~joined.gid.isin(fbs_game_ids)).sum()),
            'team_games': len(games), 'covered_team_games': int(joined.covered.eq(True).sum()), 'uncovered_team_games': len(missing),
            'missing_examples': missing[['gid', 'team', 'opp', 'phase']].head(8).to_dict('records'),
            'denominator_identity_max_error': float((counts.plays_off / counts.playsgame_off_n - counts.playsgame_off).abs().max()),
            'teams_sample': summary_sets[:8]}


if __name__ == '__main__':
    print(json.dumps([audit(y) for y in [2025, 2026]], indent=2))
