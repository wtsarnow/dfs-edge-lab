#!/usr/bin/env python3
"""optimize.py - Current-week FanDuel Classic lineups + bot ablation -> lineups.json, bot_ablation.csv
Inputs (all saved bot outputs in /workspace; missing inputs are skipped and reported):
  board      (fanduel-salaries)    : w8-mocks/board_135562.csv
  projections(fanduel-projections) : fd-proj/classic-2026-10-25-135562.csv  (median/ceiling/floor/play_prob)
  injuries   (fanduel-injury-report): w8-main/injuries.md (OUT list, Q likelihood, HIGH beneficiary bumps)
  odds       (fanduel-odds)        : w8-main/odds.md (implied team totals)
  game script(fanduel-game-script) : w8-main/game_script.csv (p_shootout)
  offense    (fanduel-offense-overall): w8-main/offense.md (team EPA/play median)
  ownership  (fanduel-ownership)   : w8-main/ownership.md (MODEL own bands, top 30)
  simulator  (fanduel-simulator)   : sim_w8main/table.md (sim medians, top 30)
Edge Lab model (documented, deterministic):
  pts = proj_median (or, without projections, salary/1000 x historical position pts-per-$1k from players.json)
  sim: pts = 0.5*pts + 0.5*sim_median where available
  odds: pts *= (implied/slate_mean_implied)^0.5   offense: pts *= 1 + 0.5*team_EPA_median
  injury: OUT -> removed; Q -> pts *= likelihood; +bumps for HIGH beneficiaries
  play_prob from projections applied too. Cash objective = floor-weighted; GPP = ceiling*(1+p_shootout) - own penalty.
Usage: python3 tools/optimize.py [--slate 135562]
"""
import re, json, os, csv, itertools
import pandas as pd, pulp
W='/workspace'; ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP=60000; SLOTS={'QB':1,'RB':2,'WR':3,'TE':1,'D':1}
def rd(p): return open(f'{W}/{p}').read() if os.path.exists(f'{W}/{p}') else None
def nm(s): return re.sub(r'[^a-z]','',re.sub(r'\b(jr|sr|ii|iii|iv)\b','',s.lower()))
def load():
    b=pd.read_csv(f'{W}/w8-mocks/board_135562.csv'); b['k']=b.name.map(nm)
    b=b[~b.injury_tag.isin(['O','IR'])].copy()
    I={}
    f=pd.read_csv(f'{W}/fd-proj/classic-2026-10-25-135562.csv'); f['k']=f.player.map(nm)
    I['projections']=f.set_index(['k','team'])
    t=rd('w8-main/injuries.md'); inj={'out':set(),'q':{},'bump':{}}
    if t:
        for line in t.splitlines():
            c=[x.strip() for x in line.split('|')]
            if len(c)>7 and c[3] in('QB','RB','WR','TE'):
                k=nm(c[1])
                if 'OUT' in c[4]: inj['out'].add(k)
                m=re.match(r'~?(\d+)%',c[6]); 
                if m and 'OUT' not in c[4]: inj['q'][k]=int(m.group(1))/100
        for m in re.finditer(r"([A-Z][A-Za-z.'\- ]+?) \+(\d\.\d)(?: FD)?[^;()]*?\(HIGH",t): inj['bump'][nm(m.group(1).split(':')[-1].strip())]=float(m.group(2))
        for m in re.finditer(r'Others OUT: (.*)',t):
            for n in re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+) [A-Z]{2,3} RB',m.group(1)): inj['out'].add(nm(n))
        I['injury']=inj
    t=rd('w8-main/odds.md')
    if t:
        imp={}
        for m in re.finditer(r'\| ([A-Z]{2,3}) ([\d.]+) / ([A-Z]{2,3}) ([\d.]+) \|',t): imp[m.group(1)]=float(m.group(2)); imp[m.group(3)]=float(m.group(4))
        I['odds']=imp
    if os.path.exists(f'{W}/w8-main/game_script.csv'):
        g=pd.read_csv(f'{W}/w8-main/game_script.csv'); gs={}
        for r in g.itertuples():
            a,h=r.game.split('@'); gs[a]=gs[h]=r.p_shootout
        I['game-script']=gs
    t=rd('w8-main/offense.md')
    if t: I['offense-overall']={m.group(1):float(m.group(2)) for m in re.finditer(r'^\| ([A-Z]{2,3}) \| [A-Z]{2,3} \| ([+-][\d.]+) \[',t,re.M)}
    t=rd('w8-main/ownership.md')
    if t:
        o={}
        for m in re.finditer(r'^\| \d+ \| ([^|]+?)(?: \(Q\))? \| ([A-Z]{2,3}) \|.*?\| (\d+)–(\d+)% MODEL',t,re.M): o[(nm(m.group(1)),m.group(2))]=(int(m.group(3))+int(m.group(4)))/2
        I['ownership']=o
    t=rd('sim_w8main/table.md')
    if t: I['simulator']={(nm(m.group(1).replace(' (Q)','')),m.group(2)):float(m.group(3)) for m in re.finditer(r'^\| \d+ \| ([^|]+?) \| ([A-Z]{2,3}) \| \w+ \| \$[\d,]+ \| ([\d.]+) \|',t,re.M)}
    return b,I
def hist_rate():
    r=pd.DataFrame(json.load(open(f'{ROOT}/players.json'))['rows']); r=r[r.pts_per_1k.notna()&(r.salary_type=='classic')]
    m=r.groupby('pos').pts_per_1k.mean().to_dict(); m['D']=m.get('DST',m.get('D',1.0)); return m
def score(b,I,use):
    d=b.copy(); P=I['projections']; HR=hist_rate()
    def g(r,c): 
        try: return float(P.loc[(r.k,r.team)][c])
        except Exception: return None
    if 'projections' in use:
        d['med']=[g(r,'median') for r in d.itertuples()]; d['ceil']=[g(r,'ceiling') for r in d.itertuples()]; d['flo']=[g(r,'floor') for r in d.itertuples()]
        pp=[g(r,'play_prob') for r in d.itertuples()]; d['med']=d.med*[x if x is not None else 1 for x in pp]
        d=d[d.med.notna()].copy()
    else:
        d['med']=d.salary/1000*d.position.map(HR).fillna(1.5); d['ceil']=d.med*1.6; d['flo']=d.med*0.6
    if 'simulator' in use and 'simulator' in I:
        s=[I['simulator'].get((r.k,r.team)) for r in d.itertuples()]; d['med']=[0.5*m+0.5*x if x else m for m,x in zip(d.med,s)]
    if 'odds' in use and 'odds' in I:
        mu=sum(I['odds'].values())/len(I['odds']); f=d.team.map(lambda t:(I['odds'].get(t,mu)/mu)**0.5)
        for c in ['med','ceil','flo']: d[c]=d[c]*f
    if 'offense-overall' in use and 'offense-overall' in I:
        f=d.apply(lambda r:1+0.5*I['offense-overall'].get(r.team,0) if r.position!='D' else 1,axis=1)
        for c in ['med','ceil','flo']: d[c]=d[c]*f
    if 'injury' in use and 'injury' in I:
        J=I['injury']; d=d[~d.k.isin(J['out'])].copy()
        q=d.k.map(lambda k:J['q'].get(k,1.0)); bump=d.k.map(lambda k:J['bump'].get(k,0.0))
        for c in ['med','ceil','flo']: d[c]=d[c]*q+bump
    sh=d.team.map(lambda t:I['game-script'].get(t,0)) if 'game-script' in use and 'game-script' in I else 0
    own=[I['ownership'].get((r.k,r.team),None) for r in d.itertuples()] if 'ownership' in use and 'ownership' in I else [None]*len(d)
    d['own']=own; d['gpp']=d.ceil*(1+sh*0.5)-0.15*pd.Series([o or 0 for o in own],index=d.index)
    d['cash']=0.6*d.med+0.4*d.flo
    return d.reset_index(drop=True)
def solve(d,obj,n=1,stack=False,mindiff=3):
    out=[]; prev=[]
    for _ in range(n):
        m=pulp.LpProblem('l',pulp.LpMaximize); x=[pulp.LpVariable(f'x{i}',cat='Binary') for i in range(len(d))]
        m+=pulp.lpSum(x[i]*d[obj][i] for i in range(len(d)))
        m+=pulp.lpSum(x[i]*d.salary[i] for i in range(len(d)))<=CAP; m+=pulp.lpSum(x)==9
        for p,c in SLOTS.items():
            idx=[i for i in range(len(d)) if d.position[i]==p]
            m+=pulp.lpSum(x[i] for i in idx)>=c
            if p in('QB','D'): m+=pulp.lpSum(x[i] for i in idx)==1
        m+=pulp.lpSum(x[i] for i in range(len(d)) if d.position[i] in('RB','WR','TE'))==7
        for p,c in [('RB',3),('WR',4),('TE',2)]: m+=pulp.lpSum(x[i] for i in range(len(d)) if d.position[i]==p)<=c
        for t in d.team.unique(): m+=pulp.lpSum(x[i] for i in range(len(d)) if d.team[i]==t)<=4
        for L in prev: m+=pulp.lpSum(x[i] for i in L)<=9-mindiff
        if stack:  # QB + 2 same-team pass catchers + 1 opponent bring-back
            opp={}; 
            for gm in d.game.unique() if 'game' in d else []: pass
            for i in range(len(d)):
                if d.position[i]=='QB':
                    mates=[j for j in range(len(d)) if d.team[j]==d.team[i] and d.position[j] in('WR','TE')]
                    bb=[j for j in range(len(d)) if d.team[j]==d.opp[i] and d.position[j] in('WR','TE','RB')]
                    m+=pulp.lpSum(x[j] for j in mates)>=2*x[i]; m+=pulp.lpSum(x[j] for j in bb)>=x[i]
        m.solve(pulp.PULP_CBC_CMD(msg=0))
        if pulp.LpStatus[m.status]!='Optimal': break
        L=[i for i in range(len(d)) if x[i].value()>0.5]; prev.append(L); out.append(L)
    return out
def fmt(d,L,label,obj):
    order={'QB':0,'RB':1,'WR':2,'TE':3,'D':5}; ps=sorted(L,key=lambda i:order[d.position[i]])
    pl=[dict(name=d.name[i],pos=d.position[i],team=d.team[i],opp=d.opp[i],salary=int(d.salary[i]),proj=round(d.med[i],2),ceil=round(d.ceil[i],2),floor=round(d.flo[i],2),own=(None if d.own[i] is None or d.own[i]!=d.own[i] else d.own[i]),inj=d.injury_tag[i] if isinstance(d.injury_tag[i],str) else None) for i in ps]
    return dict(label=label,objective=obj,players=pl,salary=sum(p['salary'] for p in pl),proj=round(sum(p['proj'] for p in pl),2),ceil=round(sum(p['ceil'] for p in pl),2),floor=round(sum(p['floor'] for p in pl),2))
def opp_map(b):
    t=rd('w8-main/game_script.csv'); o={}
    for r in pd.read_csv(f'{W}/w8-main/game_script.csv').itertuples():
        a,h=r.game.split('@'); o[a]=h; o[h]=a
    return o
def main():
    b,I=load(); om=opp_map(b); b['opp']=b.team.map(om)
    ALL=['projections','simulator','odds','offense-overall','injury','game-script','ownership']
    d=score(b,I,set(ALL))
    out=dict(slate=135562,label='FanDuel Week 8 Sunday Main (nflverse Week 7), lock Sun 10/25 1:00 PM ET',
      projection_source='fanduel-projections fd-proj/classic-2026-10-25-135562.csv, adjusted by the Edge Lab model (see tools/optimize.py header)',
      inputs_loaded={k:(len(v) if hasattr(v,'__len__') else 1) for k,v in I.items()},
      top=[fmt(d,L,f'Top #{n+1}','median') for n,L in enumerate(solve(d,'med',10,mindiff=2))],
      cash=fmt(d,solve(d,'cash')[0],'Cash-safe','0.6*median+0.4*floor'),
      gpp=fmt(d,solve(d,'gpp')[0],'GPP leverage','ceiling*(1+0.5*p_shootout) - 0.15*own%'),
      stack=fmt(d,solve(d,'med',stack=True)[0],'Stacked (QB+2 + bring-back)','median, stack constraint'),
      official=None)
    abl=[]
    for obj,base in [('med',out['top'][0]),('gpp',out['gpp'])]:
        bnames={p['name'] for p in base['players']}; full=d.set_index('name')[obj]; bscore=round(sum(full.get(n,0) for n in bnames),2)
        for bot in ALL:
            dd=score(b,I,set(ALL)-{bot}); L=solve(dd,obj)[0]; lu=fmt(dd,L,'w/o '+bot,obj)
            names={p['name'] for p in lu['players']}
            rescored=round(sum(full.get(n,0) for n in names),2)
            ch=len(bnames-names)
            abl.append(dict(build='Top #1 (median)' if obj=='med' else 'GPP leverage',bot='fanduel-'+bot if bot!='injury' else 'fanduel-injury-report',removed=bot,
               lineup_proj_own_model=lu['proj'],delta_vs_full=round(rescored-bscore,2) if ch else 0.0,
               players_out=sorted(bnames-names),players_in=sorted(names-bnames),changed=ch,lineup=[p['name'] for p in lu['players']]))
    out['ablation']=abl
    json.dump(out,open(f'{ROOT}/lineups.json','w'),indent=1)
    with open(f'{ROOT}/bot_ablation.csv','w',newline='') as f:
        w=csv.writer(f); w.writerow(['build','bot','removed_input','players_changed','delta_proj_full_model','players_out','players_in'])
        for a in abl: w.writerow([a['build'],a['bot'],a['removed'],a['changed'],a['delta_vs_full'],'; '.join(a['players_out']),'; '.join(a['players_in'])])
    for k in ['cash','gpp','stack']: print(k,out[k]['proj'],[p['name'] for p in out[k]['players']])
    print('top1',out['top'][0]['proj'],[p['name'] for p in out['top'][0]['players']])
    for a in abl: print(a['build'],a['bot'],a['changed'],a['delta_vs_full'])
    print(out['inputs_loaded'])
if __name__=='__main__': main()
