#!/bin/bash
# Full pilot for one problem: explore (graph) -> grade the runs listed in grade/runs/<slug>/pilot_runs.txt -> validate.
# The run list has one *_transcript.jsonl path per line (absolute, or relative to this directory); # starts a comment.
# RUNLIST=<file> reads another list.
# usage: bash run_pilot.sh 2024/J-the-silk-road-with-robots [explore.py flags...]
set -u
cd "$(dirname "$0")"
P="$1"; shift
SLUG="$(echo "$P" | sed 's#/#_#')"
LIST="${RUNLIST:-grade/runs/$SLUG/pilot_runs.txt}"
test -f "$LIST" || { echo "missing $LIST"; exit 1; }
mkdir -p graph/logs
if [ -f "graph/graphs/$SLUG/graph.json" ]; then
    echo "$(date +%H:%M:%S) graph exists, explore skipped (graph/graphs/$SLUG/graph.json)"
else
    echo "$(date +%H:%M:%S) explore $P"
    python3 graph/explore.py --problems "$P" "$@" > "graph/logs/${SLUG}_explore.log" 2>&1 || { echo "explore failed, see graph/logs/${SLUG}_explore.log"; exit 1; }
fi
RUNS=$(sed 's/#.*//' "$LIST" | awk 'NF')     # one path per line; # starts a comment, also inline
echo "$(date +%H:%M:%S) grade $SLUG"
mkdir -p "grade/runs/$SLUG" validate/reports
python3 grade/grade.py --graph "graph/graphs/$SLUG/graph.json" --runs $RUNS --out "grade/runs/$SLUG/pilot" \
    > "grade/runs/$SLUG/pilot_grade.log" 2>&1 || { echo "grade failed, see grade/runs/$SLUG/pilot_grade.log"; exit 1; }
echo "$(date +%H:%M:%S) validate $SLUG"
python3 validate/validate.py --graph "graph/graphs/$SLUG/graph.json" --runs "grade/runs/$SLUG/pilot/runs.jsonl" \
    --out "validate/reports/$SLUG" > "validate/reports/${SLUG}_validate.log" 2>&1 || { echo "validate failed"; exit 1; }
echo "$(date +%H:%M:%S) done $SLUG"
