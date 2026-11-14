#!/bin/bash
# run_pilot.sh over a list of problems, JOBS at a time, with one line per problem in LOG.
# usage: bash run_list.sh LIST [JOBS=4] [LOG=graph/logs/run_list_<date>.log]; per-problem output: graph/logs/<slug>_pilot.log
set -u
cd "$(dirname "$0")"
LIST="$1"; JOBS="${2:-4}"; LOG="${3:-graph/logs/run_list_$(date +%Y%m%d_%H%M).log}"
echo "$(date +%H:%M:%S) $(grep -cE '^[0-9]{4}/' "$LIST") problems from $LIST, $JOBS at a time" | tee "$LOG"
grep -E '^[0-9]{4}/' "$LIST" | xargs -P "$JOBS" -I{} bash -c '
    P="{}"; S="$(echo "$P" | sed s#/#_#)"
    bash run_pilot.sh "$P" > "graph/logs/${S}_pilot.log" 2>&1; RC=$?
    echo "$(date +%H:%M:%S) $P exit $RC $(grep -h "failed\|missing" "graph/logs/${S}_pilot.log" | head -1)"' | tee -a "$LOG"
echo "$(date +%H:%M:%S) all done" | tee -a "$LOG"
