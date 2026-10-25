import unittest
import numpy as np
import pandas as pd
import core as C
from build import make_game_features,make_player_features


class Tests(unittest.TestCase):
    def games(self):
        tips=pd.to_datetime(['2020-09-01T17:00:00Z','2020-09-08T17:00:00Z','2020-09-15T17:00:00Z'])
        return pd.DataFrame(dict(game_id=['a','b','c'],season=[2020]*3,week=[1,2,3],tip=tips,
            home_team=['A']*3,away_team=['B']*3,home_score=[20,30,40],away_score=[10,10,10],location=['Home']*3))
    def agg(self):
        return pd.DataFrame([dict(game_id=g,team=t,pass_off=v,rush_off=v,pass_def=v,rush_def=v,plays=60,attempts=30)
            for g,v in [('a',.1),('b',.2),('c',.3)] for t in ('A','B')])
    def stats(self):return pd.DataFrame(dict(game_id=['a','a','b','b','c','c'],team=['A','B']*3,attempts=[30]*6))

    def test_current_and_future_outcomes_do_not_change_features(self):
        g=self.games();a,_=make_game_features(g,self.agg(),self.stats())
        g.loc[1:,'home_score']=99
        agg=self.agg();agg.loc[agg.game_id.isin(['b','c']),'pass_off']=99
        b,_=make_game_features(g,agg,self.stats())
        np.testing.assert_array_equal(a.loc[:1,C.GAME_FEATURES+['elo_p']].to_numpy(),b.loc[:1,C.GAME_FEATURES+['elo_p']].to_numpy())

    def test_six_hour_availability_buffer(self):
        g=self.games();g.loc[1,'tip']=g.loc[0,'tip']+pd.Timedelta(hours=3)
        a,_=make_game_features(g,self.agg(),self.stats())
        self.assertEqual(a.iloc[1].h_pass_off,0)
        self.assertEqual(a.iloc[0].elo_p,a.iloc[1].elo_p)

    def test_elo_direction_and_bounds(self):
        self.assertEqual(float(C.elo_probability(0)),.5)
        self.assertGreater(C.elo_change(0,7),0)
        self.assertLess(C.elo_change(0,-7),0)
        self.assertEqual(C.elo_change(0,0),0)

    def test_market_fields_not_features(self):
        self.assertFalse(any(any(x in c for x in ['spread','moneyline','odds','total_line','qb_id']) for c in C.GAME_FEATURES+C.VOLUME_FEATURES+C.APP_FEATURES))

    def test_allocation_count_and_tail_invariants(self):
        volume=np.zeros((2,11));volume[:,5]=1
        q=C.allocation_pmf(volume,np.array([.2,.8]),10)
        np.testing.assert_allclose(q.sum(1),1)
        self.assertTrue((q[:,6:]==0).all())
        np.testing.assert_allclose(q@np.arange(11),[1,4],atol=1e-10)
        small=C.allocation_pmf(volume,np.array([.2,.8]),10,limit=2)
        np.testing.assert_allclose(small.sum(1),1)
        np.testing.assert_allclose(small[:,2],q[:,2:].sum(1))

    def test_count_pmf_and_rps(self):
        q=C.nb_pmf([1,20],5,100)
        np.testing.assert_allclose(q.sum(1),1)
        p=np.zeros((1,10));p[0,3]=1
        self.assertEqual(C.rps(p,[3])[0],0)

    def test_empirical_margin_ties_retained(self):
        p=C.empirical_pmf([0],[-1,0,1],-2,2)
        self.assertAlmostEqual(p[0,2],1/3)

    def test_player_candidate_not_selected_from_target_box(self):
        g=self.games();_,teams=make_game_features(g,self.agg(),self.stats())
        st=pd.DataFrame([dict(game_id=gid,team='A',aid=aid,attempts=30,targets=0,receptions=0) for gid,aid in [('a','old'),('b','new'),('c','new')]])
        sn=pd.DataFrame([dict(game_id='a',team='A',aid='old',player='Old',position='QB',offense_snaps=60,offense_pct=1.),
            dict(game_id='b',team='A',aid='new',player='New',position='QB',offense_snaps=60,offense_pct=1.)])
        complete=pd.DataFrame(dict(game_id=['a','b','c'],team=['A']*3,complete=[True]*3)).set_index(['game_id','team'])
        p,audit=make_player_features(g,st,sn,complete,teams)
        self.assertEqual(set(p[p.game_id=='b'].aid),{'old'})
        self.assertEqual(float(p[p.game_id=='b'].app.iloc[0]),0)
        self.assertGreater(audit['excluded_actual_first_or_unseen_appearances'],0)

    def test_official_production_overrides_zero_offensive_snaps_as_label_only(self):
        g=self.games();_,teams=make_game_features(g,self.agg(),self.stats())
        st=pd.DataFrame([dict(game_id=gid,team='A',aid='old',attempts=30,targets=0,receptions=0) for gid in ['a','b','c']])
        sn=pd.DataFrame([dict(game_id='a',team='A',aid='old',player='Old',position='QB',offense_snaps=60,offense_pct=1.),
            dict(game_id='b',team='A',aid='old',player='Old',position='QB',offense_snaps=0,offense_pct=0.)])
        comp=pd.DataFrame(dict(game_id=['a','b','c'],team=['A']*3,complete=[True]*3)).set_index(['game_id','team'])
        p,_=make_player_features(g,st,sn,comp,teams)
        self.assertEqual(float(p[p.game_id=='b'].app.iloc[0]),1)

    def test_missing_snap_file_does_not_become_dnp(self):
        g=self.games();_,teams=make_game_features(g,self.agg(),self.stats())
        st=pd.DataFrame([dict(game_id='a',team='A',aid='old',attempts=30,targets=0,receptions=0)])
        sn=pd.DataFrame([dict(game_id='a',team='A',aid='old',player='Old',position='QB',offense_snaps=60,offense_pct=1.)])
        comp=pd.DataFrame(dict(game_id=['a'],team=['A'],complete=[True])).set_index(['game_id','team'])
        p,_=make_player_features(g,st,sn,comp,teams)
        self.assertTrue(np.isnan(p[p.game_id=='b'].app.iloc[0]))


if __name__=='__main__':unittest.main()
