import unittest
import numpy as np
import pandas as pd
from receiver_allocation_test import conditional_scales


class AllocationTests(unittest.TestCase):
    def test_focal_is_certain_only_in_own_denominator(self):
        z=pd.DataFrame(dict(game_id=['g']*3,team=['T']*3))
        shares=np.array([.4,.3,.2]);prob=np.array([.2,.5,.8])
        scale,den=conditional_scales(z,shares,prob)
        expected=np.array([.4+.5*.3+.8*.2,.2*.4+.3+.8*.2,.2*.4+.5*.3+.2])
        np.testing.assert_allclose(den,expected)
        np.testing.assert_allclose(scale,np.minimum(1,1/expected))

    def test_other_games_and_teams_do_not_mix(self):
        z=pd.DataFrame(dict(game_id=['g','g','h'],team=['T','U','T']))
        shares=np.array([.7,.7,.7]);prob=np.array([.5,.5,.5])
        scale,den=conditional_scales(z,shares,prob)
        np.testing.assert_allclose(den,[.7,.7,.7])
        np.testing.assert_allclose(scale,[1,1,1])


if __name__=='__main__':unittest.main()
