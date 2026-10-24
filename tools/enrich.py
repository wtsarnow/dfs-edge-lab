#!/usr/bin/env python3
"""enrich.py - add nflverse/Vegas/travel/officials/FTN/stack signals to players.json (idempotent).
Run after collect_signals.py. Real sources only; missing => null.
  pbp        : /workspace/pbp/pbp26.csv.gz (nflverse play-by-play)
  games      : /workspace/pbp/games.csv (lines, moneylines, wind, surface, coaches, stadium)
  snaps      : tools/cache/nflverse/snap_counts_2026.csv
  ftn        : tools/cache/nflverse/ftn_charting_2026.csv
  officials  : tools/cache/nflverse/officials.csv (referee = crew chief)
  stadium coords: STAD below (public stadium locations)
Refresh nflverse caches: python3 tools/enrich.py --download
"""
import json, os, sys, math, re, subprocess, argparse
import pandas as pd, numpy as np
W='/workspace'; ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NV=f'{ROOT}/tools/cache/nflverse'
sys.path.insert(0,W); import fdscore
norm=fdscore.norm
# team home stadium lat, lon, utc offset (standard time) -- public stadium locations
STAD={'ARI':(33.528,-112.263,-7),'ATL':(33.755,-84.401,-5),'BAL':(39.278,-76.623,-5),'BUF':(42.774,-78.787,-5),
'CAR':(35.226,-80.853,-5),'CHI':(41.862,-87.617,-6),'CIN':(39.095,-84.516,-5),'CLE':(41.506,-81.700,-5),
'DAL':(32.748,-97.093,-6),'DEN':(39.744,-105.020,-7),'DET':(42.340,-83.046,-5),'GB':(44.501,-88.062,-6),
'HOU':(29.685,-95.411,-6),'IND':(39.760,-86.164,-5),'JAX':(30.324,-81.637,-5),'KC':(39.049,-94.484,-6),
'LV':(36.091,-115.184,-8),'LAC':(33.953,-118.339,-8),'LA':(33.953,-118.339,-8),'MIA':(25.958,-80.239,-5),
'MIN':(44.974,-93.258,-6),'NE':(42.091,-71.264,-5),'NO':(29.951,-90.081,-6),'NYG':(40.813,-74.074,-5),
'NYJ':(40.813,-74.074,-5),'PHI':(39.901,-75.168,-5),'PIT':(40.447,-80.016,-5),'SF':(37.403,-121.970,-8),
'SEA':(47.595,-122.332,-8),'TB':(27.976,-82.503,-5),'TEN':(36.166,-86.771,-6),'WAS':(38.908,-76.864,-5)}
def hav(a,b):
    R=3958.8;la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]])
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return round(2*R*math.asin(math.sqrt(h)))
def clean(v):
    if v is None: return None
    if isinstance(v,(np.floating,float)):
        return None if (isinstance(v,float) and math.isnan(v)) or np.isnan(v) else round(float(v),4)
    if isinstance(v,(np.integer,)): return int(v)
    if isinstance(v,np.bool_): return bool(v)
    return v
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--download',action='store_true'); a=ap.parse_args()
    if a.download:
        for u in ['snap_counts/snap_counts_2026.csv','ftn_charting/ftn_charting_2026.csv','officials/officials.csv']:
            subprocess.run(['curl','-sL','-o',f'{NV}/'+u.split('/')[1],'https://github.com/nflverse/nflverse-data/releases/download/'+u])
    D=json.load(open(f'{ROOT}/players.json')); rows=D['rows']
    pbp=pd.read_csv(f'{W}/pbp/pbp26.csv.gz',low_memory=False)
    G=pd.read_csv(f'{W}/pbp/games.csv'); G=G[G.season==2026].set_index('game_id')
    ros=pd.read_csv(f'{W}/rosters2026.csv',low_memory=False).drop_duplicates('gsis_id')
    idname={r.gsis_id:r.full_name for r in ros.itertuples()}
    # officials
    off=pd.read_csv(f'{NV}/officials.csv'); off=off[(off.season==2026)&(off.position=='Referee')]
    ref_by_old={str(r.game_id):r.official_name for r in off.itertuples()}
    # FTN join
    ftn=pd.read_csv(f'{NV}/ftn_charting_2026.csv',low_memory=False)
    ftn=ftn.rename(columns={'nflverse_game_id':'game_id','nflverse_play_id':'play_id'})
    for c in ['is_play_action','is_contested_ball','is_catchable_ball','is_drop','is_screen_pass','is_motion']:
        ftn[c]=ftn[c].astype(str).str.upper().eq('TRUE')
    p=pbp.merge(ftn[['game_id','play_id','is_play_action','is_contested_ball','is_catchable_ball','is_drop','is_screen_pass','is_motion','n_blitzers','n_defense_box']],on=['game_id','play_id'],how='left')
    p=p[p.play_type.isin(['pass','run'])]
    rz=p.yardline_100<=20; g10=p.yardline_100<=10
    # team-level per game
    neutral=(p.wp.between(.2,.8))&(p.qtr<=3)&(p.down.isin([1,2]))
    tg={}
    for (gid,tm),d in p.groupby(['game_id','posteam']):
        n=d[neutral.loc[d.index]]
        secs=d.sort_values('play_id').game_seconds_remaining.diff().abs()
        tg[(gid,tm)]=dict(team_plays=len(d),team_pass_att=int((d.play_type=='pass').sum()),
          neutral_pass_rate=(n.play_type=='pass').mean() if len(n)>=10 else None,
          pass_oe=d.pass_oe.mean(), team_epa_play=d.epa.mean(),
          sec_per_play=secs[secs<60].mean(), play_action_rate=d[d.play_type=='pass'].is_play_action.mean(),
          team_air_yards=d.air_yards.sum())
    # player-level per game
    pg={}
    def add(key,**kw):
        e=pg.setdefault(key,{}); 
        for k,v in kw.items(): e[k]=e.get(k,0)+v
    pas=p[p.play_type=='pass']
    for r in pas[pas.receiver_player_id.notna()].itertuples():
        add((r.game_id,r.receiver_player_id),targets=1,air_yards=r.air_yards if r.air_yards==r.air_yards else 0,
            rz_targets=int(r.yardline_100<=20),ez_targets=int((r.air_yards or 0)>=r.yardline_100),
            rec_epa=r.epa if r.epa==r.epa else 0,contested_tgts=int(r.is_contested_ball is True),
            catchable_tgts=int(r.is_catchable_ball is True),drops=int(r.is_drop is True),deep_tgts=int((r.air_yards or 0)>=20))
    ru=p[(p.play_type=='run')&p.rusher_player_id.notna()]
    for r in ru.itertuples():
        add((r.game_id,r.rusher_player_id),carries=1,rz_carries=int(r.yardline_100<=20),gl_carries=int(r.yardline_100<=5),rush_epa=r.epa if r.epa==r.epa else 0)
    for r in pas[pas.passer_player_id.notna()].itertuples():
        add((r.game_id,r.passer_player_id),dropbacks=1,pass_epa=r.epa if r.epa==r.epa else 0,cpoe_sum=r.cpoe if r.cpoe==r.cpoe else 0,cpoe_n=int(r.cpoe==r.cpoe),
            blitzed=int((r.n_blitzers or 0)>0) if r.n_blitzers==r.n_blitzers else 0, pa_db=int(r.is_play_action is True))
    pgn={}
    for (gid,pid),e in pg.items():
        nm=idname.get(pid); 
        if nm: pgn[(gid,norm(nm))]=e
    sn=pd.read_csv(f'{NV}/snap_counts_2026.csv'); snap={(r.game_id,norm(r.player),r.team):r.offense_pct for r in sn.itertuples()}
    # prior-weeks positional points allowed (FD pts by opp defense, by position)
    df=pd.DataFrame(rows)
    allowed=df[df.pos.isin(['QB','RB','WR','TE'])].groupby(['week','opp','pos']).fd_pts.sum().reset_index()
    def pos_allowed(week,opp,pos):
        a=allowed[(allowed.week<week)&(allowed.opp==opp)&(allowed.pos==pos)]
        return round(a.fd_pts.mean(),2) if len(a) else None
    # salary history
    sal={}
    for r in sorted(rows,key=lambda r:r['week']):
        if r.get('salary') and r.get('salary_type')=='classic': sal.setdefault((norm(r['player']),r['team']),[]).append((r['week'],r['salary']))
    # team totals for share calcs
    for r in rows:
        gid=r['game_id']; tm=r['team']; g=G.loc[gid] if gid in G.index else None
        if g is not None:
            home=g.home_team==tm; sp=g.spread_line  # + = home favored
            tot=g.total_line
            r['implied_total']=clean((tot/2+sp/2) if home else (tot/2-sp/2)) if tot==tot and sp==sp else None
            ml=g.home_moneyline if home else g.away_moneyline
            r['moneyline']=clean(ml)
            r['win_prob_ml']=clean((-ml/(-ml+100) if ml<0 else 100/(ml+100))) if ml==ml else None
            r['wind_mph']=clean(g.wind); r['surface']=g.surface if g.surface==g.surface else None
            r['referee']=ref_by_old.get(str(int(g.old_game_id))) if g.old_game_id==g.old_game_id else None
            if r['referee'] is None and g.referee==g.referee: r['referee']=g.referee
            r['coach']=(g.home_coach if home else g.away_coach)
            r['stadium']=g.stadium
            hs=g.home_team; me=tm
            if me in STAD and hs in STAD and g.location!='Neutral':
                r['travel_mi']=0 if home else hav(STAD[me],STAD[hs]); r['tz_shift']=0 if home else STAD[hs][2]-STAD[me][2]
            else: r['travel_mi']=None; r['tz_shift']=None
            r['game_total_actual']=clean(g.total); r['team_score']=clean(g.home_score if home else g.away_score)
            r['opp_score']=clean(g.away_score if home else g.home_score)
        t=tg.get((gid,tm),{})
        for k in ['team_plays','team_pass_att','neutral_pass_rate','pass_oe','team_epa_play','sec_per_play','play_action_rate']: r[k]=clean(t.get(k))
        e=pgn.get((gid,norm(r['player'])),{})
        for k in ['targets','air_yards','rz_targets','ez_targets','deep_tgts','contested_tgts','catchable_tgts','drops','carries','rz_carries','gl_carries','dropbacks']:
            r[k]=clean(e.get(k)) if e else (0 if r['pos'] in ('RB','WR','TE') and k not in ('dropbacks',) and (gid,tm) in tg else None)
        r['epa_total']=clean(sum(e.get(k,0) for k in ['rec_epa','rush_epa','pass_epa'])) if e else None
        r['cpoe']=clean(e['cpoe_sum']/e['cpoe_n']) if e.get('cpoe_n') else None
        r['blitz_rate_faced']=clean(e['blitzed']/e['dropbacks']) if e.get('dropbacks') else None
        r['target_share']=clean(e.get('targets',0)/t['team_pass_att']) if t.get('team_pass_att') and r['pos'] in ('RB','WR','TE') else None
        r['air_yards_share']=clean(e.get('air_yards',0)/t['team_air_yards']) if t.get('team_air_yards') and r['pos'] in ('RB','WR','TE') else None
        r['wopr']=clean(1.5*r['target_share']+0.7*r['air_yards_share']) if r['target_share'] is not None and r['air_yards_share'] is not None else None
        r['adot']=clean(e['air_yards']/e['targets']) if e.get('targets') else None
        r['rz_touches']=(r.get('rz_targets') or 0)+(r.get('rz_carries') or 0) if e else None
        r['snap_pct']=clean(snap.get((gid,norm(r['player']),tm)))
        r['opp_pos_pts_allowed']=pos_allowed(r['week'],r['opp'],r['pos']) if r['pos'] in ('QB','RB','WR','TE') else None
        h=sal.get((norm(r['player']),tm),[]); prev=[s for w,s in h if w<r['week']]
        r['salary_chg']=clean(r['salary']-prev[-1]) if r.get('salary') and prev and r.get('salary_type')=='classic' else None
        r['pts_per_1k']=clean(r['fd_pts']/(r['salary']/1000)) if r.get('salary') and r.get('fd_pts') is not None else None
        r['boom']=(r['pts_per_1k']>=3) if r['pts_per_1k'] is not None else None
        r['bust']=(r['pts_per_1k']<1.5) if r['pts_per_1k'] is not None else None
    # stack correlations: QB pts vs teammates' pts per team-game
    df=pd.DataFrame(rows); st=[]
    for (gid,tm),d in df.groupby(['game_id','team']):
        q=d[d.pos=='QB'].sort_values('fd_pts',ascending=False)
        if not len(q): continue
        qp=q.iloc[0].fd_pts
        opp=df[(df.game_id==gid)&(df.team!=tm)]
        for pos in ['WR','TE','RB']:
            top=d[d.pos==pos].sort_values('targets' if pos!='RB' else 'carries',ascending=False,na_position='last')
            if len(top): st.append(dict(game_id=gid,team=tm,pair='QB-'+pos+'1',qb=qp,mate=top.iloc[0].fd_pts))
        ow=opp[opp.pos=='WR'].sort_values('targets',ascending=False,na_position='last')
        if len(ow): st.append(dict(game_id=gid,team=tm,pair='QB-OppWR1',qb=qp,mate=ow.iloc[0].fd_pts))
        dst=opp[opp.pos=='DST']
        if len(dst): st.append(dict(game_id=gid,team=tm,pair='QB-OppDST',qb=qp,mate=dst.iloc[0].fd_pts))
    S=pd.DataFrame(st); stacks=[]
    from scipy import stats
    for pr,d in S.groupby('pair'):
        d=d.dropna()
        if len(d)>4:
            r_,pv=stats.pearsonr(d.qb,d.mate); stacks.append(dict(pair=pr,n=len(d),r=round(r_,3),p=round(pv,4)))
    D['rows']=[{k:clean(v) for k,v in r.items()} for r in rows]
    json.dump(D,open(f'{ROOT}/players.json','w'),separators=(',',':'))
    json.dump(dict(stacks=stacks,pairs=S.round(2).to_dict('records')),open(f'{ROOT}/stacks.json','w'),separators=(',',':'))
    tj=[dict(game_id=g,team=t_,**{k:clean(v) for k,v in v_.items()}) for (g,t_),v_ in tg.items()]
    json.dump(tj,open(f'{ROOT}/teams.json','w'),separators=(',',':'))
    print('rows',len(rows),'stacks',stacks)
if __name__=='__main__': main()
