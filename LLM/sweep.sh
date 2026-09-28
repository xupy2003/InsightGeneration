#!/bin/bash
# All 53 problems, one job each, for one arm and one repeat.
#
#   ./sweep.sh -n                 # dry run: print what would be submitted
#   ./sweep.sh                    # baseline, run 1
#   ./sweep.sh -r 2               # baseline, run 2
#   ./sweep.sh -i                 # insight, run 1
#   ./sweep.sh -i -r 3            # insight, run 3
#   ./sweep.sh -c 8               # at most 8 jobs at once
#
# The two arms write to separate directories, runs_baseline and runs_insight,
# because the file names carry only problem and run number and would otherwise
# overwrite each other. A finished problem is skipped, so an interrupted sweep
# resumes without re-spending GPU hours; -f forces a resubmit.
#
# Concurrency defaults to the gpu-short QOS ceiling: MaxTRESPU is gres/gpu=44,
# and at one GPU per job that is 44 jobs.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MODEL_PATH="${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}"
LIST="${PROBLEM_LIST:-$REPO/problems.txt}"
ARM=baseline
RUN=1
CONCURRENCY=44
DRY=0
FORCE=0

while getopts "inr:c:l:fh" opt; do
    case $opt in
        i) ARM=insight ;;
        n) DRY=1 ;;
        r) RUN=$OPTARG ;;
        c) CONCURRENCY=$OPTARG ;;
        l) LIST=$OPTARG ;;
        f) FORCE=1 ;;
        h) sed -n '2,17p' "$0"; exit 0 ;;
        *) exit 1 ;;
    esac
done

RUNS_DIR="${RUNS_DIR:-$REPO/runs_$ARM}"
[ -f "$LIST" ] || { echo "no problem list at $LIST"; exit 1; }
[ -s "$MODEL_PATH/config.json" ] || { echo "no model at $MODEL_PATH"; exit 1; }
PENDING="$(mktemp)"
trap 'rm -f "$PENDING"' EXIT
total=0
while read -r p; do
    [ -z "$p" ] && continue
    total=$((total + 1))
    slug=$(echo "$p" | tr / _)
    if [ "$FORCE" -eq 0 ] && [ -s "$RUNS_DIR/${slug}_run${RUN}_summary.json" ]; then
        continue
    fi
    echo "$p" >> "$PENDING"
done < "$LIST"

n=$(wc -l < "$PENDING" | tr -d ' ')
echo "arm=$ARM  run=$RUN  model=$MODEL_PATH"
echo "results=$RUNS_DIR"
echo "total=$total  done=$((total - n))  to submit=$n  concurrency=$CONCURRENCY"
[ "$n" -eq 0 ] && { echo "nothing to do"; exit 0; }

if [ "$DRY" -eq 1 ]; then
    nl -ba "$PENDING"
    exit 0
fi

mkdir -p "$RUNS_DIR" "$REPO/logs"

# The array indexes the pending list, so keep a dated copy: $PENDING is a
# tempfile and the jobs read it after this script exits.
KEPT="$RUNS_DIR/pending-run${RUN}-$(date +%Y%m%d-%H%M%S).txt"
cp "$PENDING" "$KEPT"

sbatch --array=1-${n}%${CONCURRENCY} \
       --job-name="wf_${ARM}_run${RUN}" \
       --export=ALL,PROBLEM_LIST="$KEPT",RUN="$RUN",ARM="$ARM",RUNS_DIR="$RUNS_DIR",MODEL_PATH="$MODEL_PATH" \
       "$REPO/contest.sh"
echo "submitted; list frozen at $KEPT"
echo "results: $RUNS_DIR/<year>_<problem>_run${RUN}_summary.json"
