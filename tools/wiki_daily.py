#!/usr/bin/env python3
"""wiki_daily.py - daily Wikipedia pageview series per player (Wikimedia REST), cached.
Adds wiki_d1 (views day before game) and wiki_z (z-score of day-before vs prior 28 days) to players.json,
and writes wiki_daily.json {title: {YYYYMMDD: views}}. Idempotent; re-fetches only titles without a cache file
newer than 12h (use --refresh to force)."""
import json, os, sys, time, urllib.request, urllib.parse, datetime as dt, statistics as st
from concurrent.futures import ThreadPoolExecutor
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); C=f'{ROOT}/tools/cache/wiki_daily'; os.makedirs(C,exist_ok=True)
UA={'User-Agent':'DFSEdgeLab/1.0 (wtsarnow.github.io; research)'}
D=json.load(open(f'{ROOT}/players.json')); rows=D['rows']
titles=sorted({r['wiki_title'] for r in rows if r.get('wiki_title')})
end=dt.date.today().strftime('%Y%m%d')
def get(t):
    f=f'{C}/'+urllib.parse.quote(t,safe='')+'.json'
    if os.path.exists(f) and time.time()-os.path.getmtime(f)<43200 and '--refresh' not in sys.argv: return t,json.load(open(f))
    u=('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/'
       +urllib.parse.quote(t.replace(' ','_'),safe='')+f'/daily/20260801/{end}')
    for i in range(3):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20))
            s={x['timestamp'][:8]:x['views'] for x in d['items']}; json.dump(s,open(f,'w')); return t,s
        except Exception as e: time.sleep(1+i)
    return t,None
with ThreadPoolExecutor(6) as ex: S=dict(ex.map(get,titles))
S={k:v for k,v in S.items() if v}
for r in rows:
    s=S.get(r.get('wiki_title')); r['wiki_d1']=None; r['wiki_z']=None
    if not s: continue
    g=dt.date.fromisoformat(r['gameday']); d1=(g-dt.timedelta(1)).strftime('%Y%m%d')
    base=[s.get((g-dt.timedelta(i)).strftime('%Y%m%d')) for i in range(2,30)]; base=[b for b in base if b is not None]
    if d1 in s:
        r['wiki_d1']=s[d1]
        if len(base)>=14 and st.pstdev(base)>0: r['wiki_z']=round((s[d1]-st.mean(base))/st.pstdev(base),3)
json.dump(D,open(f'{ROOT}/players.json','w'),separators=(',',':'))
json.dump(S,open(f'{ROOT}/wiki_daily.json','w'),separators=(',',':'))
print('titles',len(titles),'series',len(S),'rows wiki_z',sum(r['wiki_z'] is not None for r in rows))
