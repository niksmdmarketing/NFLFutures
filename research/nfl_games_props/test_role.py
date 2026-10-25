import unittest
import numpy as np
import pandas as pd
import role_models as R

class RoleTests(unittest.TestCase):
    def test_target_and_future_production_do_not_change_role_features(self):
        p=pd.DataFrame([dict(game_id='target',team='A',aid='backup',tip=pd.Timestamp('2024-09-15T17:00Z'),
            h_attempts=1.,h_team_att=100.,report_status='UNKNOWN_NO_ELIGIBLE_ROW')])
        g=pd.DataFrame(dict(game_id=['prior','target','future'],tip=pd.to_datetime(['2024-09-08T17:00Z','2024-09-15T17:00Z','2024-09-22T17:00Z'])))
        stats=pd.DataFrame([dict(game_id='prior',team='A',aid='leader',position='QB',attempts=30),
            dict(game_id='prior',team='A',aid='backup',position='QB',attempts=1),
            dict(game_id='target',team='A',aid='backup',position='QB',attempts=35)])
        a=R.history_features(p,stats,g)
        stats.loc[stats.game_id=='target','attempts']=0
        stats=pd.concat([stats,pd.DataFrame([dict(game_id='future',team='A',aid='backup',position='QB',attempts=99)])])
        b=R.history_features(p,stats,g)
        pd.testing.assert_frame_equal(a,b)
        self.assertAlmostEqual(a.last_qb_share.iloc[0],1/31)

    def test_primary_scenario_ignores_tiny_backup_history(self):
        volume=np.zeros((1,41));volume[0,35]=1
        states={'primary':dict(share=.96,concentration=40),'relief':dict(share=.05,concentration=3)}
        starter=R.qb_pmf(volume,np.array([1.]),states)
        backup=R.qb_pmf(volume,np.array([0.]),states)
        self.assertAlmostEqual(starter.sum(),1);self.assertAlmostEqual(backup.sum(),1)
        self.assertGreater(float((starter@np.arange(starter.shape[1]))[0]),30)
        self.assertLess(float((backup@np.arange(backup.shape[1]))[0]),3)

    def test_own_absence_not_reallocated_to_self(self):
        z=pd.DataFrame(dict(game_id=['a','a'],team=['T','T']))
        s=np.array([.3,.2]);pa=np.array([.3,1.])
        other=R.missing_others(z,s,pa)
        self.assertAlmostEqual(other[0],0);self.assertAlmostEqual(other[1],.21)
        changed,_,_=R.redistribute(z,s,pa,1.)
        self.assertAlmostEqual(changed[0],s[0]);self.assertGreater(changed[1],s[1])

    def test_expected_target_budget_and_unchanged_catch(self):
        z=pd.DataFrame(dict(game_id=['a','a'],team=['T','T'],position=['WR','TE'],h_targets=[20.,30.],
            h_receptions=[10.,24.],h_team_att=[40.,40.]))
        pri={'target_share':{'WR':.2,'TE':.1},'catch':{'WR':.6,'TE':.7}}
        target,catch=R.receiving_parts(z,pri);original=z.copy(deep=True)
        repaired,_,_=R.redistribute(z,np.array([.8,.7]),np.array([1.,1.]),1.)
        self.assertLessEqual(repaired.sum(),1+1e-12)
        _,after=R.receiving_parts(z,pri);np.testing.assert_array_equal(catch,after)
        pd.testing.assert_frame_equal(z,original)

if __name__=='__main__':unittest.main()
