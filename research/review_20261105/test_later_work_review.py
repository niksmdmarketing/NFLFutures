"""Offline independent witnesses; original forecasting/research source remains unchanged."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'pipeline'),str(ROOT/'research')]
import nba_award_sim as SIM
import nhl_awards as NHL
import award_eval as AE

# Execute the ORIGINAL feature functions without the module's network-fetching import.
def injury_module(frames):
 tree=ast.parse((ROOT/'research/nfl_nonqb_injury_test.py').read_text())
 names={'GROUPS','EXCLUDE','G'}
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'group','fix','season_features','futures_missing'} or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
 env={'pd':pd,'np':np,'os':os,'FIX':{'OAK':'LV','SD':'LAC','STL':'LA','LAR':'LA','JAC':'JAX'},'PFR2GSIS':{'P1':'ID1','P2':'ID2'},'PLAYER_POS':{'ID1':'OL','ID2':'QB'},'load':lambda rel,y:frames[rel].copy()}
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'ORIGINAL_nfl_nonqb_feature_functions','exec'),env)
 return env

def injury_frames(future_position='WR',missing_week3=True):
 snap=pd.DataFrame([{'game_type':'REG','team':'BUF','week':w,'pfr_player_id':'P1','offense_pct':.8,'defense_pct':0.,'offense_snaps':40,'defense_snaps':0} for w in [1,2]])
 roster=[]
 for w in [1,2,3,4]:
  if not (w==3 and missing_week3):roster.append({'game_type':'REG','team':'BUF','week':w,'pfr_id':None,'gsis_id':'ID1','position':'OL' if w!=4 else future_position,'depth_chart_position':'OL' if w!=4 else future_position,'status':'ACT'})
 roster.append({'game_type':'REG','team':'BUF','week':3,'pfr_id':None,'gsis_id':'ID2','position':'QB','depth_chart_position':'QB','status':'ACT'})
 injury=pd.DataFrame([{'game_type':'REG','team':'BUF','week':3,'gsis_id':'ID1','report_status':'Out'}])
 return {'snap_counts/snap_counts':snap,'weekly_rosters/roster_weekly':pd.DataFrame(roster),'injuries/injuries':injury}

class LaterWork(unittest.TestCase):
 def test_witness_future_position_changes_an_earlier_feature(self):
  a=injury_module(injury_frames('WR'))['season_features'](2025)
  b=injury_module(injury_frames('OL'))['season_features'](2025)
  self.assertEqual(a[('BUF',3)]['WR'],.8);self.assertEqual(b[('BUF',3)]['OL'],.8)
  self.assertNotEqual(a[('BUF',3)],b[('BUF',3)])
 def test_global_player_link_restores_missing_roster_pfr_and_depth_position(self):
  frames=injury_frames('OL',False);ro=frames['weekly_rosters/roster_weekly'];ro.loc[ro.gsis_id.eq('ID1'),'position']='DB';ro.loc[ro.gsis_id.eq('ID1'),'depth_chart_position']='CB'
  env=injury_module(frames);f=env['season_features'](2025)
  self.assertEqual(f[('BUF',3)]['CB'],.8);self.assertEqual(f[('BUF',3)]['S'],0.)
 def test_current_or_future_game_snaps_do_not_change_stage1_importance(self):
  frames=injury_frames('OL',False);env=injury_module(frames);before=env['season_features'](2025)[('BUF',3)]
  extra=frames['snap_counts/snap_counts'].iloc[[0]].copy();extra['week']=3;extra['offense_pct']=.01
  frames['snap_counts/snap_counts']=pd.concat([frames['snap_counts/snap_counts'],extra]);after=injury_module(frames)['season_features'](2025)[('BUF',3)]
  self.assertEqual(before,after)
 def test_witness_stage2_loop_omits_registered_week17(self):
  tree=ast.parse((ROOT/'research/replay_nfl.py').read_text())
  loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='w' and 'BT_WMIN' in ast.unparse(n.iter))
  with patch.dict(os.environ,{'BT_WMIN':'2'}):weeks=list(eval(compile(ast.Expression(loop.iter),'ORIGINAL_replay_loop','eval'),{'os':os,'last_week':18}))
  self.assertEqual(weeks,list(range(2,17)));self.assertNotIn(17,weeks)
 def test_witness_week2_known_zero_is_dropped(self):
  f=injury_module(injury_frames('OL',False))['season_features'](2025)
  self.assertNotIn(('BUF',2),f)
 def test_witness_simulated_award_pool_is_larger_than_fixed_baseline(self):
  n=30;d=pd.DataFrame({k:np.full(n,10.) for k in SIM.STATS},index=range(n));d['pts']=100.;d['mins']=220.;d['gp']=10.;d['tg']=10.;d['tw']=5.;d['wp']=.5;d['name']=['Candidate '+chr(65+i//26)+chr(65+i%26) for i in range(n)];d['team']='BOS';d['rookie']=True;d['bench']=True;d['start']=0.
  d=d.assign(**SIM.features(d,10.));feats=SIM.SPECS['ROY'][3]
  with patch.object(SIM,'SIMS',100):prob=SIM.simulate(d,d.iloc[:0],d,'ROY',feats,np.zeros(len(feats)),82.,2023,rng=np.random.default_rng(123))
  positive=sum(x>0 for x in prob.values());self.assertGreater(positive,15);self.assertAlmostEqual(sum(prob.values()),1.,places=12)
  self.assertGreater(positive/15,1.)
 def test_witness_nhl_pools_are_maxima_not_fixed_sizes(self):
  sk=pd.DataFrame({'pts':range(30),'pos':['D']*15+['F']*15,'rookie':[1]*30,'gp':[40]*30});gl=pd.DataFrame({'gp':[40,30],'saa':[1.,2.],'rookie':[1,1]})
  self.assertEqual(len(NHL.pool('Hart',sk,gl)),22);self.assertEqual(len(NHL.pool('Calder',sk,gl)),14)
 def test_witness_failed_calibration_rewrites_measured_log_loss(self):
  ev={'seasons':2,'log_loss':.2,'baseline_log_loss':1.,'mean_p_winner':.8,'winner_in_pool':1.,'fav_said':.9,'fav_won':.5,'fav_gap_ci90':[.1,.4],'pass':False,'basis':'test'}
  with tempfile.TemporaryDirectory() as td:
   f=Path(td)/'eval.json';f.write_text(json.dumps({'nba:MVP':ev}))
   with patch.object(AE,'PATH',str(f)):obj=AE.attach({'awards':{'MVP':{'current':[{'prob':.7}]}}},'nba')
  self.assertEqual(obj['awards']['MVP']['eval']['log_loss'],1.);self.assertEqual(obj['awards']['MVP']['current'][0]['prob'],.7)

if __name__=='__main__':unittest.main(verbosity=2)
