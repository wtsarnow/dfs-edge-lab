#!/usr/bin/env bash
# Full idempotent refresh. Usage: tools/run.sh <week> [slate|game_id]   e.g. tools/run.sh 8 sun | tools/run.sh 8 2026_07_GB_DET
set -e; cd "$(dirname "$0")/.."
W=$1; X=${2:-all}
if [[ $X == 20* ]]; then python3 tools/collect_signals.py --week "$W" --game "$X"; else python3 tools/collect_signals.py --week "$W" --slate "$X"; fi
python3 tools/enrich.py --download
python3 tools/wiki_daily.py
python3 tools/analyze.py
python3 tools/optimize.py || echo "optimize skipped (missing current-week inputs)"
