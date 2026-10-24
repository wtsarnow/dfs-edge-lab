#!/usr/bin/env python3
"""collect_signals.py - build/refresh the per-player, per-game FanDuel dataset.

Every NFL game (not only our lineups). Keyed by game_id (nflverse style, e.g. 2026_07_NE_CHI).
Idempotent: rows in players.json are upserted by key "<game_id>|<player>|<team>".

Usage:
  python3 tools/collect_signals.py --week 7                 # every final game in week 7
  python3 tools/collect_signals.py --week 7 --game 2026_07_NE_CHI
  python3 tools/collect_signals.py --week 8 --slate sun     # tnf|sun|snf|mnf|all
  add --trends to also pull Google Trends (pytrends; slow, rate-limited -> null on failure)
  add --no-wiki to skip Wikipedia pageviews
  python3 tools/collect_signals.py --analyze-only           # just recompute signals.json

Sources (all real, nothing invented; missing => null):
  schedule/lines/rest/roof : /workspace/pbp/games.csv (nflverse)
  FD points                : ESPN game summary JSON -> /workspace/fdscore.py (shared scorer)
  position                 : /workspace/rosters2026.csv
  FD salary/projection/inj : board files listed in BOARDS below (per slate)
  opp defensive rank       : nflverse pbp EPA/play allowed, weeks before the game (1 = toughest)
  wiki_views_7d            : Wikimedia REST pageviews, 7 days ending the day before kickoff
  trends_rel               : Google Trends (US, 7 days before) player mean / anchor 'NFL' mean
  x_mentions               : null (X counts API only covers the last 7 days; not backfillable)
"""
import argparse, csv, gzip, json, os, re, sys, time, datetime as dt, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
W = '/workspace'; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W); import fdscore
CACHE = os.path.join(ROOT, 'tools', 'cache'); os.makedirs(CACHE + '/espn', exist_ok=True)
UA = {'User-Agent': 'FanDuelWeekly/1.0 (wtsarnow.github.io; research)'}
TM = {'WSH': 'WAS', 'LAR': 'LA', 'JAC': 'JAX'}
t = lambda x: TM.get((x or '').upper(), (x or '').upper())
norm = fdscore.norm

# board files: (week, glob-ish path, kind, salary_type). kind tells the parser.
BOARDS = [
 (3, 'fd-showdown-phi-chi-2026-09-28.csv', 'sd', 'showdown_flex'),
 (4, 'fd-showdown-pit-cle-2026-10-01.csv', 'sd', 'showdown_flex'),
 (4, 'fd-showdown-ATL-NO-2026-10-05.csv', 'sd', 'showdown_flex'),
 (5, 'fd-showdown-TB-DAL-2026-10-08.csv', 'sd', 'showdown_flex'),
 (5, 'fd-showdown-BUF-LAR-2026-10-12.csv', 'sd', 'showdown_flex'),
 (6, 'sm6/fd_board_verified.csv', 'fdlist', 'classic'),
 (6, 'sm6/projections_sm6.csv', 'sm6proj', 'classic'),
 (6, 'w6-snf-dal-gb-salaries.csv', 'sd', 'showdown_flex'),
 (6, 'mnf-w7/fanduel-nfl-2026-10-19-WAS-SF-showdown-135541-players.csv', 'fdlist', 'showdown_flex'),
 (6, 'mnf-w7/projections.csv', 'proj', None),
 (7, 'tnf-w7/board-135561.csv', 'fdlist', 'showdown_flex'),
 (7, 'tnf-w7/projections.csv', 'proj', None),
 (8, 'w8-mocks/board_135562.csv', 'w8', 'classic'),
]
# our lineup appearances (known lineup files only)
def lineup_counts():
    c = {}
    p = f'{W}/sm6/lineups20.csv'
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            for col in ['QB','RB1','RB2','WR3','WR4','WR5','TE','FLEX','DEF']:
                m = re.match(r'(.+?) \((\w+) ', r[col] or '')
                if m: k = (6, norm(m.group(1))); c[k] = c.get(k, 0) + 1
    for w, n in [(7, "D'Andre Swift"), (7, 'A.J. Brown')]:   # TNF W7 MVPs (from graded entries)
        c[(w, norm(n))] = c.get((w, norm(n)), 0) + 1
    return c
MVPS = {(7, norm("D'Andre Swift")), (7, norm('A.J. Brown'))}

def fnum(x):
    try: return float(x) if x not in (None, '') else None
    except: return None

def load_boards(week):
    out = {}   # (norm name, team) -> dict
    def put(name, team, **kw):
        k = (norm(name), t(team)); d = out.setdefault(k, {'display': name})
        for a, b in kw.items():
            if b is not None and d.get(a) is None: d[a] = b
    for w, path, kind, st in BOARDS:
        if w != week or not os.path.exists(f'{W}/{path}'): continue
        for r in csv.DictReader(open(f'{W}/{path}')):
            if kind == 'sd':
                put(r['player'], r['team'], salary=fnum(r['flex']), salary_type=st, injury=r.get('injury') or None, proj=fnum(r.get('dff_proj') or r.get('proj')), pos_fd=r['pos'])
            elif kind == 'fdlist':
                nm = r['Nickname']; pos = r['Position']
                if pos == 'D': nm = r['Team']
                put(nm, r['Team'], salary=fnum(r['Salary']), salary_type=st, injury=r.get('Injury Indicator') or None, pos_fd=pos, fppg=fnum(r['FPPG']))
            elif kind == 'sm6proj':
                nm = r['team'] if r['pos'] == 'DST' else r['name']
                put(nm, r['team'], proj=fnum(r['proj']), own=fnum(r['own_proxy']), own_src='model estimate', team_implied=fnum(r['team_implied']))
            elif kind == 'proj':
                put(r['player'], r['team'], proj=fnum(r.get('median')))
            elif kind == 'w8':
                put(r['name'], r['team'], salary=fnum(r['salary']), salary_type=st, injury=r.get('injury_tag') or None, pos_fd=r['position'])
    return out

def games(week, game=None, slate='all'):
    G = [r for r in csv.DictReader(open(f'{W}/pbp/games.csv')) if r['season'] == '2026' and int(r['week']) == week]
    if game: G = [g for g in G if g['game_id'] == game]
    def sl(g):
        if g['weekday'] == 'Thursday': return 'tnf'
        if g['weekday'] == 'Monday': return 'mnf'
        if g['weekday'] == 'Sunday' and g['gametime'] >= '19:00': return 'snf'
        return 'sun'
    for g in G: g['slate'] = sl(g)
    if slate != 'all': G = [g for g in G if g['slate'] == slate]
    return G

def espn(eid):
    p = f'{CACHE}/espn/{eid}.json'
    if not os.path.exists(p):
        u = f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}'
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
        json.dump(d, open(p, 'w'))
    return p

_ros = None
def roster_pos(name, team):
    global _ros
    if _ros is None:
        _ros = {}
        for r in csv.DictReader(open(f'{W}/rosters2026.csv')):
            _ros[(norm(r['full_name']), t(r['team']))] = r['position']; _ros.setdefault((norm(r['full_name']), None), r['position'])
    return _ros.get((norm(name), team)) or _ros.get((norm(name), None))

_def = {}
def def_rank(week):
    if week in _def: return _def[week]
    import pandas as pd
    p = pd.read_csv(f'{W}/pbp/pbp26.csv.gz', usecols=['week', 'defteam', 'epa', 'play_type'], low_memory=False)
    p = p[(p.week < week) & p.play_type.isin(['pass', 'run']) & p.epa.notna()]
    s = p.groupby('defteam').epa.mean().rank(method='min')   # 1 = lowest EPA allowed = toughest
    _def[week] = {t(k): int(v) for k, v in s.items()}; return _def[week]

def http_json(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(1 + i)
        except Exception: time.sleep(1 + i)
    return None

TITLES = os.path.join(CACHE, 'wiki_titles.json')
def wiki_title(name, cache):
    if name in cache: return cache[name]
    q = urllib.parse.quote(f'{name} American football')
    d = http_json(f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&srlimit=3&format=json')
    title = None
    for h in (d or {}).get('query', {}).get('search', []):
        if norm(h['title'].split(' (')[0]) == norm(name): title = h['title']; break
    cache[name] = title; return title

def wiki_views(title, gameday):
    end = dt.date.fromisoformat(gameday) - dt.timedelta(days=1); st = end - dt.timedelta(days=6)
    u = ('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/'
         f'{urllib.parse.quote(title.replace(" ", "_"), safe="")}/daily/{st:%Y%m%d}00/{end:%Y%m%d}00')
    d = http_json(u)
    if not d or 'items' not in d: return None, None
    v = [i['views'] for i in d['items']]
    if not v: return None, None
    base = sum(v[:-1]) / max(1, len(v) - 1)
    return sum(v), (round(v[-1] / base, 3) if base else None)

def trends(rows):
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print('pytrends missing; trends stay null'); return
    tr = TrendReq(hl='en-US', tz=240); fails = 0
    by = {}
    for r in rows:
        if r.get('salary') and r['pos'] != 'DST' and r.get('trends_rel') is None: by.setdefault(r['gameday'], []).append(r)
    for day, rs in by.items():
        end = dt.date.fromisoformat(day) - dt.timedelta(days=1); st = end - dt.timedelta(days=6)
        for i in range(0, len(rs), 4):
            chunk = rs[i:i + 4]; kw = ['NFL'] + [r['player'] for r in chunk]
            try:
                tr.build_payload(kw, timeframe=f'{st} {end}', geo='US'); df = tr.interest_over_time(); fails = 0
                a = df['NFL'].mean()
                for r in chunk:
                    r['trends_rel'] = round(float(df[r['player']].mean() / a), 4) if a and r['player'] in df else None
            except Exception as e:
                fails += 1; print('trends fail', type(e).__name__, fails)
                if fails >= 4: print('Google Trends blocked; leaving rest null'); return
                time.sleep(20)
            time.sleep(2)

SKILL = {'QB', 'RB', 'WR', 'TE', 'K', 'FB'}
def build_game(g, boards, lc, dr):
    eid = g['espn']; final = g['home_score'] != ''
    rows = []
    if not eid: return rows
    P, T, _ = fdscore.load(espn(eid)) if final else ({}, {}, {})
    home, away = t(g['home_team']), t(g['away_team'])
    dome = g['roof'] in ('dome', 'closed')
    temp = fnum(g['temp'])
    try:
        wx = json.load(open(f'{CACHE}/espn/{eid}.json')).get('gameInfo', {}).get('weather') or {}
        if temp is None and wx.get('temperature') is not None: temp = float(wx['temperature'])
    except Exception: pass
    spread_home = fnum(g['spread_line'])    # nflverse: + = home favored by that many
    week = int(g['week']); wd = g['weekday']
    prime = g['slate'] in ('tnf', 'snf', 'mnf')
    base = dict(week=week, game_id=g['game_id'], slate=g['slate'], gameday=g['gameday'], weekday=wd, kickoff_et=g['gametime'],
                primetime=prime, dome=dome, roof=g['roof'] or None, temp_f=None if dome else temp, total_line=fnum(g['total_line']), div_game=g['div_game'] == '1')
    def mk(name, team, pos, pts, line):
        opp = away if team == home else home; ishome = team == home
        b = boards.get((norm(name), team)) or {}
        sal = b.get('salary'); proj = b.get('proj')
        r = dict(base, key=f"{g['game_id']}|{name}|{team}", player=name, team=team, opp=opp, pos=pos, home=ishome,
                 spread=(None if spread_home is None else (-spread_home if ishome else spread_home)),
                 rest_days=fnum(g['home_rest'] if ishome else g['away_rest']), opp_def_rank=dr.get(opp),
                 salary=sal, salary_type=b.get('salary_type'), proj=proj, injury=b.get('injury'), own=b.get('own'), own_src=b.get('own_src'),
                 fd_pts=pts, value=(round(pts / (sal / 1000), 3) if pts is not None and sal else None),
                 beat_proj=(round(pts - proj, 2) if pts is not None and proj is not None else None),
                 our_lineups=lc.get((week, norm(name))), mvp=(week, norm(name)) in MVPS or None,
                 box=line, wiki_title=None, wiki_views_7d=None, wiki_spike=None, trends_rel=None, x_mentions=None)
        return r
    seen = set()
    for k, p in P.items():
        team = t(p['team']); pos = roster_pos(p['name'], team)
        if pos not in SKILL: continue
        rows.append(mk(p['name'], team, pos, round(p['pts'], 2), '; '.join(p['line']) if isinstance(p['line'], list) else p['line'])); seen.add((norm(p['name']), team))
    for ab, d in T.items():
        rows.append(mk(fdscore.NICK and ab, t(ab), 'DST', round(d['pts'], 2), d['line'] if isinstance(d['line'], str) else '; '.join(d['line']))); seen.add((norm(ab), t(ab)))
    # salaried players with no box line (didn't record a stat / inactive / not played yet)
    for (n, team), b in boards.items():
        if team in (home, away) and (n, team) not in seen and b.get('salary'):
            nm = n
            for w, path, kind, st in BOARDS: pass
            r = mk(b.get('display', n), team, b.get('pos_fd') or roster_pos(n, team), (0.0 if final else None), 'no box line' if final else None)
            rows.append(r)
    return rows

def load_json(p, d):
    return json.load(open(p)) if os.path.exists(p) else d

def analyze(rows):
    import numpy as np, pandas as pd
    df = pd.DataFrame([r for r in rows if r.get('fd_pts') is not None])
    sig = ['salary', 'proj', 'own', 'wiki_views_7d', 'wiki_spike', 'trends_rel', 'x_mentions', 'rest_days', 'home', 'primetime', 'dome', 'temp_f', 'total_line', 'spread', 'opp_def_rank', 'kickoff_hour', 'our_lineups']
    df['kickoff_hour'] = df['kickoff_et'].str.slice(0, 2).astype(float)
    df['log_wiki'] = np.log1p(df['wiki_views_7d'].astype(float))
    sig.insert(4, 'log_wiki')
    targets = {'fd_pts': 'FD points', 'beat_proj': 'Pts minus projection', 'value': 'Pts per $1K'}
    corr = []
    for s in sig:
        for tg in targets:
            if tg not in df: continue
            sub = df[[s, tg]].dropna()
            sub = sub.astype(float)
            n = len(sub)
            if n < 8 or sub[s].nunique() < 2 or sub[tg].nunique() < 2:
                corr.append(dict(signal=s, target=tg, n=n, r=None, rho=None)); continue
            corr.append(dict(signal=s, target=tg, n=n, r=round(float(sub[s].corr(sub[tg])), 3), rho=round(float(sub[s].rank().corr(sub[tg].rank())), 3)))
    # same correlations inside salaried players only, by position (fairer)
    bypos = []
    for pos in ['QB', 'RB', 'WR', 'TE', 'K', 'DST']:
        d = df[df.pos == pos]
        for s in ['salary', 'log_wiki', 'wiki_spike', 'trends_rel', 'opp_def_rank', 'total_line', 'spread', 'home', 'dome', 'primetime', 'rest_days']:
            sub = d[[s, 'fd_pts']].dropna().astype(float)
            if len(sub) >= 10 and sub[s].nunique() > 1:
                bypos.append(dict(pos=pos, signal=s, n=len(sub), rho=round(float(sub[s].rank().corr(sub['fd_pts'].rank())), 3)))
    # bucket comparisons
    buckets = []
    def cmp(label, mask_a, mask_b, la, lb, d=df):
        a, b = d[mask_a].fd_pts, d[mask_b].fd_pts
        if len(a) >= 5 and len(b) >= 5:
            buckets.append(dict(label=label, a=la, b=lb, n_a=int(len(a)), n_b=int(len(b)), mean_a=round(float(a.mean()), 2), mean_b=round(float(b.mean()), 2), diff=round(float(a.mean() - b.mean()), 2)))
    sk = df[df.pos.isin(['QB', 'RB', 'WR', 'TE'])]
    cmp('Skill players: home vs away', sk.home == True, sk.home == False, 'home', 'away', sk)
    cmp('Skill players: dome vs outdoor', sk.dome == True, sk.dome == False, 'dome', 'outdoor', sk)
    cmp('Skill players: primetime vs day', sk.primetime == True, sk.primetime == False, 'primetime', 'day', sk)
    cmp('Skill players: favorite vs underdog', sk.spread < 0, sk.spread > 0, 'favorite', 'underdog', sk)
    cmp('Skill players: vs bottom-10 defense vs top-10', sk.opp_def_rank > 22, sk.opp_def_rank <= 10, 'soft D', 'tough D', sk)
    cmp('Skill players: game total >= 47.5 vs < 44', sk.total_line >= 47.5, sk.total_line < 44, 'high total', 'low total', sk)
    q = sk.wiki_spike.dropna()
    if len(q) > 20:
        cmp('Skill players: Wikipedia spike top quartile vs bottom', sk.wiki_spike >= q.quantile(.75), sk.wiki_spike <= q.quantile(.25), 'top 25% spike', 'bottom 25%', sk)
    sal = df[df.salary.notna() & df.pos.isin(['QB', 'RB', 'WR', 'TE'])]
    if len(sal) > 20:
        w = sal.log_wiki.dropna(); 
        if len(w) > 20:
            cmp('Salaried skill: most-viewed Wikipedia half vs least (raw pts)', sal.log_wiki >= w.median(), sal.log_wiki < w.median(), 'more views', 'fewer views', sal)
    # top patterns: strongest |rho| with n>=30, excluding trivial salary/proj
    cand = [c for c in corr if c['rho'] is not None and c['n'] >= 30 and c['signal'] not in ('salary', 'proj')]
    cand += [dict(signal=f"{b['signal']} ({b['pos']})", target='fd_pts', n=b['n'], rho=b['rho'], r=None) for b in bypos if b['n'] >= 30 and b['signal'] != 'salary']
    cand.sort(key=lambda c: -abs(c['rho']))
    top = cand[:10]
    cov = {k: int(df[k].notna().sum()) if k in df else 0 for k in ['salary', 'proj', 'own', 'wiki_views_7d', 'trends_rel', 'x_mentions', 'temp_f', 'opp_def_rank']}
    return dict(updated=dt.date.today().isoformat(), rows_scored=int(len(df)), games=int(df.game_id.nunique()), coverage=cov,
                correlations=corr, by_position=bypos, buckets=buckets, top_patterns=top,
                notes=['Spearman rho shown; |rho| < 0.1 is noise at these sample sizes. Small sample: one season, a handful of weeks.',
                       'Salaries exist only for slates we pulled boards for; most Sunday games outside Week 6 have no salary (null).',
                       'Ownership is our model estimate (Week 6 main only), not FanDuel actual ownership.',
                       'X mention volume: null. The X counts API covers only the last 7 days, so past games cannot be backfilled.',
                       'Google Trends values are relative to the term "NFL" in the same request; null where Google rate-limited us.'])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--week', type=int, action='append'); ap.add_argument('--game'); ap.add_argument('--slate', default='all')
    ap.add_argument('--trends', action='store_true'); ap.add_argument('--no-wiki', action='store_true'); ap.add_argument('--analyze-only', action='store_true')
    a = ap.parse_args()
    PJ, SJ = f'{ROOT}/players.json', f'{ROOT}/signals.json'
    store = load_json(PJ, {'rows': []}); idx = {r['key']: r for r in store['rows']}
    if not a.analyze_only:
        lc = lineup_counts()
        for wk in a.week or []:
            boards = load_boards(wk); dr = def_rank(wk)
            for g in games(wk, a.game, a.slate):
                try: rs = build_game(g, boards, lc, dr)
                except Exception as e: print('skip', g['game_id'], e); continue
                for r in rs:
                    old = idx.get(r['key'], {})
                    for k in ('wiki_title', 'wiki_views_7d', 'wiki_spike', 'trends_rel', 'x_mentions'):
                        if r.get(k) is None and old.get(k) is not None: r[k] = old[k]
                    idx[r['key']] = r
                print(g['game_id'], len(rs), 'rows')
        rows = list(idx.values())
        todo = [r for r in rows if (a.week is None or r['week'] in a.week) and r['pos'] != 'DST' and r.get('wiki_views_7d') is None]
        if not a.no_wiki and todo:
            tc = load_json(TITLES, {})
            names = sorted({r['player'] for r in todo if r['player'] not in tc})
            with ThreadPoolExecutor(8) as ex: list(ex.map(lambda n: wiki_title(n, tc), names))
            json.dump(tc, open(TITLES, 'w'))
            def f(r):
                ti = tc.get(r['player']); r['wiki_title'] = ti
                if ti: r['wiki_views_7d'], r['wiki_spike'] = wiki_views(ti, r['gameday'])
            with ThreadPoolExecutor(8) as ex: list(ex.map(f, todo))
        if a.trends: trends([r for r in rows if a.week is None or r['week'] in a.week])
        rows.sort(key=lambda r: (r['week'], r['game_id'], -(r['fd_pts'] or 0)))
        store = {'updated': dt.date.today().isoformat(), 'rows': rows}
        json.dump(store, open(PJ, 'w'), separators=(',', ':'))
    json.dump(analyze(store['rows']), open(SJ, 'w'), indent=1)
    print('players.json rows', len(store['rows']))

if __name__ == '__main__':
    main()
