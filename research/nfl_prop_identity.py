"""Price-independent, fail-closed NFL fixture/player identity matching."""
from __future__ import annotations
import datetime as dt
import re
import unicodedata

SUFFIXES={'jr','sr','ii','iii','iv','v'}
POSITIONS={'pass_attempts':{'QB'},'receptions':{'WR','TE','RB','FB'}}
NAME_PAIRS=[('Gabriel Davis','Gabe Davis'),('Marquise Brown','Hollywood Brown'),
            ('Kenneth Walker III','Ken Walker III'),('Joshua Palmer','Josh Palmer'),
            ('Nathaniel Dell','Tank Dell'),('Chigoziem Okonkwo','Chig Okonkwo')]
TEAM_NAMES={
 'ARI':'Arizona Cardinals','ATL':'Atlanta Falcons','BAL':'Baltimore Ravens','BUF':'Buffalo Bills',
 'CAR':'Carolina Panthers','CHI':'Chicago Bears','CIN':'Cincinnati Bengals','CLE':'Cleveland Browns',
 'DAL':'Dallas Cowboys','DEN':'Denver Broncos','DET':'Detroit Lions','GB':'Green Bay Packers',
 'HOU':'Houston Texans','IND':'Indianapolis Colts','JAX':'Jacksonville Jaguars','KC':'Kansas City Chiefs',
 'LA':'Los Angeles Rams','LAC':'Los Angeles Chargers','LV':'Las Vegas Raiders','MIA':'Miami Dolphins',
 'MIN':'Minnesota Vikings','NE':'New England Patriots','NO':'New Orleans Saints','NYG':'New York Giants',
 'NYJ':'New York Jets','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers','SEA':'Seattle Seahawks',
 'SF':'San Francisco 49ers','TB':'Tampa Bay Buccaneers','TEN':'Tennessee Titans','WAS':'Washington Commanders'}

def normalize(name,drop_suffix=False):
    text=unicodedata.normalize('NFKD',str(name or ''))
    text=''.join(c for c in text if not unicodedata.combining(c)).casefold()
    if text.count(',')==1:
        left,right=text.split(',')
        if re.sub(r'[^a-z0-9]','',right) not in SUFFIXES:text=right+' '+left
    tokens=re.findall(r'[a-z0-9]+',text)
    if drop_suffix and tokens and tokens[-1] in SUFFIXES:tokens=tokens[:-1]
    return ''.join(tokens)

TEAM_MAP={normalize(v):k for k,v in TEAM_NAMES.items()}|{normalize(k):k for k in TEAM_NAMES}
TEAM_MAP.update({normalize(k):v for k,v in {'LAR':'LA','JAC':'JAX','WSH':'WAS','OAK':'LV','SD':'LAC','STL':'LA'}.items()})

def utc(value):
    t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('UTC/offset required')
    return t.astimezone(dt.timezone.utc)

def fixture(home,away,start,games):
    h,a=TEAM_MAP.get(normalize(home)),TEAM_MAP.get(normalize(away))
    if not h or not a:return {'status':'unknown_team','game_id':None}
    try:t=utc(start)
    except (ValueError,TypeError):return {'status':'invalid_time','game_id':None}
    hits=[g for g in games if g['home']==h and g['away']==a and abs((utc(g['kickoff_utc'])-t).total_seconds())<=900]
    return {'status':'matched' if len(hits)==1 else 'ambiguous_fixture' if hits else 'unmatched_fixture',
            'game_id':hits[0]['game_id'] if len(hits)==1 else None}

def player(name,stat,candidates,team=None,gsis_id=None,espn_id=None):
    """Candidates must already be scoped to a single pre-game fixture and horizon."""
    if stat not in POSITIONS:return {'status':'unsupported_stat','gsis_id':None,'espn_id':None}
    if not normalize(name) and not (gsis_id or espn_id):return {'status':'missing_name','gsis_id':None,'espn_id':None}
    pool=[r for r in candidates if r.get('stat')==stat and r.get('position') in POSITIONS[stat]]
    if team:
        code=TEAM_MAP.get(normalize(team))
        if code is None:return {'status':'unknown_team','gsis_id':None,'espn_id':None}
        pool=[r for r in pool if r.get('team')==code]
    def answer(hits,method):
        ids={r['gsis_id'] for r in hits}
        if len(ids)!=1:return {'status':'ambiguous' if ids else 'unmatched','gsis_id':None,'espn_id':None,'method':method}
        r=hits[0]
        return {'status':'matched','gsis_id':r['gsis_id'],'espn_id':r.get('espn_id') or None,'name':r['name'],'team':r['team'],'method':method}
    if gsis_id or espn_id:
        hits=[r for r in pool if (not gsis_id or str(r['gsis_id'])==str(gsis_id)) and (not espn_id or str(r.get('espn_id'))==str(espn_id))]
        if len({r['gsis_id'] for r in hits})!=1:return answer(hits,'provided_id')
        # A supplied ID must not override a contradictory full name.
        check=player(name,stat,pool,team=team) if normalize(name) else {'status':'matched','gsis_id':hits[0]['gsis_id']}
        if check.get('gsis_id')!=hits[0]['gsis_id']:return {'status':'id_name_conflict','gsis_id':None,'espn_id':None}
        return answer(hits,'provided_id')
    query=normalize(name)
    names=lambda r:[r['name']]+list(r.get('name_aliases') or [])
    hits=[r for r in pool if query in {normalize(n) for n in names(r)}]
    if hits:return answer(hits,'exact_normalized')
    for a,b in NAME_PAIRS:
        keys={normalize(a),normalize(b)}
        if query in keys:
            hits=[r for r in pool if keys.intersection(normalize(n) for n in names(r))]
            if hits:return answer(hits,'frozen_name_alias')
    query=normalize(name,True)
    def suffix(n):
        tokens=re.findall(r'[a-z0-9]+',str(n).casefold())
        return tokens[-1] if tokens and tokens[-1] in SUFFIXES else None
    requested_suffix=suffix(name)
    hits=[r for r in pool if any(query==normalize(n,True) and (not requested_suffix or not suffix(n) or requested_suffix==suffix(n)) for n in names(r))]
    return answer(hits,'unique_suffix_fallback')

def probabilities(pmf,line):
    """Count probabilities; never resolve a line inside the pooled upper tail."""
    import math
    if isinstance(line,bool) or not isinstance(line,(int,float)) or not math.isfinite(line) or line<0 or line>=len(pmf)-1:
        raise ValueError('Unsupported line or pooled-tail boundary')
    if any(not math.isfinite(p) or p<0 for p in pmf) or abs(sum(pmf)-1)>1e-8:
        raise ValueError('Invalid PMF')
    return {'over':sum(p for k,p in enumerate(pmf) if k>line),
            'under':sum(p for k,p in enumerate(pmf) if k<line),
            'push':sum(p for k,p in enumerate(pmf) if k==line)}
