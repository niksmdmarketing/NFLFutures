import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'pipeline'),str(ROOT/'research')]
import nba_award_sim as S
from nba_award_bugfix_compare import published_identity
class AwardBugfixTests(unittest.TestCase):
 def lines(self,gp=70,tg=82):
  r={'name':'Synthetic Player','team':'BOS','gp':gp,'tg':tg,'tw':tg*.6,'rookie':True,'wp':.6}
  for k in S.STATS:r[k]=gp*(30 if k=='mins' else 1 if k in ('m20','m15') else 0 if k=='start' else 10)
  return pd.DataFrame([r],index=[1])
 def test_flag_off_is_legacy_and_flag_on_is_unit_mass(self):
  prev=self.lines();a=S.preseason_pool(prev,'MVP');a['avail0']=.5;args=(a,prev,a,'MVP',S.SPECS['MVP'][3],np.zeros(6),82,2024)
  with patch.object(S,'SIMS',100),patch.object(S,'AVAIL_SD',.35),patch.object(S,'BUGFIXES',False):
   old=S.simulate(*args,pre=True);self.assertEqual(old,S.simulate(*args,pre=True,replay=False));self.assertLess(sum(old.values()),1)
  with patch.object(S,'SIMS',100),patch.object(S,'AVAIL_SD',.35),patch.object(S,'BUGFIXES',True):
   fixed=S.simulate(*args,pre=True);self.assertAlmostEqual(sum(fixed.values()),1)
 def test_rookie_and_sixth_man_not_given_sixty_five_game_rule(self):
  a=self.lines(50);D=a.assign(**S.features(a,82));D['bench']=True
  with patch.object(S,'SIMS',3),patch.object(S,'BUGFIXES',True):
   for award in ('ROY','6MOY'):
    self.assertAlmostEqual(sum(S.simulate(a,a,D,award,S.SPECS[award][3],np.zeros(len(S.SPECS[award][3])),82,2024).values()),1)
   self.assertEqual(S.simulate(a,a,D,'MVP',S.SPECS['MVP'][3],np.zeros(6),82,2024),{})
 def test_known_published_comparison_rejects_wrong_rank_or_probability(self):
  x={'awards':{a:{'current':[{'name':'A','prob':.6}]} for a in ('MVP','DPOY','ROY','6MOY')}}
  self.assertTrue(published_identity(x,x)['top15_names_identical'])
  import copy
  y=copy.deepcopy(x);y['awards']['MVP']['current'][0]['prob']=.61
  with self.assertRaises(ValueError):published_identity(x,y)
 def test_no_rejected_shrink_layer_in_live_candidate(self):
  source=(ROOT/'pipeline/nba_award_sim.py').read_text(encoding='utf-8')
  self.assertNotIn('AW_EARLY',source);self.assertNotIn('Lc / 20',source)
if __name__=='__main__':unittest.main()
