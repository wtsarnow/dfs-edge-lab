# DFS Edge Lab: update guide (wtsarnow.github.io/dfs-edge-lab)
Static site (no build). `index.html`, `app.js`, `styles.css` read the JSON files at the repo root. Never invent values: unknown = null (shown as n/a).

## Pipeline (run from /workspace/dfs-edge-lab; every step is idempotent)
| Step | Script | Writes |
|---|---|---|
| 1 | `tools/collect_signals.py` – ESPN box scores → FD points, FD boards, nflverse lines/rest/roof, Wikipedia 7-day views, Trends | players.json, signals.json |
| 2 | `tools/enrich.py [--download]` – nflverse pbp (targets, air yards, aDOT, WOPR, RZ/goal-line, EPA, CPOE, pace, neutral pass rate, PROE), snap counts, FTN charting (contested/catchable/drops/play action/blitz), officials (referee), moneylines/implied totals/wind/surface/coach, travel miles + time-zone shift, opp points allowed by position, salary change, pts/$1k, boom/bust, stack pairs | players.json, stacks.json, teams.json |
| 3 | `tools/wiki_daily.py` – daily Wikipedia series, day-before views, z-score vs 28-day baseline | wiki_daily.json, players.json |
| 4 | `tools/analyze.py` – Pattern Lab tests (Pearson/Spearman, p, BH q, small-n flags, residual vs Vegas), ANOVA factors, buckets, entries, Bot Impact history | patterns.json, entries.json, bots.json, data/*.csv |
| 5 | `tools/optimize.py` – current-week Classic lineups + bot ablation | lineups.json, bot_ablation.csv |
Shortcut: `tools/run.sh <week> <tnf|sun|snf|mnf|all|game_id>`.

Before a run: refresh `/workspace/pbp/games.csv` and `/workspace/pbp/pbp26.csv.gz` (nflverse); add new FD board/projection files to `BOARDS` in collect_signals.py. Note: FanDuel's week label is one ahead of nflverse from Week 7 on (FD Week 8 = nflverse week 7).

## Per-game run (after each game window: TNF, Sun early, Sun late, SNF, MNF)
`tools/run.sh <nflverse week> <slate>` then check the printed row counts, preview with `python3 -m http.server` and upload the files below.

## Weekly run (Tuesday after MNF)
1. Add the week to `weeks.json` (entries with fee, score, rank, field, pct, winnings; mocks count, set `estimated:true` if estimated; auto-tune changes → `autotune_history`).
2. `tools/run.sh <week> all`.

## Current-week lineups refresh (before lock, and after inactives)
1. Point `tools/optimize.py` at the new slate files: board (`w8-mocks/board_<slate>.csv`), projections (`fd-proj/classic-<date>-<slate>.csv`), `w8-main/{injuries.md,odds.md,game_script.csv,offense.md,ownership.md}`, `sim_<x>/table.md`. Missing inputs are skipped and the ablation shows them as unchanged.
2. `python3 tools/optimize.py` → lineups.json + bot_ablation.csv, then `python3 tools/analyze.py` (refreshes bots.json).
3. Official picks: put the fanduel bot's lineup in `lineups.json → official` as `{label, objective, players:[{name,pos,team,opp,salary,proj,ceil,floor,own,inj}], salary, proj, ceil, floor}`.

## Files to upload (repo root; never upload tools/cache)
index.html, app.js, styles.css, players.json, patterns.json, entries.json, bots.json, lineups.json, stacks.json, teams.json, wiki_daily.json, weeks.json, signals.json, bot_ablation.csv, data/player_games.csv, data/pattern_tests.csv, data/entries.csv, data/pick_impact.csv, UPDATE.md, tools/*.py, tools/run.sh. All files are well under 25 MB.
