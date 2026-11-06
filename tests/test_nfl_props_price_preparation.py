"""Synthetic identity, distribution, timing and data-leak tests; no bookmaker data."""
import copy,datetime as dt,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import nfl_prop_identity as I
import nfl_props_price_match as M
import nfl_props_price_export as E

def row(name='Amon-Ra St. Brown',aid='00-1',team='DET',stat='receptions',position='WR',**kw):
    return {'name':name,'gsis_id':aid,'espn_id':'100','name_aliases':[],'team':team,'stat':stat,'position':position,**kw}

class IdentityTests(unittest.TestCase):
    def test_punctuation_diacritics_and_initials_within_full_name(self):
        self.assertEqual(I.player('Amon Ra St Brown','receptions',[row()])['gsis_id'],'00-1')
        self.assertEqual(I.player('AJ Brown','receptions',[row('A.J. Brown')])['status'],'matched')
        self.assertEqual(I.player('Jose Smith','receptions',[row('José Smith')])['status'],'matched')
        self.assertEqual(I.player('Brown, Amon-Ra St.','receptions',[row()])['status'],'matched')
    def test_suffixes_collisions_and_explicit_conflicts(self):
        a=row('Marvin Harrison Jr.')
        self.assertEqual(I.player('Marvin Harrison','receptions',[a])['status'],'matched')
        self.assertEqual(I.player('Marvin Harrison Sr','receptions',[a])['status'],'unmatched')
        self.assertEqual(I.player('Marvin Harrison','receptions',[a,row('Marvin Harrison Sr',aid='00-2')])['status'],'ambiguous')
    def test_no_fuzzy_surname_or_proprietary_numeric_key(self):
        self.assertEqual(I.player('St Brown','receptions',[row()])['status'],'unmatched')
        self.assertEqual(I.player('St Browne','receptions',[row()])['status'],'unmatched')
        self.assertEqual(I.player('','receptions',[row()])['status'],'missing_name')
        self.assertEqual(I.player('A. Brown','receptions',[row('AJ Brown')])['status'],'unmatched')
    def test_position_and_team_scoping(self):
        pool=[row('Josh Allen',stat='pass_attempts',position='QB'),row('Josh Allen',aid='00-2',stat='receptions',position='LB')]
        self.assertEqual(I.player('Josh Allen','pass_attempts',pool)['gsis_id'],'00-1')
        self.assertEqual(I.player('Josh Allen','receptions',pool)['status'],'unmatched')
        self.assertEqual(I.player('Josh Allen','pass_attempts',pool,team='Buffalo Bills')['status'],'unmatched')
    def test_given_id_does_not_override_conflicting_name(self):
        self.assertEqual(I.player('Someone Else','receptions',[row()],gsis_id='00-1')['status'],'id_name_conflict')
        self.assertEqual(I.player('Amon-Ra St. Brown','receptions',[row()],espn_id='100')['gsis_id'],'00-1')
    def test_fixed_nickname_alias(self):
        self.assertEqual(I.player('Hollywood Brown','receptions',[row('Marquise Brown')])['method'],'frozen_name_alias')
    def test_fixture_requires_two_teams_time_and_unique_match(self):
        game={'game_id':'2026_01_DET_LA','home':'LA','away':'DET','kickoff_utc':'2026-09-10T20:00Z'}
        self.assertEqual(I.fixture('Los Angeles Rams','Detroit Lions','2026-09-10T20:05Z',[game])['game_id'],game['game_id'])
        self.assertEqual(I.fixture('LA','DET','2026-09-10T20:16Z',[game])['status'],'unmatched_fixture')
        self.assertEqual(I.fixture('LA','DET','2026-09-10T20:00',[game])['status'],'invalid_time')
        self.assertEqual(I.fixture('LA','DET','2026-09-10T20:00Z',[game,game])['status'],'ambiguous_fixture')
    def test_line_probabilities_and_tail_boundary(self):
        pmf=[.1,.2,.3,.4]
        self.assertAlmostEqual(I.probabilities(pmf,1.5)['over'],.7)
        self.assertAlmostEqual(I.probabilities(pmf,1)['push'],.2)
        for line in (True,'1.5',3,3.5,-.5,float('nan')):
            with self.assertRaises(ValueError):I.probabilities(pmf,line)

class TimingTests(unittest.TestCase):
    def test_football_name_is_first_name_not_full_name_alias(self):
        ids=pd.DataFrame([{'gsis_id':'00-1','espn_id':'100','display_name':'Josh Allen','football_name':'Josh','first_name':'Joshua','common_first_name':'Josh','last_name':'Allen','suffix':None}])
        aliases=E.aliases(ids)['00-1']['name_aliases']
        self.assertNotIn('Josh',aliases);self.assertIn('Josh Allen',aliases);self.assertIn('Joshua Allen',aliases)
    def test_strict_six_hour_completion_lag(self):
        schedule=pd.DataFrame({'game_id':['a','b'],'kickoff':pd.to_datetime(['2026-09-10T12:00Z','2026-09-10T13:00Z'])})
        self.assertEqual(E.prior_games(schedule,pd.Timestamp('2026-09-10T18:00Z')),set())
        self.assertEqual(E.prior_games(schedule,pd.Timestamp('2026-09-10T18:01Z')),{'a'})
    def test_depth_at_cannot_use_future_roster(self):
        d=pd.DataFrame([{'team':'DET','dt':'2026-09-10T12:00Z','gsis_id':'a','pos_abb':'WR','pos_rank':1},
                        {'team':'DET','dt':'2026-09-10T13:00Z','gsis_id':'future','pos_abb':'WR','pos_rank':1}])
        d['dt']=pd.to_datetime(d.dt)
        self.assertEqual(E.depth_at(d,'DET',pd.Timestamp('2026-09-10T12:30Z')).gsis_id.tolist(),['a'])
    def test_export_preserves_original_pmf_and_flags_future_input(self):
        p={'player_id':'00-1','name':'A','position':'WR','availability_probability':.8,'stat':'receptions','pmf':[.5,.3,.2],'source_times':['2026-09-11T00:00Z']}
        snap={'generated_utc':'2026-09-10T12:00Z'};game={'home':'DET','away':'LA','teams':[{'team':'DET','players':[p]}]}
        before=copy.deepcopy(p)
        out=E.export_rows(snap,game,{'source_tier':'receipt_proved'},{})[0]
        self.assertEqual(p,before);self.assertEqual(out['pmf'],p['pmf']);self.assertFalse(out['primary_eligible'])
        self.assertEqual(out['distribution'],'conditional_on_appearance')

class JoinTests(unittest.TestCase):
    # Amendment 2 (6 Nov 2026): the line is the market's frozen numeric handicap; names come only from the key-to-name map.
    def _setup(self):
        f=row(game_id='g',horizon_minutes=60,source_tier='receipt_proved',primary_eligible=True,cutoff_utc='2026-09-10T19:00Z',pmf=[.2,.3,.5])
        game={'game_id':'g','home':'DET','away':'LA','kickoff_utc':'2026-09-10T20:00Z'}
        last,first=f['name'].split(' ',1)[1],f['name'].split(' ',1)[0]
        names={'777':{'name':f'{last}, {first}'}}
        quote={'home':'Detroit Lions','away':'Los Angeles Rams','start_time':game['kickoff_utc'],'market_id':'1','player_key':'777',
               'handicap':'1.5','gsis_id':'00-WRONG','espn_id':'999'}
        mapping={'1':{'scope':'full_game','stat':'receptions','line_field':'handicap','handicap':1.5}}
        return f,game,names,quote,mapping
    def test_numeric_handicap_and_last_first_name_resolve(self):
        f,game,names,quote,mapping=self._setup()
        result=list(M.join([quote],[f],[game],mapping,60,names))[0]
        self.assertEqual(result['status'],'matched');self.assertEqual(result['line_status'],'numeric_half_point')
        self.assertEqual(result['line'],1.5);self.assertEqual(result['p_over'],.5);self.assertEqual(result['gsis_id'],f['gsis_id'])
    def test_boolean_or_mismatched_handicap_rejected(self):
        f,game,names,quote,mapping=self._setup()
        for bad in (True,'True','2.5','',None,'1.0'):
            q=dict(quote,handicap=bad)
            self.assertEqual(list(M.join([q],[f],[game],mapping,60,names))[0]['status'],'market_handicap_mismatch',bad)
    def test_missing_name_and_unverified_market(self):
        f,game,names,quote,mapping=self._setup()
        self.assertEqual(list(M.join([dict(quote,player_key='888')],[f],[game],mapping,60,names))[0]['status'],'missing_player_name_map')
        self.assertEqual(list(M.join([quote],[f],[game],mapping,60,{}))[0]['status'],'missing_player_name_map')
        self.assertEqual(list(M.join([quote],[f],[game],{},60,names))[0]['status'],'unsupported_or_unverified_market')

if __name__=='__main__':unittest.main()
