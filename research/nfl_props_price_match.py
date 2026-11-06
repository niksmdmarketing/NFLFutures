"""Join future OddsPapi reference rows to NFL PMFs without modifying prices/models.

Not run on real prices during the preparation task. A market crosswalk must be
frozen from discovery metadata before use. Proprietary player keys are not ESPN IDs.
"""
import argparse,csv,gzip,json,math
from collections import defaultdict
from pathlib import Path
import nfl_prop_identity as I

def read_csv(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)

def join(rows,forecasts,fixtures,market_map,horizon,player_names=None):
    candidates=defaultdict(list)
    for r in forecasts:
        if int(r['horizon_minutes'])==horizon:candidates[r['game_id']].append(r)
    for row in rows:
        result={k:row.get(k) for k in ('fixture_id','bookmaker','market_id','outcome_id','player_key','player_name')}
        result.update(reference_only=True,price_eligibility_assessed=False)
        market=market_map.get(str(row.get('market_id')))
        if not market or market.get('scope')!='full_game' or market.get('stat') not in I.POSITIONS:
            yield {**result,'status':'unsupported_or_unverified_market'};continue
        try:
            raw=row.get('handicap')
            if isinstance(raw,bool) or raw is None:raise ValueError()
            line=float(raw)
            if not math.isfinite(line) or line<0 or line%1!=.5 or line!=market['handicap']:raise ValueError()
        except (KeyError,ValueError,TypeError):
            yield {**result,'status':'market_handicap_mismatch'};continue
        result['line']=line
        entry=(player_names or {}).get(str(row.get('player_key')))
        name=entry.get('name') if isinstance(entry,dict) else entry
        if not isinstance(name,str) or not name.strip():
            yield {**result,'status':'missing_player_name_map'};continue
        # OddsPapi keys are only keys into this name map, never ESPN/GSIS IDs.
        result['player_name']=name
        game=I.fixture(row.get('home'),row.get('away'),row.get('start_time'),fixtures)
        if game['status']!='matched':yield {**result,**game};continue
        matched=I.player(name,market['stat'],candidates[game['game_id']])
        result.update(matched,game_id=game['game_id'],stat=market['stat'],horizon_minutes=horizon)
        if matched['status']=='matched':
            selected=[r for r in candidates[game['game_id']] if r['gsis_id']==matched['gsis_id'] and r['stat']==market['stat']]
            if len(selected)!=1:
                yield {**result,'status':'ambiguous_forecast'};continue
            f=selected[0];result.update(distribution_id='|'.join([f['game_id'],str(horizon),f['gsis_id'],f['stat']]),
                                       source_tier=f['source_tier'],forecast_primary_eligible=f['primary_eligible'],cutoff_utc=f['cutoff_utc'])
            try:
                probability=I.probabilities(f['pmf'],line)
                result.update(line=line,p_over=probability['over'],p_under=probability['under'],line_status='numeric_half_point')
            except (ValueError,TypeError):result['line_status']='missing_or_unsupported_numeric_line'
        yield result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True);p.add_argument('--odds',type=Path,required=True)
    p.add_argument('--market-map',type=Path,required=True);p.add_argument('--horizon',type=int,choices=[60,360],default=60)
    p.add_argument('--player-names',type=Path,help='OddsPapi key-to-name map; defaults to sibling of props directory')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    with gzip.open(a.export/'probabilities.jsonl.gz','rt',encoding='utf-8') as f:forecasts=[json.loads(line) for line in f]
    fixtures=json.loads((a.export/'fixtures.json').read_text(encoding='utf-8'))
    mapping=json.loads(a.market_map.read_text(encoding='utf-8'))
    names_path=a.player_names or a.odds.parent.parent/'player_names.json'
    player_names=json.loads(names_path.read_text(encoding='utf-8'))
    output=list(join(read_csv(a.odds),forecasts,fixtures,mapping,a.horizon,player_names))
    with a.output.open('x',encoding='utf-8') as f:
        for row in output:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    counts=defaultdict(int)
    for row in output:counts[row['status']]+=1
    print(json.dumps({'identity_counts':dict(counts),'real_bookmaker_match_rate_requires_real_price_rows':True},indent=2))

if __name__=='__main__':main()
