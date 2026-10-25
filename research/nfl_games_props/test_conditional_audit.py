import unittest
import numpy as np
import pandas as pd
from conditional_audit import control_means, appearances, budget_rates


class AuditTests(unittest.TestCase):
    def history(self):
        return pd.DataFrame(dict(aid=['a']*12,position=['QB']*12,season=[2020]*12,
            tip=pd.date_range('2020-09-01',periods=12,freq='7D',tz='UTC'),attempts=np.arange(12)))

    def test_last_ten_and_current_future_isolation(self):
        h=self.history()
        target=pd.DataFrame([dict(aid='a',position='QB',season=2021,tip=pd.Timestamp('2021-01-01',tz='UTC'))])
        got=control_means(target,h,'attempts',35.)
        self.assertEqual(got.recent_mean.iloc[0],6.5)
        self.assertEqual(got.season_mean.iloc[0],5.5)
        future=target.assign(attempts=1000)
        both=pd.concat([h,future],ignore_index=True)
        pd.testing.assert_frame_equal(got,control_means(target,both,'attempts',35.))

    def test_buffer_and_fallback(self):
        h=self.history().iloc[:1]
        t=h.drop(columns='attempts').copy();t.tip+=pd.Timedelta(hours=7)
        self.assertEqual(control_means(t,h,'attempts',35.).earlier_appearances.iloc[0],0)
        t.tip+=pd.Timedelta(seconds=1)
        self.assertEqual(control_means(t,h,'attempts',35.).earlier_appearances.iloc[0],1)
        t['aid']='new';t['season']=2021
        self.assertEqual(control_means(t,h,'attempts',35.).season_mean.iloc[0],0.)

    def test_appearances_include_zero_not_dnp(self):
        sn=pd.DataFrame(dict(game_id=['g']*3,team=['T']*3,aid=['a','b','c'],position=['WR']*3,offense_snaps=[10,0,0]))
        st=pd.DataFrame(dict(game_id=['g']*2,team=['T']*2,aid=['b','c'],position=['WR']*2,targets=[0,1],receptions=[0,1]))
        games=pd.DataFrame([dict(game_id='g',season=2020,tip=pd.Timestamp('2020-01-01',tz='UTC'))])
        z=appearances(st,sn,games)
        self.assertEqual(set(z.aid),{'a','c'})
        self.assertEqual(z.set_index('aid').loc['a','receptions'],0.)

    def test_budget_ignores_eventual_participation(self):
        z=pd.DataFrame(dict(game_id=['g','g'],team=['T','T'],position=['WR','WR'],h_targets=[80,80],h_team_att=[100,100],h_receptions=[50,50],app=[1,0]))
        pri=dict(target_share={'WR':.2},catch={'WR':.65})
        rate,scale,*_=budget_rates(z,pri)
        self.assertTrue(np.all(scale<1))
        z.app=1
        np.testing.assert_array_equal(rate,budget_rates(z,pri)[0])
        np.testing.assert_allclose(scale.sum()*84/120,1.)

    def test_position_change_does_not_drop_offensive_appearance(self):
        sn=pd.DataFrame([dict(game_id='g',team='T',aid='a',position='LB',offense_snaps=1)])
        st=pd.DataFrame(columns=['game_id','team','aid','position','targets','receptions'])
        games=pd.DataFrame([dict(game_id='g',season=2020,tip=pd.Timestamp('2020-01-01',tz='UTC'))])
        z=appearances(st,sn,games)
        self.assertEqual(z.aid.tolist(),['a'])
        self.assertEqual(z.receptions.tolist(),[0.])


if __name__=='__main__':
    unittest.main()
