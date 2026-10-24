#!/usr/bin/env python3
"""context.py - pre-game context signals added to players.json (idempotent; run after enrich.py, before analyze.py).
Sources (real data only):
  nflverse games.csv (github.com/nflverse/nfldata): roof, rest days, spread/total, div, surface, kickoff, head-to-head history
  nflverse stats_player_week_<season>.csv: prior-season vs-opponent FD points, season-to-date averages, form, teammates
  nflverse snap_counts_2026.csv: snap share trend
  Open-Meteo archive / historical-forecast API: temp, precip, wind at kickoff hour by stadium lat/lon
Leakage rules: vs-opponent uses seasons < game season; season/to-date/form/DvP use weeks < game week."""
import json, os, re, sys, subprocess, urllib.request, math
import pandas as pd, numpy as np
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); NV=f'{ROOT}/tools/cache/nflverse'; WC=f'{ROOT}/tools/cache/weather'; os.makedirs(WC,exist_ok=True)
if '--download' in sys.argv:
    subprocess.run(['curl','-sL','-o',f'{NV}/games.csv','https://github.com/nflverse/nfldata/raw/master/data/games.csv'])
    for y in range(2021,2027):
        if y==2026 or not os.path.exists(f'{NV}/stats_player_week_{y}.csv'):
            subprocess.run(['curl','-sL','-o',f'{NV}/stats_player_week_{y}.csv',f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{y}.csv'])
# stadium lat, lon, elevation ft (public stadium coordinates)
STAD={"Levi's Stadium":(37.4033,-121.9694,30),'Lambeau Field':(44.5013,-88.0622,640),'Maracana Stadium':(-22.9122,-43.2302,30),'Huntington Bank Field':(41.5061,-81.6995,580),
'Acrisure Stadium':(40.4468,-80.0158,730),'Lucas Oil Stadium':(39.7601,-86.1639,715),'Hard Rock Stadium':(25.958,-80.2389,7),'Highmark Stadium':(42.7738,-78.787,640),
'Empower Field at Mile High':(39.7439,-105.0201,5280),'Caesars Superdome':(29.9511,-90.0812,3),'Raymond James Stadium':(27.9759,-82.5033,26),'EverBank Stadium':(30.3239,-81.6373,16),
'Ford Field':(42.34,-83.0456,600),'Soldier Field':(41.8623,-87.6167,595),'Northwest Stadium':(38.9076,-76.8645,200),'MetLife Stadium':(40.8135,-74.0745,7),
'Reliant Stadium':(29.6847,-95.4107,50),'NRG Stadium':(29.6847,-95.4107,50),'Bank of America Stadium':(35.2258,-80.8528,750),'Tottenham Hotspur Stadium':(51.6043,-0.0664,100),
'Paycor Stadium':(39.0955,-84.516,490),'Allegiant Stadium':(36.0909,-115.1833,2030),'Lumen Field':(47.5952,-122.3316,20),'Lincoln Financial Field':(39.9008,-75.1675,30),
'U.S. Bank Stadium':(44.9737,-93.2581,830),'M&T Bank Stadium':(39.278,-76.6227,30),'Mercedes-Benz Stadium':(33.7554,-84.4008,1000),'SoFi Stadium':(33.9535,-118.3392,100),
'State Farm Stadium':(33.5276,-112.2626,1070),'Nissan Stadium':(36.1665,-86.7713,420),'Gillette Stadium':(42.0909,-71.2643,290),'AT&T Stadium':(32.7473,-97.0945,600),
'Wembley Stadium':(51.556,-0.2796,100),'GEHA Field at Arrowhead Stadium':(39.0489,-94.4839,880)}
OLD={'OAK':'LV','SD':'LAC','STL':'LA','LAR':'LA','JAC':'JAX','WSH':'WAS'}
norm=lambda t: OLD.get(t,t)
nm=lambda s: re.sub(r'[^a-z]','',re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',str(s).lower()))
FD=lambda d:(d.passing_yards.fillna(0)*.04+d.passing_tds.fillna(0)*4-d.passing_interceptions.fillna(0)+d.rushing_yards.fillna(0)*.1+d.rushing_tds.fillna(0)*6
  +d.receptions.fillna(0)*.5+d.receiving_yards.fillna(0)*.1+d.receiving_tds.fillna(0)*6-d.fumbles_lost_total.fillna(0)*2
  +(d.passing_2pt_conversions.fillna(0)+d.rushing_2pt_conversions.fillna(0)+d.receiving_2pt_conversions.fillna(0))*2+d.special_teams_tds.fillna(0)*6)
G=pd.read_csv(f'{NV}/games.csv',low_memory=False); G['home_team']=G.home_team.map(norm); G['away_team']=G.away_team.map(norm)
S=pd.concat([pd.read_csv(f'{NV}/stats_player_week_{y}.csv',low_memory=False) for y in range(2021,2027) if os.path.exists(f'{NV}/stats_player_week_{y}.csv')])
S=S[S.season_type=='REG'].copy(); S['fd']=FD(S); S['k']=S.player_display_name.map(nm); S['team']=S.team.map(norm); S['opponent_team']=S.opponent_team.map(norm)
SN=pd.read_csv(f'{NV}/snap_counts_2026.csv'); SN['k']=SN.player.map(nm)
D=json.load(open(f'{ROOT}/players.json')); rows=D['rows']
gi=G.set_index('game_id')
def wx(game_id):
    f=f'{WC}/{game_id}.json'
    if os.path.exists(f): return json.load(open(f))
    g=gi.loc[game_id]; st=STAD.get(g.stadium)
    if st is None: return None
    for host in ['archive-api','historical-forecast-api']:
        u=f'https://{host}.open-meteo.com/v1/{"archive" if host=="archive-api" else "forecast"}?latitude={st[0]}&longitude={st[1]}&start_date={g.gameday}&end_date={g.gameday}&hourly=temperature_2m,precipitation,wind_speed_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York'
        try: j=json.load(urllib.request.urlopen(u,timeout=30))
        except Exception: continue
        h=j.get('hourly',{}); hr=int(str(g.gametime).split(':')[0]); i=hr
        if h.get('temperature_2m') and h['temperature_2m'][i] is not None:
            o=dict(temp=h['temperature_2m'][i],precip=h['precipitation'][i],wind=h['wind_speed_10m'][i],src=host); json.dump(o,open(f,'w')); return o
    return None
def hav(a,b):
    if not a or not b: return None
    R=3958.8; p1,p2=math.radians(a[0]),math.radians(b[0]); dl=math.radians(b[1]-a[1]); dp=p2-p1
    return 2*R*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
WEST={'SF','SEA','LA','LAC','LV','ARI','DEN'}; EAST_TZ_STAD=None
# home stadium per team from 2026 schedule (most common)
home_st=G[(G.season>=2025)&(G.location=='Home')].groupby('home_team').stadium.agg(lambda s:s.mode()[0]).to_dict()
cur=S[S.season==2026]
# DvP: FD pts allowed by opponent to position, weeks < w (2026)
dvp=cur[cur.position.isin(['QB','RB','WR','TE'])].groupby(['opponent_team','position','week']).fd.sum().reset_index()
for r in rows:
    gid=r['game_id']
    if gid not in gi.index: continue
    g=gi.loc[gid]; season=int(g.season); wk=int(g.week); tm=norm(r['team']); op=norm(r['opp']); home=tm==g.home_team
    indoor=g.roof in ('dome','closed')
    w=wx(gid)
    if w:
        r['temp_f']=round(w['temp'],1); r['wind_mph']=0.0 if indoor else round(w['wind'],1)
        r['rain_mm']=0.0 if indoor else round(w['precip'] or 0,2); r['rain_flag']=0.0 if indoor else float((w['precip'] or 0)>=0.2)
        if indoor: r['temp_f']=72.0  # climate-controlled (standard indoor assumption)
        r['heat_flag']=float(r['temp_f']>=85); r['cold_flag']=float(r['temp_f']<=40)
    for k in ['rain_mm','rain_flag','heat_flag','cold_flag']: r.setdefault(k,None)
    dr=float(g.home_rest if home else g.away_rest); odr=float(g.away_rest if home else g.home_rest)
    r['days_rest']=dr; r['opp_days_rest']=odr; r['rest_diff']=dr-odr; r['short_week']=float(dr<=5); r['off_bye']=float(dr>=13)
    st=STAD.get(g.stadium); r['altitude_ft']=st[2] if st else None
    sf=g.surface if pd.notna(g.surface) and str(g.surface).strip() else r.get('surface'); r['turf_n']=None if not sf else float('grass' not in str(sf).lower())
    hh=int(str(g.gametime).split(':')[0]); r['kick_slot']='early' if hh<16 else ('late' if hh<19 else 'night')
    r['primetime_n']=float(hh>=19); r['div_game_n']=float(g.div_game==1); r['home_n']=float(home)
    r['spread_team']=float(-g.spread_line if home else g.spread_line) if pd.notna(g.spread_line) else None  # negative = favored
    r['total_vegas']=float(g.total_line) if pd.notna(g.total_line) else None
    r['implied_team']=round(r['total_vegas']/2-r['spread_team']/2,2) if r['total_vegas'] is not None and r['spread_team'] is not None else None
    hs=home_st.get(tm); r['travel_miles']=0.0 if home else (round(hav(STAD.get(hs),st),0) if hs in STAD and st else None)
    r['east_1pm_west_team']=float(tm in WEST and hh==13 and not home) if True else None
    # head-to-head team history (seasons < current, since 2002)
    h=G[(G.season<season)&(G.season>=2002)&(G.game_type=='REG')&(((G.home_team==tm)&(G.away_team==op))|((G.home_team==op)&(G.away_team==tm)))&G.result.notna()]
    if len(h):
        won=((h.home_team==tm)&(h.result>0))|((h.away_team==tm)&(h.result<0)); tie=h.result==0
        r['team_h2h_games']=float(len(h)); r['team_h2h_winpct']=round((won.sum()+.5*tie.sum())/len(h),3)
    else: r['team_h2h_games']=0.0; r['team_h2h_winpct']=None
    if r['pos'] in ('DST','K','D'):
        for k in ['vs_opp_games','vs_opp_avg_fd','vs_opp_diff','season_avg_td','last3_avg_fd','snap_trend3','tgt_share_trend3','teammate_out','revenge_game','opp_dvp']: r[k]=None
        continue
    k=nm(r['player']); ps=S[S.k==k]
    prior=ps[(ps.season<season)&(ps.opponent_team==op)]
    r['vs_opp_games']=float(len(prior)); r['vs_opp_avg_fd']=round(prior.fd.mean(),2) if len(prior) else None
    td=ps[(ps.season==season)&(ps.week<wk)]
    r['season_avg_td']=round(td.fd.mean(),2) if len(td) else None
    r['vs_opp_diff']=round(r['vs_opp_avg_fd']-r['season_avg_td'],2) if r['vs_opp_avg_fd'] is not None and r['season_avg_td'] is not None else None
    l3=td.sort_values('week').tail(3); r['last3_avg_fd']=round(l3.fd.mean(),2) if len(l3) else None
    r['tgt_share_trend3']=round(np.polyfit(l3.week,l3.target_share.fillna(0),1)[0],4) if len(l3)>=2 else None
    sn=SN[(SN.k==k)&(SN.season==season)&(SN.week<wk)].sort_values('week').tail(3)
    r['snap_trend3']=round(np.polyfit(sn.week,sn.offense_pct,1)[0],4) if len(sn)>=2 else None
    # revenge: played for this opponent in any earlier season/week
    r['revenge_game']=float(((ps.team==op)&((ps.season<season)|(ps.week<wk))).any()) if len(ps) else None
    # teammate_out: top-2 skill teammates by season-to-date FD total who have no stat row this game
    tmw=cur[(cur.team==tm)&(cur.week<wk)&(cur.position.isin(['RB','WR','TE']))&(cur.k!=k)]
    if len(tmw) and wk>1:
        top=tmw.groupby('k').fd.sum().nlargest(2).index
        played=set(cur[(cur.team==tm)&(cur.week==wk)].k)
        r['teammate_out']=float(any(t not in played for t in top)) if played else None
    else: r['teammate_out']=None
    pos=r['pos']; dv=dvp[(dvp.opponent_team==op)&(dvp.position==pos)&(dvp.week<wk)]
    r['opp_dvp']=round(dv.fd.mean(),2) if len(dv) else None
json.dump(D,open(f'{ROOT}/players.json','w'),separators=(',',':'))
NEW=['rain_mm','rain_flag','temp_f','heat_flag','cold_flag','wind_mph','days_rest','opp_days_rest','rest_diff','short_week','off_bye','vs_opp_games','vs_opp_avg_fd','vs_opp_diff',
 'team_h2h_games','team_h2h_winpct','spread_team','total_vegas','implied_team','opp_dvp','travel_miles','east_1pm_west_team','altitude_ft','turf_n','primetime_n','kick_slot',
 'last3_avg_fd','snap_trend3','tgt_share_trend3','teammate_out','revenge_game','div_game_n','home_n']
for c in NEW: print(c, sum(r.get(c) is not None and not (isinstance(r.get(c),float) and math.isnan(r.get(c))) for r in rows),'/',len(rows))
