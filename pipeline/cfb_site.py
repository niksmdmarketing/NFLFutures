"""FBS statistics from SportsDataverse season archives; no market prices or forecast model."""
import datetime as dt
import io
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import sportsite as S

ROOT = Path(S.ROOT)
CACHE = ROOT / 'data/cfb'
OUT = ROOT / 'build/cfb'
SITE = ROOT / 'site/cfb'
BASE = 'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/'
FILES = {'teams': ('espn_cfb_teams', 'cfb_teams'),
         'summary': ('espn_cfb_team_summaries', 'cfb_team_summaries'),
         'schedule': ('espn_cfb_schedules', 'cfb_schedule'),
         'passing': ('espn_cfb_passing', 'cfb_passing'),
         'rushing': ('espn_cfb_rushing', 'cfb_rushing'),
         'receiving': ('espn_cfb_receiving', 'cfb_receiving'),
         'box': ('espn_cfb_team_box', 'team_box'),
         'advanced': ('espn_cfb_adv_team', 'adv_team'),
         'situational': ('espn_cfb_adv_situational', 'adv_situational')}


def validate(df, year):
    if df.empty or 'season' not in df or not pd.to_numeric(df.season, errors='coerce').eq(year).all():
        raise ValueError(f'Empty or wrong-season archive for {year}')


def fetch(kind, year, current):
    CACHE.mkdir(parents=True, exist_ok=True)
    tag, stem = FILES[kind]
    path = CACHE / f'{stem}_{year}.csv'
    age = 2 if year == current else 24 * 365
    fresh = path.exists() and time.time() - path.stat().st_mtime < age * 3600
    state = {'url': BASE + tag + '/' + path.name, 'warning': None}
    if not fresh:
        try:
            req = urllib.request.Request(state['url'], headers={'User-Agent': 'NFLFutures-CFB-statistics/1.0'})
            with urllib.request.urlopen(req, timeout=75) as response:
                raw = response.read()
            df = pd.read_csv(io.BytesIO(raw), low_memory=False)
            validate(df, year)
            tmp = path.with_suffix('.part')
            tmp.write_bytes(raw)
            tmp.replace(path)
        except Exception as exc:
            state['warning'] = f'{type(exc).__name__}: {exc}'
            if not path.exists():
                state.update(rows=0, checked_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                return pd.DataFrame(), state
    df = pd.read_csv(path, low_memory=False)
    validate(df, year)
    state.update(rows=len(df), checked_utc=dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat())
    return df, state


def key(v):
    return str(int(float(v)))


def fbs_ids(refs):
    """Season membership, explicitly excluding the archive's all-star/exhibition squads."""
    yes = lambda s: s.astype(str).str.lower().eq('true')
    return set(refs.loc[yes(refs.is_fbs) & ~yes(refs.is_all_star) & ~yes(refs.is_exhibition), 'team_id'].map(key))


def col(k, label=None, group='Efficiency', percent=False, lower=False):
    label = label or re.sub(r'[_\.]+', ' ', k).strip().title().replace('Epa', 'EPA')
    return S.C(k, label, group, 'pct' if percent else 'num2', lower, label)


METRICS = {'EPAplay': 'EPA/play', 'success': 'Success rate', 'explosive': 'Explosive rate',
           'yardsplay': 'Yards/play', 'play_stuffed': 'Stuff rate', 'havoc': 'Havoc rate',
           'red_zone_success': 'Red-zone success', 'third_down_success': '3rd-down success',
           'early_down_EPA': 'Early-down EPA/play', 'line_yards': 'Line yards',
           'opportunity_rate': 'Opportunity rate', 'playsgame': 'Plays/game',
           'EPAdrive': 'EPA/drive', 'yardsdrive': 'Yards/drive', 'playsdrive': 'Plays/drive',
           'pts_per_drive': 'Points/drive', 'pts_per_opp': 'Points/scoring opportunity',
           'available_yards_pct': 'Available yards gained', 'passrate': 'Pass rate',
           'turnovers': 'Turnovers', 'yardsgame': 'Yards/game'}
RATES = {'success', 'explosive', 'play_stuffed', 'havoc', 'red_zone_success', 'third_down_success',
         'opportunity_rate', 'available_yards_pct', 'passrate'}


def team_columns():
    cols = [S.C('gp', 'GP', 'Record', 'int'), S.C('playsgame_off_n', 'Advanced GP', 'Record', 'int', t='Source count of games contributing to offensive plays/game; can be smaller than record GP.'), S.C('wins', 'W', 'Record', 'int'),
            S.C('losses', 'L', 'Record', 'int'), col('wp', 'Win %', 'Record', True),
            col('pf_g', 'Points for/game', 'Record'), col('pa_g', 'Points allowed/game', 'Record', lower=True),
            col('margin_g', 'Margin/game', 'Record'), S.C('conference', 'Conference', 'Record', 'text')]
    for suffix, title in [('off', 'Offense'), ('def', 'Defense'), ('off_pass', 'Passing offense'),
                          ('def_pass', 'Passing defense'), ('off_rush', 'Rushing offense'), ('def_rush', 'Rushing defense')]:
        for metric, label in METRICS.items():
            cols.append(col(metric + '_' + suffix, ('Def ' if suffix.startswith('def') else 'Off ') + label, title, metric in RATES, suffix.startswith('def') and metric not in {'havoc', 'play_stuffed', 'turnovers'}))
    for k, label in {'adj_off_epa': 'Adjusted offensive EPA', 'adj_def_epa': 'Adjusted defensive EPA',
                     'net_adj_epa': 'Adjusted net EPA', 'off_strength_faced': 'Offense strength faced',
                     'def_strength_faced': 'Defense strength faced', 'deserved_wins': 'Deserved wins (source)',
                     'luck_wins': 'Win luck (source)', 'turnover_luck': 'Turnover luck',
                     'expected_turnover_margin': 'Expected turnover margin', 'EPAplay_margin': 'Net EPA/play',
                     'success_margin': 'Success differential', 'havoc_margin': 'Havoc differential'}.items():
        cols.append(col(k, label, 'Adjusted & differentials', lower=k == 'adj_def_epa'))
    return cols


PLAYER_METRICS = {'games': ('GP', False), 'plays': ('Plays', False), 'TEPA': ('Total EPA', False),
                  'EPAplay': ('EPA/play', False), 'success': ('Success rate', True), 'yards': ('Yards', False),
                  'yardsgame': ('Yards/game', False), 'yardsplay': ('Yards/play', False), 'EPAgame': ('EPA/game', False),
                  'comp': ('Completions / receptions', False), 'att': ('Pass attempts', False),
                  'comppct': ('Completion %', True), 'targets': ('Targets', False), 'catchpct': ('Catch %', True),
                  'passing_td': ('Passing / receiving TD', False), 'rushing_td': ('Rushing TD', False),
                  'pass_int': ('Interceptions', False), 'sacked': ('Times sacked', False),
                  'yardsdropback': ('Yards/dropback', False), 'fumbles': ('Fumbles', False),
                  'stuff_rate': ('Stuff rate', True), 'EPAplay_sd': ('Game EPA/play SD', False),
                  'EPAplay_p10': ('Game EPA/play 10th percentile', False), 'EPAplay_p90': ('Game EPA/play 90th percentile', False),
                  'dispersion_games': ('Games in variation sample', False)}


def game_rows(schedule, fbs, names):
    rows = []
    for r in schedule.to_dict('records'):
        # Source schedule archive is completed games only in some seasons. Never infer completion from a zero score.
        if str(r.get('status', '')).upper() not in {'STATUS_FINAL', 'FINAL', 'COMPLETED'}:
            continue
        for side, opposite in [('home', 'away'), ('away', 'home')]:
            t = key(r[side + '_id'])
            if t not in fbs:
                continue
            pf, pa = r.get(side + '_score'), r.get(opposite + '_score')
            if pd.isna(pf) or pd.isna(pa):
                continue
            rows.append({'gid': key(r['game_id']), 'date': str(r['game_date'])[:10], 'rnd': r.get('week'),
                         'team': names[t], 'opp': names.get(key(r[opposite + '_id']), r.get(opposite + '_team')),
                         'ha': 'N' if r.get('neutral_site') is True else ('H' if side == 'home' else 'A'),
                         'res': 'W' if pf > pa else 'L' if pf < pa else 'D', 'pf': pf, 'pa': pa,
                         'margin': pf-pa, 'team_id': t, 'phase': 'Postseason' if r.get('season_type') == 3 else 'Regular season'})
    return pd.DataFrame(rows)


def build_data(years=None):
    today = dt.date.today()
    current = today.year - (today.month < 7)
    years = list(years or range(current - 11, current + 1))
    coverage, names_all, groups, seasons = {}, {}, {}, []
    for y in years:
        frames, report = {}, {}
        for kind in FILES:
            frames[kind], report[kind] = fetch(kind, y, current)
        coverage[str(y)] = report
        refs = frames['teams']
        if refs.empty or frames['schedule'].empty:
            S.log('CFB missing reference/schedule', y)
            continue
        names = {key(r.team_id): r.display_name for r in refs.itertuples()}
        fbs = fbs_ids(refs)
        names_all.update({names[t]: names[t] for t in fbs})
        conf = {key(r.team_id): r.conference_name for r in refs.itertuples() if key(r.team_id) in fbs}
        groups[str(y)] = {}
        for t in fbs:
            groups[str(y)].setdefault(str(conf[t]) if pd.notna(conf[t]) else 'Independent', []).append(names[t])
        games = game_rows(frames['schedule'], fbs, names)
        if games.empty:
            S.log('CFB no confirmed results', y)
            continue
        base = games.groupby('team_id').agg(gp=('gid', 'nunique'), pf_g=('pf', 'mean'), pa_g=('pa', 'mean'), margin_g=('margin', 'mean'))
        wins = games.assign(w=games.res.eq('W'), l=games.res.eq('L')).groupby('team_id')[['w', 'l']].sum()
        base = base.join(wins).rename(columns={'w': 'wins', 'l': 'losses'}).reset_index()
        base['wp'] = base.wins / base.gp
        summary = frames['summary']
        if not summary.empty:
            summary = summary.assign(team_id=summary.team_id.map(key))
            base = base.merge(summary.drop(columns=['conference'], errors='ignore'), on='team_id', how='left', validate='one_to_one').copy()
        base['team'] = base.team_id.map(names)
        base['name'] = base.team_id.map(conf).fillna('Independent')
        base['conference'] = base.team_id.map(conf)
        S.write_json(str(OUT), f'team_{y}.json', S.columnar(base, y, ['team', 'name'], team_columns()))
        players = []
        for role, name_col in [('passing', 'passer_player_name'), ('rushing', 'rusher_player_name'), ('receiving', 'receiver_player_name')]:
            p = frames[role].copy()
            if p.empty:
                continue
            p['team_id'] = p.team_id.map(key)
            p = p[p.team_id.isin(fbs)].copy()
            p['team'] = p.team_id.map(names)
            p['name'] = p[name_col] + ' · ' + role.title()
            p['pos'] = role.title()
            players.append(p)
        p = pd.concat(players, ignore_index=True) if players else pd.DataFrame(columns=['name', 'team', 'pos'])
        pcols = [col(k, label, 'Volume' if k in {'games', 'plays', 'yards', 'att', 'targets', 'passing_td', 'rushing_td'} else 'Efficiency & variation', rate,
                     k in {'pass_int', 'sacked', 'fumbles', 'stuff_rate'}) for k, (label, rate) in PLAYER_METRICS.items()]
        S.write_json(str(OUT), f'players_{y}.json', S.columnar(p, y, ['name', 'team', 'pos'], pcols))
        gcols = [col('pf', 'Points for', 'Result'), col('pa', 'Points against', 'Result', lower=True), col('margin', 'Margin', 'Result'), S.C('phase', 'Season phase', 'Result', 'text')]
        for kind, id_col in [('box', 'team_id'), ('advanced', 'pos_team_id'), ('situational', 'pos_team_id')]:
            d = frames[kind].copy()
            if d.empty:
                continue
            d['team_id'] = d[id_col].map(key)
            d['gid'] = d.game_id.map(key)
            # Use documented numeric stat fields; not identifiers, odds or raw metadata.
            cols = [c for c in d if c not in {'season', 'week', 'game_id', id_col, 'team_id', 'gid'} and pd.api.types.is_numeric_dtype(d[c]) and not pd.api.types.is_bool_dtype(d[c])]
            renamed = {c: kind + '_' + c for c in cols}
            games = games.merge(d[['team_id', 'gid'] + cols].rename(columns=renamed), on=['team_id', 'gid'], how='left', validate='one_to_one')
            for c in cols:
                label = re.sub(r'([a-z])([A-Z])', r'\1 \2', c)
                gcols.append(col(renamed[c], label=label.replace('_', ' ').replace('EPA', 'EPA ').strip(), group={'box': 'Box score', 'advanced': 'Advanced efficiency', 'situational': 'Situational'}[kind], percent=c.endswith('_rate')))
        S.write_json(str(OUT), f'games_{y}.json', S.columnar(games, y, ['date', 'rnd', 'team', 'opp', 'ha', 'res'], gcols))
        seasons.append(y)
        S.log('CFB', y, len(base), 'teams', len(p), 'player role rows', len(games), 'team games')
    if not seasons:
        raise RuntimeError('No CFB seasons built')
    cfg = {'sport': 'CFB', 'season_style': 'calendar', 'ids': {'team': ['team', 'name'], 'players': ['name', 'team', 'pos'], 'games': ['date', 'rnd', 'team', 'opp', 'ha', 'res']},
           'pinned': ['gp', 'playsgame_off_n'], 'team_sort': 'net_adj_epa', 'noshade': ['gp', 'playsgame_off_n', 'conference'],
            'key': {'teams': ['gp', 'playsgame_off_n', 'wins', 'wp', 'margin_g', 'net_adj_epa', 'EPAplay_off', 'EPAplay_def', 'success_off', 'success_def', 'explosive_off', 'havoc_def', 'pts_per_drive_off'],
                   'players': ['games', 'plays', 'yards', 'yardsgame', 'TEPA', 'EPAplay', 'success']},
           'standings': {'sort': 'wins', 'order': [['wp', 1], ['margin_g', 1]], 'cols': ['gp', 'wins', 'losses', 'wp', 'pf_g', 'pa_g', 'margin_g', 'net_adj_epa'], 'note': 'Descriptive FBS records including postseason; conference grouping uses that season’s membership. This is not an official conference tiebreak ranking. No playoff/championship probabilities have been fitted.'},
           'players': {'sort': 'TEPA', 'gp_key': 'games', 'min_default': 2, 'positions': [['', 'All roles'], ['Passing', 'Passing'], ['Rushing', 'Rushing'], ['Receiving', 'Receiving']], 'note': 'Each player has separate passing/rushing/receiving rows: filter role for like-for-like comparisons. Source play-derived totals can differ from official box totals. Missing values are not zero.'},
           'games': {'results': [['W', 'Wins'], ['L', 'Losses'], ['D', 'Draws']], 'pinned': ['pf', 'pa'], 'note': 'Confirmed results only; opponent may be FCS. Advanced coverage varies by game. Season phase is shown.'},
           'team_note': 'SportsDataverse play-derived season summaries include postseason where played. Adjusted EPA is the provider’s retrospective opponent adjustment, not a point-in-time forecast. Counts and source model definitions vary by metric; season-to-date does not imply every completed game has advanced data.'}
    latest_games = json.loads((OUT / f'games_{max(seasons)}.json').read_text())
    meta = {'season': max(seasons), 'seasons': sorted(seasons, reverse=True), 'po_seasons': [], 'in_progress': max(seasons) == current,
            'results_through': max(r[0] for r in latest_games['rows']),
            'updated_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'teams': names_all, 'cfg': cfg,
            'groupings': [{'name': 'League'}, {'name': 'Conference', 'groups': groups[str(max(seasons))], 'by_season': groups}],
            'source': 'SportsDataverse / ESPN-derived archives', 'coverage': coverage}
    S.write_json(str(OUT), 'meta.json', meta)
    S.write_json(str(OUT), 'coverage.json', coverage)


PAGES = [('index', 'Records', 'College football · FBS records', 'Season records, conference groups and efficiency context. Latest 12 seasons; college football is separate from NFL.'),
         ('teams', 'Team stats', 'FBS advanced team statistics', 'Offense, defense, passing, rushing, opponent-adjusted EPA and differentials. Select a stat group, sort any heading or compare year by year.'),
         ('players', 'Players', 'FBS player production', 'Passing, rushing and receiving production, EPA, success rates and game-to-game variation. Filter role, team and minimum games.'),
         ('games', 'Game logs', 'FBS game logs', 'Final scores, box statistics, advanced efficiency and situational performance for completed games.')]


def build_site():
    # Standalone previews use the same shared assets; full-site builds already have them.
    (ROOT / 'site/js').mkdir(parents=True, exist_ok=True)
    for source, target in [(ROOT / 'site_src/style.css', ROOT / 'site/style.css'),
                           (ROOT / 'site_src/js/common.js', ROOT / 'site/js/common.js')]:
        if not target.exists():
            shutil.copyfile(source, target)
    old = S.SPORTS
    try:
        S.SPORTS = old + [('CFB', 'cfb/')]
        S.build_pages(str(SITE), 'CFB', 'Stats', PAGES, str(OUT))
        coverage_page = S.page_html('CFB', 'Stats', [(s, label) for s, label, *_ in PAGES] + [('coverage', 'Data coverage')], 'coverage', 'College football data coverage', 'Actual source file ages, row counts and retrieval warnings. Retrieved does not mean the provider has included every recent game.', script='coverage.js')
        (SITE / 'coverage.html').write_text(coverage_page, encoding='utf-8')
        (SITE / 'coverage.js').write_text("""boot(async meta => {
          document.getElementById('stamp').textContent = meta.season + ' · results through ' + meta.results_through;
          const rows = Object.entries(meta.coverage).reverse().flatMap(([year, kinds]) => Object.entries(kinds).map(([kind, r]) =>
            '<tr><td>' + esc(year) + '</td><td>' + esc(kind) + '</td><td>' + esc(r.rows) + '</td><td>' + esc(new Date(r.checked_utc).toLocaleString()) + '</td><td>' + esc(r.warning || 'None') + '</td></tr>'));
          document.getElementById('app').innerHTML = '<div class="scroll"><table class="stbl"><thead><tr><th>Season</th><th>Dataset</th><th>Source rows (before FBS filtering)</th><th>File retrieved</th><th>Warning / last-good fallback</th></tr></thead><tbody>' + rows.join('') + '</tbody></table></div><p class="note">Current-season archives checked every two hours with the existing public pipeline. Historical archives cached for a year. Source coverage and publication lag are outside our control. No odds or raw download controls. Advanced summaries are retrospective, not point-in-time model inputs. Sources: SportsDataverse ESPN-derived archives; technical definitions in cfbfastR-cfb-data/DATASETS.md. CollegeFootballData authenticated feeds, recruiting, transfers, injury reports and championship forecasting are not included in this first release.</p>';
        });""", encoding='utf-8')
        for path in SITE.glob('*.html'):
            text = path.read_text(encoding='utf-8')
            if path.name != 'coverage.html':
                text = text.replace('</nav></header>', '<a href="coverage.html">Data coverage</a></nav></header>')
                text = text.replace('</body>', '<script src="freshness.js"></script></body>')
            path.write_text(text, encoding='utf-8')
        (SITE / 'freshness.js').write_text("""getJSON('meta.json').then(m => { const note=document.createElement('p'); note.className='note'; note.textContent='Confirmed results through '+m.results_through+'. Advanced archives may lag these results. See Data coverage for file ages. Records include postseason; advanced numbers are descriptive, not forecasts.'; document.getElementById('main').prepend(note); });""", encoding='utf-8')
    finally:
        S.SPORTS = old
    # Navigation-only addition; existing sport data/scripts and models stay unchanged.
    for path in (ROOT / 'site').rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        relative = os.path.relpath(SITE, path.parent).replace('\\', '/') + '/'
        text = re.sub(r'(<(?:div|nav)\b[^>]*class=["\'][^"\']*\bsportbar\b[^"\']*["\'][^>]*>)(.*?)(</(?:div|nav)>)',
                      lambda m: m[0] if re.search(r'>CFB</a>', m[2]) else m[1] + m[2] + f'<a href="{relative}">CFB</a>' + m[3], text, flags=re.S)
        path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    build_data()
    build_site()
