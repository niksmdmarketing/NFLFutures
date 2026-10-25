"""One create-only private refresh; no existing model inputs changed."""
import hashlib,json,urllib.request
from datetime import datetime,timezone
from build import OUT

def main():
    target=OUT/'raw_fresh';target.mkdir(exist_ok=True)
    jobs=[('schedules/games.csv','games.csv'),('pbp/play_by_play_2026.csv.gz','play_by_play_2026.csv.gz'),
        ('stats_player/stats_player_week_2026.csv','stats_player_week_2026.csv'),
        ('snap_counts/snap_counts_2026.csv','snap_counts_2026.csv'),('players/players.csv','players.csv')]
    records=[]
    for rel,name in jobs:
        path=target/name;url='https://github.com/nflverse/nflverse-data/releases/download/'+rel
        if path.exists():
            print('Existing research capture retained',name,flush=True);continue
        start=datetime.now(timezone.utc).isoformat()
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Independent-NFL-research'})
            with urllib.request.urlopen(req,timeout=90) as r:data=r.read()
            if len(data)<100 or (name.endswith('.gz') and data[:2]!=b'\x1f\x8b'):raise ValueError('Invalid downloaded content')
            if name.endswith('.csv') and b',' not in data.splitlines()[0]:raise ValueError('Not CSV')
            with path.open('xb') as f:f.write(data)
            records.append(dict(file=name,url=url,started_utc=start,finished_utc=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
            print('Refreshed',name,len(data),flush=True)
        except Exception as e:
            records.append(dict(file=name,url=url,started_utc=start,error=type(e).__name__+': '+str(e)))
            print('Refresh unavailable',name,type(e).__name__,flush=True)
    with (OUT/'fresh_input_capture.json').open('x') as f:json.dump(records,f,indent=2)

if __name__=='__main__':main()
