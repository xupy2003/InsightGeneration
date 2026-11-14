#!/bin/bash
# Build the graph of every problem in a list file, N at a time: one explore.py process and one
# graph/logs/<slug>_explore.log per problem (the same files run_pilot.sh writes). explore.py itself skips a
# problem that already has graph.json, so the script is safe to rerun after a failure.
#   bash explore_list.sh problems.txt                              # 4 at a time
#   bash explore_list.sh LIST 2 --max-paths 8                      # 2 at a time, extra flags go to explore.py
# Exit lines are appended to graph/logs/explore_list_<date>.log. Run on a login node (API).
set -u
cd "$(dirname "$0")"
LIST="$1"; shift
N=4
if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]+$ ]]; then N="$1"; shift; fi
FLAGS="$*"
mkdir -p graph/logs
SUMMARY="graph/logs/explore_list_$(date +%Y%m%d-%H%M).log"
echo "$(date +%H:%M:%S) list=$LIST parallel=$N flags='$FLAGS'" | tee -a "$SUMMARY"
grep -v '^[[:space:]]*#' "$LIST" | grep -v '^[[:space:]]*$' | xargs -P "$N" -I{} bash -c '
  P="$1"; S="$(echo "$P" | sed "s#/#_#")"
  python3 graph/explore.py --problems "$P" '"$FLAGS"' > "graph/logs/${S}_explore.log" 2>&1
  echo "$(date +%H:%M:%S) $P exit $? -> graph/logs/${S}_explore.log" >> "'"$SUMMARY"'"
' _ {}
echo "$(date +%H:%M:%S) all done" | tee -a "$SUMMARY"
