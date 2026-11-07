"""Regression tests from GPT's review of NBA props Amendments 5-8 (6 Nov 2026), adapted to Amendment 11. All data fabricated."""
import contextlib,gzip,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
PROPOSED=Path(__file__).resolve().parents[1]/'research'
sys.path.insert(0,str(PROPOSED))
import nba_props_challenger_c as C
import nba_props_price_run as R
import nba_props_sgo_names as S

class ConditionalTests(unittest.TestCase):
    def test_valid_and_near_zero(self):
        np.testing.assert_allclose(C.conditional([.7,.3],.6),[.5,.5])
        np.testing.assert_allclose(C.conditional([.99,.01],.02),[.5,.5])
        with self.assertRaises(C.LowAppearance):C.conditional([1-5e-13,5e-13],1e-12)   # Amendment 11: p_appear < 0.01 excluded
    def test_invalid_inputs(self):
        for unc,pa in [([1.,0.],0),([.7,.3],.2),([.5,.5],-1),([.5,.5],1.1),([np.nan,1],1),([1.00001,0],1),([1.,0.],np.nan)]:
            with self.subTest(unc=unc,pa=pa),self.assertRaises(ValueError):C.conditional(unc,pa)
    def test_archive_rounding_policy(self):   # Amendment 11: 1e-5 tolerance for archive rounding, larger gaps stop
        np.testing.assert_allclose(C.conditional([.5000001,.5],1),[.5,.5])   # zero mass is the remainder after the tail
        with self.assertRaises(ValueError):C.conditional([.50002,.5],1)
    def test_minutes_and_bands(self):
        self.assertEqual([C.band_of(x) for x in [0,15,15.1,25,25.1,110]],[0,0,1,1,2,2])
        q=np.zeros(30);q[14]=1
        self.assertEqual(C.expected_minutes(q),15)
        for x in [np.nan,np.inf,-1]:
            with self.assertRaises(ValueError):C.band_of(x)
    def test_monotone_valid_and_no_artificial_terminal_mass(self):
        maps={'pts':{'0':{'x':[.1,.9],'y':[.2,.8]}}}
        np.testing.assert_allclose(C.calibrated_conditional(np.array([1.,0.,0.]),10,'pts',maps),[1.,0.,0.])
        rng=np.random.default_rng(9)
        for _ in range(250):
            c=rng.dirichlet(np.ones(30));p=C.calibrated_conditional(c,10,'pts',maps)
            self.assertTrue(np.isfinite(p).all() and (p>=0).all());self.assertAlmostEqual(p.sum(),1)
            self.assertTrue((np.diff(np.cumsum(p))>=0).all())
            self.assertTrue((p>=C.FLOOR*c-1e-15).all())
        np.testing.assert_array_equal(C.calibrated_conditional(c,np.nan,'pts',{}),c)
    def test_logscore_does_not_cap_tiny_supported_probabilities(self):
        data=pd.DataFrame(dict(pts=[[1-1e-12,1e-12],[.1,.9]],pa=[1.,1.],em=[10,10],y_pts=[1,1]))
        def calibrated(c,*args):
            p=1e-10 if c[-1]<.01 else .1
            return np.array([1-p,p])
        with patch.object(C,'calibrated_conditional',side_effect=calibrated):
            self.assertGreater(C.logscore(data,'pts',{}),C.logscore(data,'pts'))

class DevelopmentTests(unittest.TestCase):
    def test_registered_replay_selection_and_date_bounds(self):
        schedule=pd.DataFrame(dict(id=[1,2,3],game_date_time=['2025-11-01T20:00:00Z','2026-01-12T00:00:00Z','2025-10-20T20:00:00Z'],season_type=[2,2,2]))
        base=dict(horizon_min=60,params_id='b',report={'replay':True})
        def rec(gid,aid,cut,**extra):
            player=dict(aid=aid,p_appear=1.,minutes_v2=[1.],pts_d_v2=[.5,.5],reb_v2=[.5,.5],ast_v2=[.5,.5])
            return dict(base,game_id=gid,cutoff_utc=cut,run_utc=cut,players=[player],**extra)
        records=[rec(1,1,'2025-11-01T18:00:00Z'),rec(1,2,'2025-11-01T18:30:00Z'),rec(1,3,'2025-11-01T19:01:00Z'),
                 rec(2,4,'2026-01-11T23:00:00Z'),rec(3,5,'2025-10-20T19:00:00Z')]
        wrong=rec(1,6,'2025-11-01T19:00:00Z');wrong['params_id']='wrong';records.append(wrong)
        late=rec(1,7,'2025-11-01T19:00:00Z');late['run_utc']='2025-11-01T19:01:00Z';records.append(late)
        nonreplay=rec(1,8,'2025-11-01T19:00:00Z');nonreplay['report']={};records.append(nonreplay)
        exact=rec(1,9,'2025-11-01T19:00:00Z');records.append(exact)
        outcomes=pd.DataFrame([dict(game_id=r['game_id'],aid=r['players'][0]['aid'],minutes=10,pts=1,reb=1,ast=1) for r in records])
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            for i,r in enumerate(records):
                with gzip.open(Path(td)/f'fixture_60_{i}.json.gz','wt') as f:json.dump(r,f)
            with patch.object(C.pd,'read_csv',return_value=schedule),patch.object(R,'outcomes',return_value=outcomes):
                selected=C.load([td],end=pd.Timestamp('2027-01-01',tz='UTC'))
        self.assertEqual(selected.aid.tolist(),[9])
    def test_holdout_boundary_and_ties_keep_identity(self):
        data=pd.DataFrame(dict(tip=pd.to_datetime(['2025-12-14T23:59:59Z','2025-12-15T00:00:00Z','2026-01-11T23:59:59Z']),game_id=[1,2,3]))
        with patch.object(C,'fit',return_value={}) as fitted,patch.object(C,'logscore',return_value=-1.),patch.object(C,'_summary',return_value={}):
            result=C.holdout_check(data)
        self.assertEqual(fitted.call_args.args[0].game_id.tolist(),[1])
        self.assertEqual(result['n_holdout'],2)
        self.assertTrue(all(not value['keep'] for value in result['stats'].values()))
    def test_freeze_uses_fresh_same_cohort_decision(self):
        data=pd.DataFrame(dict(game_id=[1,2]))
        decision={'stats':{s:{'keep':False} for s in C.FIELD}}
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            # Deliberately stale and contradictory; freeze must not consult it.
            (Path(td)/'nba_props_challenger_c_check.json').write_text(json.dumps({'stats':{s:{'keep':True} for s in C.FIELD}}))
            target=Path(td)/'frozen.json'
            with patch.object(C,'HERE',td),patch.object(C,'OUT',str(target)),patch.object(C,'load',return_value=data),patch.object(C,'holdout_check',return_value=decision) as checked,patch.object(C,'fit',return_value={s:{'0':{'x':[0,1],'y':[0,1]}} for s in C.FIELD}) as fitted,contextlib.redirect_stdout(io.StringIO()):
                C.freeze(['synthetic'])
            checked.assert_called_once_with(data);fitted.assert_called_once_with(data)
            self.assertTrue(all(not v for v in json.loads(target.read_text())['maps'].values()))

class ScoringTests(unittest.TestCase):
    def test_independent_row_drop_is_forbidden(self):
        x=pd.DataFrame(dict(window=[1,2],model_over_c=[.5,np.nan]))
        with self.assertRaisesRegex(ValueError,'paired scoring'):R._evaluate(x,'model_over_c')
    def test_same_input_rows_and_shared_gates(self):
        x=pd.DataFrame(dict(window=[1,2],model_over_v2=[.4,.6],model_over_c=[.45,.55]))
        info=dict(assessable=True,model_coef=1.,lb90=.1)
        def summary(b):return dict(n=len(b),dates=2,clv_lb90=.1,clv_mean=.1)
        with patch.object(R.PT,'info_test',return_value=info),patch.object(R.PT,'bets',side_effect=lambda d,t:d),patch.object(R.PT,'clv_summary',side_effect=summary),patch.object(R.PT,'placebo_arms',return_value=dict(exceeds_binding=True)):
            b=R._evaluate(x,'model_over_v2',True);c=R._evaluate(x,'model_over_c',True)
        self.assertEqual(b['n'],c['n']);self.assertEqual(b['gates'],c['gates'])
    def test_missing_challenger_stops_before_io(self):
        with patch.object(C,'OUT',str(BASE/'definitely_missing_model.json')),patch.object(R,'assemble',side_effect=AssertionError('data IO must not occur')):
            with self.assertRaisesRegex(ValueError,'stop before prices'):R.score(SimpleNamespace(prices='not-opened',w1=None,w2=None))
    def test_live_names_win_over_stored_and_fallback(self):
        class Captured(Exception):pass
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            props=Path(td)/'props';props.mkdir();(props/'fake.csv.gz').write_bytes(b'')
            (Path(td)/'player_names.json').write_text(json.dumps({'opaque':{'name':'Live Name'}}))
            (Path(td)/'player_names_sgo.json').write_text(json.dumps({'opaque':{'name':'Fallback Name'}}))
            data=pd.DataFrame([dict(player_key='opaque',player_name='Stored Name')]);seen=[]
            def capture(d):seen.append(d.player_name.iloc[0]);raise Captured()
            with patch.object(R.pd,'read_csv',return_value=data),patch.object(R.PT,'prices_long',side_effect=capture):
                with self.assertRaises(Captured):R.assemble(str(props),[],False)
        self.assertEqual(seen,['Live Name'])
    def test_unknown_participation_is_excluded_and_counted(self):
        names=['Synthetic One','Synthetic Two','Synthetic Three']
        start=pd.Timestamp('2026-02-01T20:00:00Z');cut=start-pd.Timedelta(hours=1)
        raw=pd.DataFrame([dict(fixture_id=str(i),player_key=str(i),player_name=names[i-1],stat='pts',start_time=start.isoformat()) for i in (1,2,3)])
        lines=pd.DataFrame([dict(fixture_id=str(i),player_name=names[i-1],stat='pts',line=.5) for i in (1,2,3)])
        f=pd.DataFrame([dict(game_id=i,aid=i,name=names[i-1],p_appear=1.,em=15.,cutoff=cut,window=1,
             **{s+'_'+v:[.5,.5] for s in ('pts','reb','ast') for v in ('v2','v3')}) for i in (1,2,3)])
        o=pd.DataFrame([dict(game_id=i,aid=i,minutes=mins,pts=1.,reb=1.,ast=1.) for i,mins in [(1,10.),(2,0.),(3,np.nan)]])
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            props=Path(td)/'props';props.mkdir();(props/'fake.csv.gz').write_bytes(b'')
            with patch.object(R.pd,'read_csv',return_value=raw),patch.object(R,'forecasts',return_value=f),patch.object(R,'fixture_map',return_value={str(i):i for i in (1,2,3)}),patch.object(R.PT,'prices_long',side_effect=lambda d:d),patch.object(R.PT,'main_lines',return_value=lines),patch.object(R.PT,'devig',side_effect=lambda d:d),patch.object(R,'outcomes',return_value=o):
                _,_,joined,meta=R.assemble(str(props),[],True)
        self.assertEqual(joined.aid.tolist(),[1])
        self.assertEqual(meta['unknown_participation_player_games'],2)
        self.assertEqual(meta['unknown_participation_lines'],2)

def identity_frames(winners=('one','one'),alias=False,repeated=False,mismatch=False):
    o=[];s=[]
    for i,winner in enumerate(winners):
        stamp=(pd.Timestamp('2026-02-01',tz='UTC')+pd.Timedelta(days=0 if repeated else i)).isoformat()
        for book in (['draftkings'] if alias else ['draftkings','fanduel']):
            o.append(dict(player_key='opaque',fixture_id='f'+str(i),start_time=stamp,home='Boston Celtics',away='Miami Heat',bookmaker=book,
                market_name='Over Under Player Points (incl. overtime)',handicap=.54 if mismatch else .5,has_close_quote=True))
            if not repeated or i==0:
                for nm in (['Synthetic Name','Synthetic Alias'] if alias else ['Synthetic Name']):
                    s.append(dict(event_id='e'+str(0 if repeated else i),start_time=stamp,home='Boston Celtics',away='Miami Heat',bookmaker=book,
                                  player_id=winner,player_name=nm,stat='points',line=.5))
    return pd.DataFrame(o),pd.DataFrame(s)

class IdentityTests(unittest.TestCase):
    def test_duplicate_aliases_do_not_manufacture_pairs(self):
        o,s=identity_frames(alias=True);self.assertEqual(S.match(o,s,set()),{})
    def test_duplicate_fixtures_do_not_manufacture_games(self):
        o,s=identity_frames(repeated=True);self.assertEqual(S.match(o,s,set()),{})
    def test_line_equality_is_exact(self):
        o,s=identity_frames(mismatch=True);self.assertEqual(S.match(o,s,set()),{})
    def test_two_games_and_eighty_percent(self):
        o,s=identity_frames(winners=('one',));self.assertEqual(S.match(o,s,set()),{})
        o,s=identity_frames(winners=('one','one','one','one','two'))
        self.assertEqual(S.match(o,s,set())['opaque']['agree'],.8)
        o,s=identity_frames(winners=('one','one','one','two'));self.assertEqual(S.match(o,s,set()),{})
    def test_game_tie_is_unmatched(self):
        o,s=identity_frames();s=pd.concat([s,s.assign(player_id='two',player_name='Other Synthetic')],ignore_index=True)
        self.assertEqual(S.match(o,s,set()),{})
    def test_live_name_exclusion(self):
        o,s=identity_frames();self.assertEqual(S.match(o,s,{'opaque'}),{})
    def test_both_teams_and_fifteen_minute_boundary(self):
        o,s=identity_frames();s.start_time=pd.to_datetime(s.start_time)+pd.Timedelta(minutes=15)
        self.assertIn('opaque',S.match(o,s,set()))
        s.start_time+=pd.Timedelta(seconds=1);self.assertEqual(S.match(o,s,set()),{})
        o,s=identity_frames();s.away='New York Knicks';self.assertEqual(S.match(o,s,set()),{})
    def test_quote_presence_only_and_whitelisted_io(self):
        o,s=identity_frames();o['close_price']=object();o['result']='must not be requested'
        seen=[];reader=pd.read_csv
        def guarded(path,*args,**kwargs):
            if kwargs.get('nrows')!=0:
                self.assertIsNotNone(kwargs.get('usecols'))
                self.assertFalse({'close_price','result'} & set(kwargs['usecols']))
            seen.append(kwargs);return reader(path,*args,**kwargs)
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            op=Path(td)/'op';(op/'props').mkdir(parents=True);sp=Path(td)/'sgo';sp.mkdir()
            # All contents are invented; forbidden columns verify the I/O contract.
            o.to_csv(op/'props/fake.csv.gz',index=False);s.to_csv(sp/'fake.csv.gz',index=False)
            (op/'player_names.json').write_text(json.dumps({'opaque':{'name':''}}))
            with patch.object(S.pd,'read_csv',side_effect=guarded),contextlib.redirect_stdout(io.StringIO()):S.run(str(op),str(sp))
            self.assertIn('opaque',json.loads((op/'player_names_sgo.json').read_text()))
        self.assertTrue(seen)
    def test_missing_presence_metadata_stops_before_data_rows(self):
        o,s=identity_frames();o=o.drop(columns=['has_close_quote']);reader=pd.read_csv;calls=[]
        def guarded(path,*args,**kwargs):calls.append(kwargs);return reader(path,*args,**kwargs)
        with tempfile.TemporaryDirectory(dir=BASE) as td:
            op=Path(td)/'op';(op/'props').mkdir(parents=True);sp=Path(td)/'sgo';sp.mkdir()
            o.to_csv(op/'props/fake.csv.gz',index=False)
            with patch.object(S.pd,'read_csv',side_effect=guarded):
                with self.assertRaisesRegex(ValueError,'Identity-only metadata'):S.run(str(op),str(sp))
        self.assertTrue(all(k.get('nrows')==0 for k in calls))

if __name__=='__main__':unittest.main()
