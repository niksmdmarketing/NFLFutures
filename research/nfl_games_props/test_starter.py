import unittest
import numpy as np
import pandas as pd
import starter_models as S

class StarterTests(unittest.TestCase):
    def test_cutoff_future_stale_and_ambiguous(self):
        d=pd.DataFrame([dict(team='A',dt='2025-09-01T12:00Z',pos_abb='QB',gsis_id='old',pos_rank=1),
            dict(team='A',dt='2025-09-02T12:00Z',pos_abb='QB',gsis_id='new',pos_rank=1)])
        index=S.DepthIndex(d);a,status=index.at('A',pd.Timestamp('2025-09-02T12:00Z'))
        self.assertEqual(a.gsis_id.iloc[0],'old')
        self.assertIsNone(index.at('A',pd.Timestamp('2025-09-06T12:00:01Z'))[0])
        ambiguous=pd.concat([a,a.assign(gsis_id='tie')])
        self.assertEqual(S.signals(ambiguous),{'old':0.,'tie':0.})

    def test_fallback_cannot_see_target_stats(self):
        t=dict(team='A',season=2025,game_id='target',week=1,tip=pd.Timestamp('2025-09-08T17:00Z'))
        stats=pd.DataFrame([dict(aid='new',season=2025,ready=pd.Timestamp('2025-09-08T23:00Z'),attempts=45.,team_attempts=45.)])
        snaps=pd.DataFrame(columns=['aid','season','team','ready','offense_snaps','offense_pct'])
        snaps['ready']=pd.to_datetime(snaps.ready,utc=True)
        f=S.fallback(t,'new','New QB',stats,snaps)
        self.assertEqual(f['h_attempts'],0);self.assertEqual(f['fallback_history_games'],0)
        stats['attempts']=1
        self.assertEqual(S.fallback(t,'new','New QB',stats,snaps),f)

    def test_expected_active_is_not_starter_confirmation(self):
        cutoff=pd.Timestamp('2025-09-08T16:00Z')
        r=dict(status='expected to play',game_id='g',team='A',aid='p',source_url='https://example.com',version_observed_at_utc='2025-09-08T15:00Z')
        self.assertIsNone(S.confirmed_signal(r,'g','A','p',cutoff)[0])
        r['status']='confirmed_starter';self.assertEqual(S.confirmed_signal(r,'g','A','p',cutoff)[0],1)
        self.assertIsNone(S.confirmed_signal(r,'g','A','p',cutoff,out=True)[0])
        self.assertIsNone(S.confirmed_signal(r,'wrong','A','p',cutoff)[0])
        r['version_observed_at_utc']='2025-09-08T16:00Z'
        self.assertIsNone(S.confirmed_signal(r,'g','A','p',cutoff)[0])

    def test_depth_shift_has_no_effect_when_missing(self):
        p=np.array([.1,.9]);q=S.shifted_probability(p,np.zeros(2),4)
        np.testing.assert_allclose(p,q)
        q=S.shifted_probability(p,np.array([1.,-1.]),1.)
        self.assertGreater(q[0],p[0]);self.assertLess(q[1],p[1])

if __name__=='__main__':unittest.main()
