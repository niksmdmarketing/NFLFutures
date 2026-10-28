"""Current NBA awards before/after opt-in structural fixes. No shrinkage or performance replay."""
import argparse,datetime as dt,hashlib,json,os,subprocess,sys,math
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
import nba_site as SITE,nba as NBA,nba_award_sim as SIM


def published_identity(before,published):
    maximum=0.0
    for award in ('MVP','DPOY','ROY','6MOY'):
        a=before['awards'][award]['current'];b=published['awards'][award]['current']
        if len(a)!=len(b) or [r['name'] for r in a]!=[r['name'] for r in b]:raise ValueError('Before does not reproduce published candidate ranking')
        for x,y in zip(a,b):maximum=max(maximum,abs(float(x['prob'])-float(y['prob'])))
    if maximum>.000050001:raise ValueError('Before differs from published precision')
    return {'top15_names_identical':True,'maximum_probability_difference':maximum,'published_rounding_tolerance':.000050001}


def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if hasattr(value,'item'):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def compare(season,output,published_ref):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    # All external reads must already be cached; both evaluations use exactly this snapshot.
    def frozen_download(tag,name,*args,**kwargs):
        p=Path(NBA.NBA_DATA)/name
        if not p.exists():raise FileNotFoundError('Unfrozen required input: '+str(p))
        return str(p)
    NBA._download=frozen_download
    files=sorted(Path(NBA.NBA_DATA).glob('*.csv'))+[ROOT/'model/nba_overrides.json']
    files=[p for p in files if p.is_file()]
    manifest={'captured_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'season':season,'published_ref':published_ref,
              'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    published=json.loads(subprocess.check_output(['git','show',published_ref+':nba/data/awards.json'],cwd=ROOT))
    futures=subprocess.check_output(['git','show',published_ref+':nba/data/futures.json'],cwd=ROOT)
    # Preseason fallback reads this published team-win prior; neither evaluation builds a team model.
    SITE.OUT=str(output/'frozen_build');Path(SITE.OUT).mkdir(exist_ok=True)
    (Path(SITE.OUT)/'futures.json').write_bytes(futures)
    th={};ph=[]
    for y in range(SITE.FIRST,season+1):
        games=SITE.team_games(y)
        if games is None or games.empty:raise ValueError('Missing team history '+str(y))
        th[y]=SITE.team_season(games[games.st==2],y)
        pb=SITE.player_box(y,season)
        if pb is None:raise ValueError('Missing player history '+str(y))
        ph.append(SITE.player_table(pb[pb.season_type==2]).assign(season=y))
    results={}
    for label,flag in [('before',False),('after',True)]:
        SIM.BUGFIXES=flag
        results[label]=SITE.awards(season,[p.copy(deep=True) for p in ph],{y:t.copy(deep=True) for y,t in th.items()})
    SIM.BUGFIXES=False
    identity=published_identity(results['before'],published)
    rows=[]
    for award in ('MVP','DPOY','ROY','6MOY'):
        sides={label:(data['awards'].get(award) or {}).get('current',[])[:5] for label,data in results.items()}
        sides['published']=(published.get('awards',{}).get(award) or {}).get('current',[])[:5]
        for i in range(5):
            row={'award':award,'rank':i+1}
            for label,z in sides.items():
                r=z[i] if i<len(z) else {}
                row[label+'_player']=r.get('name');row[label+'_probability']=r.get('prob')
            rows.append(row)
    pd.DataFrame(rows).to_csv(output/'nba_award_top5_before_after.csv',index=False)
    package={'published_identity':identity,'manifest':manifest,'comparison':rows,'before':results['before'],'after':results['after'],'published':published,
             'scope':'Opt-in bug fixes only; no AW_EARLY shrink layer. Before/after share inputs, weights and seeds. Published reference is shown separately because source refresh timing may differ.'}
    (output/'nba_award_top5_before_after.json').write_text(json.dumps(clean(package),indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')
    text='# NBA award bug-fix comparison\n\nOpt-in only; not deployed. No rejected shrink layer. Frozen capture: '+manifest['captured_utc']+'.\n\nThe **before** column recomputes the current code on the same frozen inputs as **after**. The separately saved published reference may differ because its collection time differs.\n\n| Award | Rank | Before | Chance | After | Chance |\n|---|---:|---|---:|---|---:|\n'
    for r in rows:
        fmt=lambda v:'—' if v is None else f'{100*v:.1f}%'
        text+=f'| {r["award"]} | {r["rank"]} | {r["before_player"] or "—"} | {fmt(r["before_probability"])} | {r["after_player"] or "—"} | {fmt(r["after_probability"])} |\n'
    (output/'NBA_AWARD_BUGFIX_TOP5.md').write_text(text,encoding='utf-8')
    print(text,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--season',type=int,default=2027);p.add_argument('--output',default='research/award_bugfix_review');p.add_argument('--published-ref',default='417455e9d1d71326ebd1160559828f1516f749dc');a=p.parse_args()
    compare(a.season,a.output,a.published_ref)
