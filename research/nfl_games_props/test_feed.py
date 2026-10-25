import unittest
import pandas as pd
from feed_test import temporal_join,norm,team

class FeedTest(unittest.TestCase):
    def test_after_cutoff_and_wrong_team_never_join(self):
        p=pd.DataFrame([dict(game_id='g',team='NYJ',season=2024,week=1,aid='1',tip='2024-09-08T17:00:00Z'),
                        dict(game_id='g',team='NYJ',season=2024,week=1,aid='2',tip='2024-09-08T17:00:00Z')])
        r=pd.DataFrame([dict(team='NYJ',season=2024,week=1,aid='1',source_modified_at=pd.Timestamp('2024-09-08T16:00:00Z'),report_status='Out',practice_status='DNP'),
                        dict(team='NYG',season=2024,week=1,aid='2',source_modified_at=pd.Timestamp('2024-09-08T15:00:00Z'),report_status='Out',practice_status='DNP')])
        z=temporal_join(p,r)
        self.assertTrue((z.report_status=='UNKNOWN_NO_ELIGIBLE_ROW').all())
        self.assertTrue((z.team_report_evidence==0).all())
        r.loc[0,'source_modified_at']=pd.Timestamp('2024-09-08T15:59:59Z')
        z=temporal_join(p,r)
        self.assertEqual(z.iloc[0].report_status,'Out')
        self.assertEqual(z.iloc[1].report_status,'UNKNOWN_NO_ELIGIBLE_ROW')
    def test_names_teams(self):
        self.assertEqual(norm('Odell Beckham Jr.'),norm('Odell Beckham'))
        self.assertEqual(team('LAR'),'LA')

if __name__=='__main__':unittest.main()
