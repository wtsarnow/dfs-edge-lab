#!/usr/bin/env python3
"""analyze.py - Pattern Lab + My FanDuel + Bot Impact datasets. Idempotent; run after enrich.py.
Outputs: patterns.json, entries.json, bots.json, data/*.csv"""
import json, os, re, csv, glob, math
import pandas as pd, numpy as np
from scipy import stats
W='/workspace'; ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.makedirs(f'{ROOT}/data',exist_ok=True)
R=pd.DataFrame(json.load(open(f'{ROOT}/players.json'))['rows'])
SIG=['salary','proj','own','implied_total','total_line','spread','moneyline','win_prob_ml','rest_days','opp_def_rank','opp_pos_pts_allowed',
 'temp_f','wind_mph','travel_mi','tz_shift','wiki_views_7d','wiki_spike','wiki_d1','wiki_z','trends_rel','snap_pct','targets','target_share',
 'air_yards','air_yards_share','wopr','adot','rz_targets','ez_targets','deep_tgts','contested_tgts','catchable_tgts','drops','carries','rz_carries',
 'gl_carries','rz_touches','neutral_pass_rate','pass_oe','sec_per_play','team_plays','play_action_rate','team_epa_play','cpoe','blitz_rate_faced','salary_chg']
SAME_GAME={'snap_pct','targets','target_share','air_yards','air_yards_share','wopr','adot','rz_targets','ez_targets','deep_tgts','contested_tgts','catchable_tgts','drops','carries','rz_carries','gl_carries','rz_touches','neutral_pass_rate','pass_oe','sec_per_play','team_plays','play_action_rate','team_epa_play','cpoe','blitz_rate_faced'}
CTX=['rain_mm','rain_flag','heat_flag','cold_flag','days_rest','opp_days_rest','rest_diff','short_week','off_bye','vs_opp_games','vs_opp_avg_fd','vs_opp_diff','team_h2h_games','team_h2h_winpct','spread_team','total_vegas','implied_team','opp_dvp','travel_miles','east_1pm_west_team','altitude_ft','turf_n','last3_avg_fd','snap_trend3','tgt_share_trend3','teammate_out','revenge_game','season_avg_td']
for c in CTX:
    if c not in R: R[c]=None
SIG+=CTX
for b in ['primetime','dome','div_game','home']: R[b+'_n']=R[b].map(lambda v: None if v is None else float(bool(v))); SIG.append(b+'_n')
# residual vs position + implied total (what Vegas+position can't explain)
R['fd_resid']=np.nan
m=R.fd_pts.notna()&R.implied_total.notna()
for pos,d in R[m].groupby('pos'):
    if len(d)>10:
        sl,ic,*_=stats.linregress(d.implied_total,d.fd_pts); R.loc[d.index,'fd_resid']=d.fd_pts-(ic+sl*d.implied_total)
R['boom_n']=R.boom.map(lambda v: None if v is None or (isinstance(v,float) and math.isnan(v)) else float(v))
OUT=['fd_pts','fd_resid','pts_per_1k','beat_proj','boom_n']
def corr(x,y):
    d=pd.DataFrame({'x':pd.to_numeric(x,errors='coerce'),'y':pd.to_numeric(y,errors='coerce')}).dropna()
    if len(d)<12 or d.x.nunique()<3 and d.x.nunique()!=2: return None
    if d.x.std()==0 or d.y.std()==0: return None
    r,p=stats.pearsonr(d.x,d.y); rho,_=stats.spearmanr(d.x,d.y); return len(d),r,p,rho
P=[]
for pos in ['ALL','QB','RB','WR','TE','DST']:
    d=R if pos=='ALL' else R[R.pos==pos]
    for s in SIG:
        for o in OUT:
            c=corr(d[s],d[o])
            if c: P.append(dict(pos=pos,signal=s,outcome=o,n=c[0],r=round(c[1],3),rho=round(c[3],3),p=float(f'{c[2]:.3g}'),
               same_game=s in SAME_GAME,small_n=c[0]<100))
P=pd.DataFrame(P)
# Benjamini-Hochberg q
P=P.sort_values('p'); k=np.arange(1,len(P)+1); q=(P.p*len(P)/k)[::-1].cummin()[::-1].clip(upper=1); P['q']=q.round(4)
KNOWN={'salary','proj','own','implied_total','total_line','spread','moneyline','win_prob_ml','wiki_views_7d'}
def obvious(r): return r.signal in KNOWN and r.outcome!='beat_proj'
P['novelty']=P.apply(lambda r:'obvious' if obvious(r) else ('in-game (descriptive, not predictive)' if r.same_game else 'pre-game (predictive)'),axis=1)
ranked=P[(P.p<0.05)].copy(); ranked['abs_r']=ranked.r.abs()
ranked=ranked.sort_values(['novelty','abs_r'],ascending=[False,False])
# categorical: referee, surface, coach, stadium on residual
cat=[]
for c in ['referee','surface','roof','weekday','slate','coach','kick_slot']:
    d=R[[c,'fd_resid']].dropna()
    grp=[g.fd_resid.values for _,g in d.groupby(c) if len(g)>=15]
    if len(grp)>=2:
        F,p=stats.f_oneway(*grp)
        by=d.groupby(c).fd_resid.agg(['mean','count']).reset_index().sort_values('mean',ascending=False)
        cat.append(dict(factor=c,groups=len(grp),F=round(F,3),p=float(f'{p:.3g}'),levels=[dict(level=r[c],mean_resid=round(r['mean'],3),n=int(r['count'])) for _,r in by.iterrows()]))
# unusual highlights: pre-game, non-obvious, p<0.05
unusual=ranked[(ranked.novelty=='pre-game (predictive)')].head(15)
# positional bucket splits for fd_resid
buckets=[]
for s,cuts in [('wiki_z',[-99,0,1,2,99]),('travel_mi',[-1,0,500,1500,9999]),('tz_shift',[-4,-1,0,1,4]),('wind_mph',[-1,5,10,15,99]),('rest_days',[0,6,7,9,30]),('opp_pos_pts_allowed',[0,5,10,15,99])]:
    d=R[[s,'fd_resid','pos']].dropna()
    if len(d)<30: continue
    d['b']=pd.cut(d[s],cuts).astype(str)
    for (pos,b),g in d.groupby(['pos','b']):
        if len(g)>=8: buckets.append(dict(signal=s,pos=pos,bucket=b,n=len(g),mean_resid=round(g.fd_resid.mean(),3)))
json.dump(dict(signals=SIG,outcomes=OUT,all=P.drop(columns=[]).to_dict('records'),ranked=ranked.head(60).drop(columns='abs_r').to_dict('records'),
  context_signals=CTX+['temp_f','wind_mph','primetime_n','div_game_n','home_n'],categorical=cat,unusual=unusual.drop(columns='abs_r').to_dict('records'),buckets=buckets,
  notes=['fd_resid = FD points minus a per-position linear fit on the Vegas implied team total (what Vegas and position do not explain).',
         'q = Benjamini-Hochberg false-discovery-adjusted p across every test run; treat q>0.10 as unconfirmed.',
         'In-game signals (snaps, targets, EPA) describe the same game and are not usable before lock; pre-game signals are.',
         'small_n = fewer than 100 rows.']),open(f'{ROOT}/patterns.json','w'),separators=(',',':'),default=float)
PJ=json.load(open(f'{ROOT}/players.json'))
for row,(_,x) in zip(PJ['rows'],R.iterrows()):
    row['fd_resid']=None if pd.isna(x.fd_resid) else round(float(x.fd_resid),3); row['boom_n']=None if pd.isna(x.boom_n) else float(x.boom_n)
    for b in ['primetime','dome','div_game','home']: row[b+'_n']=None if pd.isna(x[b+'_n']) else float(x[b+'_n'])
json.dump(PJ,open(f'{ROOT}/players.json','w'),separators=(',',':'))
P.to_csv(f'{ROOT}/data/pattern_tests.csv',index=False); R.drop(columns=['boom_n']).to_csv(f'{ROOT}/data/player_games.csv',index=False)
# entries
Wk=json.load(open(f'{ROOT}/weeks.json')); E=[]
for w in Wk['weeks']:
    for e in w['entries']:
        r=dict(week=w['week'],**{k:v for k,v in e.items() if k!='lineup'}); r['lineup']='; '.join(e['lineup']) if isinstance(e.get('lineup'),list) else e.get('lineup')
        r['type']='Showdown' if re.search(r'Showdown|Thu|Monday|MNF|TNF|SNF|Primetime|Night',str(e.get('contest'))+str(e.get('slate'))) and 'Classic' not in str(e.get('contest')) else 'Classic'
        f=e.get('fee'); r['fee_tier']='free' if f==0 else ('n/a' if f is None else ('<$1' if f<1 else ('$1-$5' if f<=5 else '$6+')))
        r['roi']=round((e['winnings']-f)/f*100,1) if f and e.get('winnings') is not None else None
        r['beat80']=(e['pct']>=80) if e.get('pct') is not None else None
        r['mock']=bool(e.get('estimated')) or 'mock' in str(e.get('contest')).lower() or 'mock' in str(e.get('note','')).lower()
        E.append(r)
json.dump(dict(entries=E,autotune=Wk['autotune_history']),open(f'{ROOT}/entries.json','w'),indent=0)
pd.DataFrame(E).to_csv(f'{ROOT}/data/entries.csv',index=False)
# pick impact: players in our lineups -> pts vs salary expectation
pk=R[R.our_lineups.notna()&(R.our_lineups>0)][['week','player','team','pos','salary','fd_pts','proj','pts_per_1k','our_lineups','fd_resid']]
pk.to_csv(f'{ROOT}/data/pick_impact.csv',index=False)
# Bot Impact: historical accuracy from saved records
B=[]
def csvrows(p):
    p=f'{W}/{p}'; return list(csv.DictReader(open(p))) if os.path.exists(p) else []
er=[r for r in csvrows('epa-calibration.csv') if r['actual']]
gs=[r for r in csvrows('game-script-calibration.csv') if r.get('actual_bucket')]
pr=R[R.proj.notna()&R.fd_pts.notna()]
own=R[R.own.notna()]
patch=[l for l in open(f'{W}/fd-patch-log.md').read().splitlines()[2:] if '|' in l]
led=[l for l in open(f'{W}/fd-beat80-ledger.md').read().splitlines() if l.startswith('| 2026')]
fc=csvrows('fd-field-calibration.csv'); sc=csvrows('sim_calibration.csv')
ab=pd.read_csv(f'{ROOT}/bot_ablation.csv') if os.path.exists(f'{ROOT}/bot_ablation.csv') else None
def abl(bot):
    if ab is None: return []
    return ab[ab.bot==bot].fillna('').to_dict('records')
BOTS=[
 ('fanduel','Orchestrator: builds every slate lineup, coordinates specialists, applies auto-tune/BEAT_80 rules.',None,
   dict(records=f'{len(led)} ledger rows (fd-beat80-ledger.md)',hit=f"{sum('YES' in l for l in led)} BEAT_80 YES of {sum(('YES' in l) or ('| NO' in l) for l in led)} decided")),
 ('fanduel-projections','Median/ceiling/floor per player (fd-proj/*.csv).','projections',
   dict(records=f'{len(pr)} graded player projections',hit=f"r={pr.proj.corr(pr.fd_pts):.3f}, MAE={(pr.proj-pr.fd_pts).abs().mean():.2f} pts, beat-proj rate {(pr.fd_pts>pr.proj).mean()*100:.0f}%") if len(pr) else None),
 ('fanduel-salaries','Verified FD salary board + FD injury tags (w8-mocks/board_135562.csv).',None,dict(records='Board is the optimizer\'s required universe; no ablation possible (no lineup without salaries).',hit=None)),
 ('fanduel-ownership','Ownership bands (MODEL) and chalk/leverage flags.','ownership',
   dict(records=f'{len(own)} player-games carry a model ownership; ownership-calibration.md has 0 graded rows',hit='No actual FD ownership saved to grade against')),
 ('fanduel-injury-report','Final designations, play likelihood, beneficiary bumps (w8-main/injuries.md).','injury',dict(records='No saved call-vs-outcome log',hit=None)),
 ('fanduel-weather','Wind/temp/precip by stadium (weather/*.md).',None,dict(records='Saved Week 6 notes only; no Week 8 output, so no ablation; no graded log',hit=None)),
 ('fanduel-odds','Vegas consensus, implied team totals, line moves (w8-main/odds.md).','odds',dict(records='No saved graded log of line calls',hit=None)),
 ('fanduel-game-script','Script buckets (grind/balanced/shootout) and total bands.','game-script',
   dict(records=f'{len(gs)} graded games (game-script-calibration.csv)',hit=f"bucket hit {sum(r['pred_top_bucket']==r['actual_bucket'] for r in gs)}/{len(gs)}, total inside p10-p90 {sum(r['in_p10_p90']=='yes' for r in gs)}/{len(gs)}" if gs else None)),
 ('fanduel-offense-overall','Team EPA/play median with bands, target/air/RZ shares (w8-main/offense.md).','offense-overall',
   dict(records=f'{len(er)} graded team-games (epa-calibration.csv)',hit=f"inside band {sum(r['inside_band']=='Y' for r in er)}/{len(er)}, MAE {np.mean([abs(float(r['median'])-float(r['actual'])) for r in er]):.3f} EPA/play" if er else None)),
 ('fanduel-late-news','Last-minute inactives and lock-flip checks.',None,dict(records='No saved structured outputs in /workspace (only inactives notes, e.g. *-inactives-*.md); not graded',hit=None)),
 ('fanduel-simulator','Monte-Carlo sim medians/value (sim_w8main/).','simulator',dict(records=f'sim_calibration.csv has {len(sc)} graded rows',hit=None)),
 ('fanduel-field-payout','Contest field size, cash lines, payout structure.',None,dict(records=f'{len(fc)} contests in fd-field-calibration.csv (field reference data, not predictions)',hit=None)),
 ('fanduel-contest-results','Pulls official rank/field/percentile from FanDuel History.',None,dict(records=f'{sum("OFFICIAL" in l for l in led)} OFFICIAL results recorded in the ledger',hit=None)),
 ('fanduel-review','Weekly grading and patch proposals (fd-patch-log.md).',None,
   dict(records=f'{len(patch)} patches logged',hit=f"applied {sum('| yes |' in l for l in patch)}, proposals {sum('PROPOSAL' in l for l in patch)}, retired {sum(l.startswith('RETIRED') for l in patch)}; results: {sum('matched' in l or 'fixed' in l for l in patch)} confirmed, rest pending")),
]
for name,role,key,h in BOTS:
    B.append(dict(bot=name,role=role,ablation_input=key,ablation=abl(name),history=h,
      patches=[l for l in patch] if name=='fanduel-review' else []))
json.dump(dict(bots=B,epa=er,game_script=gs,proj_accuracy=pr.groupby('pos').apply(lambda d:dict(n=len(d),mae=round((d.proj-d.fd_pts).abs().mean(),2),r=round(d.proj.corr(d.fd_pts),3) if len(d)>2 else None)).to_dict()),open(f'{ROOT}/bots.json','w'),indent=0,default=str)
print('tests',len(P),'sig',len(ranked),'q<.1',int((P.q<.1).sum()))
print(unusual[['pos','signal','outcome','n','r','p','q']].head(12).to_string())
print(ranked[ranked.novelty!='obvious'][['pos','signal','outcome','n','r','p','q','novelty']].head(8).to_string())
for c in cat: print(c['factor'],c['p'],c['levels'][:2])
