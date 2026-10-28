import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pipeline'),str(ROOT/'research')]
import nba_award_sim as S
from nba_award_early_tools import blend,scheduled_games,validate_distribution
from nba_award_early_shrink_score import score

class EarlyAwardTests(unittest.TestCase):
    def lines(self,gp=70,tg=82):
        r={'name':'Synthetic Player','team':'BOS','gp':gp,'tg':tg,'tw':tg*.6,'rookie':True,'wp':.6}
        for k in S.STATS:r[k]=gp*(30 if k=='mins' else 1 if k in ('m20','m15') else 0 if k=='start' else 10)
        return pd.DataFrame([r],index=[1])
    def test_mass_repair_and_legacy_default_is_unchanged(self):
        prev=self.lines();C=S.preseason_pool(prev,'MVP');C['avail0']=.5
        args=(C,prev,C,'MVP',S.SPECS['MVP'][3],np.zeros(6),82,2024)
        with patch.object(S,'SIMS',100),patch.object(S,'AVAIL_SD',.35):
            default=S.simulate(*args,pre=True);legacy=S.simulate(*args,pre=True,replay=False)
            diag={};fixed=S.simulate(*args,pre=True,replay=True,diagnostics=diag)
        self.assertEqual(default,legacy);self.assertLess(sum(default.values()),1)
        self.assertAlmostEqual(sum(fixed.values()),1);self.assertGreater(diag['invalid_draws'],0)
    def test_rookie_and_sixth_man_are_not_subject_to_65_game_minimum(self):
        a=self.lines(50);feats=S.features(a,82);D=a.assign(**feats);D['bench']=True
        with patch.object(S,'SIMS',3):
            for award in ('ROY','6MOY'):
                p=S.simulate(a,a,D,award,S.SPECS[award][3],np.zeros(len(S.SPECS[award][3])),82,2024,replay=True)
                self.assertAlmostEqual(sum(p.values()),1)
            self.assertEqual(S.simulate(a,a,D,'MVP',S.SPECS['MVP'][3],np.zeros(6),82,2024,replay=True),{})
    def test_blend_union_empty_zero_and_exact_twenty_game_identity(self):
        ps={'new':.75,'shared':.25};pp={'old':.8,'shared':.2}
        p=blend(ps,pp,5);self.assertAlmostEqual(p['new'],.1875);self.assertAlmostEqual(p['old'],.6)
        self.assertAlmostEqual(sum(p.values()),1)
        self.assertEqual(blend(ps,{},5),blend(ps,{'old':0},5))
        self.assertEqual(blend(ps,pp,20),ps);self.assertEqual(blend(ps,{},21),ps)
        with self.assertRaises(ValueError):blend({'A':.5},{},2)
    def test_scheduled_horizon_uses_opening_schedule_not_final_2020_length(self):
        self.assertEqual(scheduled_games(2012),66);self.assertEqual(scheduled_games(2021),72);self.assertEqual(scheduled_games(2020),82)
    def box_frame(self,n):
        data={'season_type':[2]*n,'game_id':list(range(n)),'minutes':[30]*n,'team_abbreviation':['BOS']*n,'starter':['false']*n,'team_winner':['true']*n,'game_date':pd.date_range('2019-10-01',periods=n),'athlete_id':[1]*n,'athlete_display_name':['Synthetic Player']*n}
        for c in ('points','rebounds','defensive_rebounds','assists','steals','blocks','turnovers','plus_minus','field_goals_attempted','free_throws_attempted'):data[c]=[10]*n
        return pd.DataFrame(data)
    def test_replay_input_prefix_does_not_depend_on_future_boxes(self):
        with patch.object(S.os.path,'exists',return_value=True):
            with patch.object(S.pd,'read_csv',return_value=self.box_frame(3)):
                prefix=S.season_lines(S.boxes(2020,replay=True),pd.Timestamp('2019-10-03'))
                self.assertTrue(S.boxes(2020).empty)
            with patch.object(S.pd,'read_csv',return_value=self.box_frame(40)):
                full=S.season_lines(S.boxes(2020,replay=True),pd.Timestamp('2019-10-03'))
        pd.testing.assert_frame_equal(prefix,full)
    def test_exhibition_codes_are_excluded_without_future_coverage(self):
        data=self.box_frame(3);data.loc[0,'team_abbreviation']='EAST'
        with patch.object(S.os.path,'exists',return_value=True),patch.object(S.pd,'read_csv',return_value=data):
            b=S.boxes(2020,replay=True)
        self.assertEqual(set(b.team),{'BOS'});self.assertEqual(len(b),2)
    def scoring_rows(self):
        return pd.DataFrame([{'season':y,'award':a,'ck':k,'method':m,'frac':n/66,'L':66,'team_games':n,'p_winner':.3 if m=='sim' else .4,'fav':.5,'fav_won':1,'probability_mass':1}
                             for y in (2010,2011) for a in ('MVP','DPOY','ROY','6MOY') for k,n in enumerate((3,7,14,19,20)) for m in ('sim','shrink')])
    def test_scorer_pairs_exact_rows_excludes_twenty_games_and_is_reproducible(self):
        rows=self.scoring_rows();result=score(rows,[2010,2011])
        self.assertEqual(result['paired_cells'],32);self.assertEqual(result['verdict'],'pass')
        self.assertAlmostEqual(result['gain'],np.log(.4/.3));self.assertEqual(result,score(rows,[2010,2011]))
        self.assertEqual(result['gates']['G3']['better_or_equal_seasons'],2)
        rows.loc[rows.team_games==20,'frac']=.303
        with self.assertRaises(ValueError):score(rows)
    def test_scorer_keeps_ties_and_rejects_missing_or_duplicate_pairs(self):
        rows=self.scoring_rows();rows['p_winner']=.3;r=score(rows)
        self.assertEqual(r['gates']['G3']['share'],1);self.assertFalse(r['gates']['G1']['pass'])
        with self.assertRaises(ValueError):score(rows.iloc[1:])
        with self.assertRaises(ValueError):score(pd.concat([rows,rows.iloc[:1]]))
if __name__=='__main__':unittest.main()

