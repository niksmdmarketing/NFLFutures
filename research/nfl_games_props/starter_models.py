"""Dated roster evidence, explicit new-QB fallback and provenance-checked signals."""
import bisect
import numpy as np
import pandas as pd
from scipy.special import expit,logit
from scipy.optimize import minimize_scalar
import core as C

class DepthIndex:
    def __init__(self,d):
        d=d.copy();d['team']=d.team.replace(C.FIX);d['time']=pd.to_datetime(d.dt,utc=True,errors='coerce')
        d=d[(d.pos_abb=='QB')&d.time.notna()&d.gsis_id.notna()]
        self.groups={};self.times={}
        for t,z in d.groupby('team'):
            groups=[]
            for time,g in z.groupby('time'):
                # Duplicate formations do not create duplicate candidates.
                g=g.sort_values('pos_rank').drop_duplicates('gsis_id')
                groups.append((time,g.copy()))
            groups.sort(key=lambda x:x[0]);self.groups[t]=groups;self.times[t]=[x[0].value for x in groups]

    def at(self,t,cutoff):
        cutoff=pd.Timestamp(cutoff);j=bisect.bisect_left(self.times.get(t,[]),cutoff.value)-1
        if j<0:return None,'missing'
        tm,g=self.groups[t][j]
        if cutoff-tm>pd.Timedelta(hours=72):return None,'stale'
        return g,'eligible'

def signals(rows):
    if rows is None:return {}
    first=rows[rows.pos_rank==1]
    if len(first)!=1:return {r.gsis_id:0. for r in rows.itertuples()}
    return {r.gsis_id:1. if r.pos_rank==1 else -1. for r in rows.itertuples()}

def fallback(teamrow,aid,name,prior_stats,prior_snaps):
    """Caller supplies only already-available history. No target labels inspected."""
    t=teamrow['team'];season=int(teamrow['season']);cut=pd.Timestamp(teamrow['tip'])-pd.Timedelta(hours=1)
    old=prior_stats[(prior_stats.aid==aid)&(prior_stats.season>=season-1)&(prior_stats.ready<cut)].sort_values('ready').tail(8)
    snaps=prior_snaps[(prior_snaps.aid==aid)&(prior_snaps.ready<cut)&(prior_snaps.season>=season-1)].sort_values('ready').tail(8)
    weight=.5**(np.arange(len(old))[::-1]/4)
    den=float(weight@old.team_attempts.to_numpy()) if len(old) else 0.
    attempts=float(weight@old.attempts.to_numpy()) if len(old) else 0.
    same=snaps[snaps.team==t]
    return dict(game_id=teamrow['game_id'],team=t,aid=aid,name=name,position='QB',is_qb=1,season=season,
        week=teamrow['week'],tip=teamrow['tip'],h_attempts=attempts,h_team_att=den,h_targets=0.,h_receptions=0.,
        avg_attempts=float(old.attempts.mean()) if len(old) else 0.,
        app_rate=.5 if same.empty else float((same.offense_snaps>0).mean()),
        last_snap_share=float(same.offense_pct.iloc[-1]) if len(same) else 0.,
        mean_snap_share=float(same.offense_pct.mean()) if len(same) else 0.,miss_streak=0,
        report_status='UNKNOWN_NO_ELIGIBLE_ROW',practice_status='UNKNOWN_NO_ELIGIBLE_ROW',team_report_evidence=0,
        added_candidate=True,fallback_history_games=len(old))

def shifted_probability(p,signal,beta):
    return expit(logit(np.clip(np.asarray(p,float),1e-5,1-1e-5))+float(beta)*np.asarray(signal,float))

def fit_depth(p,signal,y):
    p=np.asarray(p,float);signal=np.asarray(signal,float);y=np.asarray(y,float)
    def loss(beta):
        q=np.clip(shifted_probability(p,signal,beta),1e-8,1-1e-8)
        return float(-np.sum(y*np.log(q)+(1-y)*np.log1p(-q))+beta**2/(2*.5**2))
    fit=minimize_scalar(loss,bounds=(0,4),method='bounded')
    return float(fit.x)

def confirmed_signal(record,game_id,t,aid,cutoff,out=False):
    """Reject missing provenance, generic availability, late news and conflicts."""
    if not record or record.get('status')!='confirmed_starter':return None,'not_confirmed_starter'
    if (record.get('game_id'),record.get('team'),record.get('aid'))!=(game_id,t,aid):return None,'wrong_game_team_or_player'
    if not str(record.get('source_url','')).startswith('https://'):return None,'missing_source'
    observed=pd.to_datetime(record.get('version_observed_at_utc'),utc=True,errors='coerce')
    if pd.isna(observed) or observed>=pd.Timestamp(cutoff):return None,'late_or_unknown_version_time'
    if out:return None,'conflict_with_out'
    return 1.,'confirmed_record_eligible'
