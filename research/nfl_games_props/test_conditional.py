import unittest
import numpy as np
import conditional_engine as E

class ConditionalTests(unittest.TestCase):
    def test_integer_and_half_point_lines(self):
        p=np.array([.2,.3,.5])
        self.assertEqual(E.line_probabilities(p,1.),dict(line=1.,over=.5,under=.2,push=.3))
        x=E.line_probabilities(p,.5);self.assertAlmostEqual(x['over'],.8);self.assertEqual(x['push'],0)
        self.assertAlmostEqual(x['over']+x['under']+x['push'],1)

    def test_explicit_budget_and_disabled_role(self):
        rows=[dict(aid='a',default_target_share=.6,target_share_override=.7),
              dict(aid='b',default_target_share=.6,target_share_override=None),
              dict(aid='new',default_target_share=.2,include_projection=False)]
        enabled,b=E.target_budget(rows)
        self.assertEqual(len(enabled),2);self.assertAlmostEqual(sum(x['effective_target_share'] for x in enabled),1)
        self.assertEqual(enabled[0]['effective_target_share'],.7)
        rows[1]['target_share_override']=.5
        with self.assertRaises(ValueError):E.target_budget(rows)

    def test_disabling_does_not_reallocate(self):
        rows=[dict(aid='a',default_target_share=.3),dict(aid='b',default_target_share=.2,assumed_playing=False)]
        enabled,b=E.target_budget(rows)
        self.assertEqual(len(enabled),1);self.assertEqual(enabled[0]['effective_target_share'],.3)
        self.assertAlmostEqual(b['unallocated_target_share'],.7)

    def test_starting_role_and_receiving_pmfs(self):
        v=np.zeros(101);v[0]=.1;v[35]=.9
        q=E.starting_qb(v,dict(share=.94,concentration=4))
        r=E.receiving(v,.2,.7,50)
        self.assertAlmostEqual(q.sum(),1);self.assertAlmostEqual(r.sum(),1)
        self.assertTrue((q[36:]==0).all());self.assertTrue((r[36:]==0).all())
        self.assertAlmostEqual(float(q@np.arange(101)),.9*35*.94)
        self.assertAlmostEqual(float(r@np.arange(41)),.9*35*.2*.7)
        self.assertAlmostEqual(E.describe(q)['mean'],float(q@np.arange(101)))

if __name__=='__main__':unittest.main()
