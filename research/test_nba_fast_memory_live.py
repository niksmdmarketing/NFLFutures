"""Research-only runtime regressions; run unittest discover -s research -p test_nba_fast_memory_live.py."""
import copy, gzip, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import nba_fast_memory_live as L
import nba_props_live_core as C
import nba_props_repair as R
import nba_props_simple_test as P
import nba_fast_memory_audit as A

ROOT=Path(__file__).resolve().parents[1]


class LiveTests(unittest.TestCase):
    def fixture(self):
        f=json.loads((ROOT/'model/nba_props_live_params_2027b.json').read_text())
        p=json.loads((L.HERE/'nba_fast_memory_params_2027.json').read_text())
        z=pd.DataFrame(dict(game_id=[1],season=[2027],team=['A'],aid=[7],tip=['2026-10-23T23:00:00Z'],
            mu1=[24.],ewm=[24.],season_mpg=[24.],vac_same1=[0.],vac_other1=[0.],st1=[''],
            absm=[5.],b2b=[0.],s_sum=[1.],s_cnt=[10.],early=[0.],streak=[0.],start10=[.5],
            pa1=[.9],grp=['W'],h_M=[100.],h_reb=[15.],h_ast=[10.],h_pm_pace=[10000.],
            V_now1_ast=[0.],V_ref_ast=[0.],opp_reb=[1.],pace_exp=[100.],
            n_cur=[2],n_prv=[0],reb_cur=[6],ast_cur=[4],reb_prv=[0],ast_prv=[0]))
        h=pd.DataFrame(dict(season=[2027]*3,aid=[7]*3,tip=pd.date_range('2026-10-15',periods=3,tz='UTC'),minutes=[20.,25.,30.]))
        q,_=C.q_m2(z,f['m2'],True)
        player=dict(aid=7,team='A',name='Test',status='',p_appear=.9,minutes_v3=q[0].tolist())
        for stat in ('reb','ast'):
            rate,disp=C.prop_rate(z,stat,f['props'])
            pm=P.mixture_pmf(rate,q,disp,P.SUP_FULL[stat])[0]*.9;pm[0]+=.1
            player[stat+'_v3']=pm.tolist()
        primary=dict(game_id=1,horizon_min=60,cutoff_utc='2026-10-23T22:00:00Z',
            forecast_finished_utc='2026-10-23T21:30:00Z',code_commit='test',params_id='b',inputs={},players=[player])
        return primary,z,h,f,p

    def test_pair_and_primary_unchanged(self):
        r,z,h,f,p=self.fixture(); before=copy.deepcopy(r)
        s=L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')
        self.assertEqual(r,before);self.assertTrue(s['pair_check']['same_players'])
        self.assertEqual(s['players'][0]['reb_calibration_line'],3.5)
        for stat in ('reb','ast'):
            self.assertAlmostEqual(sum(s['players'][0][stat+'_including_dnp_zero']),1)

    def test_activation_and_late_rejected(self):
        r,z,h,f,p=self.fixture()
        self.assertIsNone(L.build_record(r,z,h,f,p,'2026-10-23T14:59:00Z'))
        with self.assertRaises(ValueError):L.build_record(r,z,h,f,p,'2026-10-23T22:01:00Z')

    def test_pair_mismatch_rejected(self):
        r,z,h,f,p=self.fixture();r['players'][0]['p_appear']=.8
        with self.assertRaisesRegex(ValueError,'appearance mismatch'):L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')

    def test_target_placeholders_are_not_history_observations(self):
        r,z,h,f,p=self.fixture()
        expected=L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')
        placeholders=pd.DataFrame(dict(season=[2027,2027],aid=[7,-1],
            tip=['2026-10-23T23:00:00Z','2026-10-24T01:00:00Z'],minutes=[0.,0.]))
        combined=pd.concat([h,placeholders],ignore_index=True)
        # The old hook failed here before the fast-input code could discard zeros.
        bad=combined.copy();bad['observed_at_utc']=r['forecast_finished_utc']
        with self.assertRaisesRegex(ValueError,'Invalid observed-history timing'):
            L.S.make_shadow(z,bad,f,p,r['cutoff_utc'],'2026-10-23T21:31:00Z',replay=False)
        before=copy.deepcopy(r)
        actual=L.build_record(r,z,combined,f,p,'2026-10-23T21:31:00Z')
        self.assertEqual(actual['players'],expected['players'])
        self.assertEqual(actual['history_filter'],dict(input_rows=5,positive_appearances=3,nonappearance_rows_removed=2))
        self.assertEqual(r,before)

    def test_future_positive_history_still_rejected(self):
        r,z,h,f,p=self.fixture()
        h=pd.concat([h,pd.DataFrame(dict(season=[2027],aid=[7],tip=['2026-10-23T23:00:00Z'],minutes=[10.]))],ignore_index=True)
        with self.assertRaisesRegex(ValueError,'Invalid observed-history timing'):
            L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')

    def test_missing_negative_and_nonfinite_history_rejected(self):
        for value in (np.nan,np.inf,-1.):
            r,z,h,f,p=self.fixture();h.loc[0,'minutes']=value
            with self.assertRaisesRegex(ValueError,'Invalid minutes'):
                L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')

    def test_observation_after_capture_still_rejected(self):
        r,z,h,f,p=self.fixture();r['forecast_finished_utc']='2026-10-23T21:32:00Z'
        with self.assertRaisesRegex(ValueError,'Invalid observed-history timing'):
            L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')

    def test_blob_create_only_and_corruption(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            h=L._store_blob(d,b'original','json')
            self.assertEqual(h,L._store_blob(d,b'original','json'))
            path=Path(d)/'nba/props_forward/inputs'/(h+'.json');path.write_bytes(b'wrong')
            with self.assertRaises(ValueError):L._store_blob(d,b'original','json')

    def test_live_archive_separate_and_immutable(self):
        r,z,h,f,p=self.fixture()
        from datetime import datetime,timezone
        fake=datetime(2026,10,23,21,31,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            path=Path(d)/'nba/props_forward/2026-10-23/1_60.json.gz';path.parent.mkdir(parents=True)
            path.write_bytes(gzip.compress(json.dumps(r).encode(),mtime=0));raw=path.read_bytes()
            with patch.object(L,'datetime') as clock:
                clock.now.return_value=fake
                dest=L.archive_challenger(d,path,r,z,h,f)
                self.assertIn('/challengers/',Path(dest).as_posix())
                s=json.loads(gzip.decompress(Path(dest).read_bytes()))
                self.assertEqual(s['primary_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertTrue(s['locally_on_time'])
                with self.assertRaises(FileExistsError):L.archive_challenger(d,path,r,z,h,f)
            self.assertEqual(path.read_bytes(),raw)

    def test_auditor_requires_own_receipt(self):
        r,z,h,f,p=self.fixture()
        s=L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')
        raw=json.dumps(r).encode(); s.update(primary_sha256=hashlib.sha256(raw).hexdigest(),forecast_finished_utc='2026-10-23T21:31:05Z')
        valid={'errors':[],**{k:r[k] for k in ('game_id','horizon_min','cutoff_utc')}}
        self.assertEqual(A.timing_errors(s,'2026-10-23T21:31:10Z',valid,raw),[])
        self.assertIn('no_on_time_independent_receipt',A.timing_errors(s,None,valid,raw))
        self.assertIn('no_on_time_independent_receipt',A.timing_errors(s,'2026-10-23T22:01:00Z',valid,raw))

    def test_auditor_rejects_wrong_primary_and_replay(self):
        r,z,h,f,p=self.fixture()
        s=L.build_record(r,z,h,f,p,'2026-10-23T21:31:00Z')
        s.update(primary_sha256='wrong',forecast_finished_utc='2026-10-23T21:31:05Z',replay=True)
        errors=A.timing_errors(s,'2026-10-23T21:31:10Z',{'errors':['late']},b'original')
        self.assertTrue({'wrong_model_or_replay','invalid_primary','primary_bytes_mismatch'}.issubset(errors))


if __name__=='__main__':unittest.main()
