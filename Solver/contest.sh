#!/bin/bash
#SBATCH --job-name=wfa3
#SBATCH --output=logs/wfa3_%A_%a.out
#SBATCH --error=logs/wfa3_%A_%a.out
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --mem=150G
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --partition=ailab

set -x

# Slurm copies the batch script to a spool directory before running it, so
# ${BASH_SOURCE[0]} points there and not at the repo. sweep.sh exports REPO; a
# bare sbatch falls back to the directory it was submitted from; running this
# script directly falls back to its own directory. Whichever it is, it has to
# contain run.py, or the job would start, spend twenty minutes loading a model
# and only then discover it cannot import anything.
if [ -z "${REPO:-}" ]; then
    for cand in "${SLURM_SUBMIT_DIR:-}" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; do
        [ -n "$cand" ] && [ -f "$cand/run.py" ] && { REPO="$cand"; break; }
    done
fi
[ -n "${REPO:-}" ] && [ -f "$REPO/run.py" ] || {
    echo "cannot find the repo: no run.py in SLURM_SUBMIT_DIR (${SLURM_SUBMIT_DIR:-unset})"
    echo "or beside this script. Set REPO=/path/to/agent and resubmit."
    exit 1
}
cd "$REPO" || exit 1
mkdir -p logs

if [ -z "${PROBLEM:-}" ]; then
    PROBLEM=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$PROBLEM_LIST")
fi
[ -n "$PROBLEM" ] || { echo "set PROBLEM=<year>/<letter>, or submit as an array"; exit 1; }

SLUG=$(echo "$PROBLEM" | tr / _)
RUN="${RUN:-1}"
ARM="${ARM:-baseline}"
TOOLSET="${TOOLSET:-v3}"
RUNS_DIR="${RUNS_DIR:-$REPO/runs_${ARM}_${TOOLSET}}"
mkdir -p "$RUNS_DIR"

# The ICPC WF archive: WF_ARCHIVE (see env.example.sh at the repository root), else data/ICPC_WF there.
export WF_ARCHIVE="${WF_ARCHIVE:-$REPO/../data/ICPC_WF}"
[ -d "$WF_ARCHIVE" ] || { echo "no problem archive at $WF_ARCHIVE"; exit 1; }

# conda: CONDA_SH, else the installation of the conda on PATH.
CONDA_SH="${CONDA_SH:-$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh}"
[ -f "$CONDA_SH" ] || { echo "no conda.sh at $CONDA_SH; set CONDA_SH"; exit 1; }
source "$CONDA_SH"
conda activate "${CONDA_ENV:-nemotron}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# The insight, if any. ARM=insight is the problem's own solution.tex (the
# editorial arm); INSIGHT_PICK names a generated one, one file per problem
# under INSIGHT_ROOT (insights/gpt_best3: min_tokens, shortest_success, balanced).
INSIGHT_ARGS=()
if [ "$ARM" = insight ]; then
    INSIGHT_ARGS=(--insight)
elif [ -n "${INSIGHT_PICK:-}" ]; then
    INSIGHT_FILE="${INSIGHT_ROOT:-$REPO/insights/gpt_best3}/$SLUG/$INSIGHT_PICK/insight.txt"
    [ -s "$INSIGHT_FILE" ] || { echo "no insight at $INSIGHT_FILE"; exit 1; }
    INSIGHT_ARGS=(--insight-file "$INSIGHT_FILE")
fi

echo "PROBLEM=$PROBLEM RUN=$RUN ARM=$ARM TOOLSET=$TOOLSET INSIGHT=${INSIGHT_ARGS[*]} RUNS_DIR=$RUNS_DIR WF_ARCHIVE=$WF_ARCHIVE"
python3 run.py \
    --model "${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}" \
    --problem "$PROBLEM" \
    --seed "$RUN" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
    --max-tokens-per-round "${MAX_TOKENS_PER_ROUND:-131072}" \
    --keep-last-turns "${KEEP_LAST_TURNS:-3}" \
    --max-rounds "${MAX_ROUNDS:-0}" \
    --time-budget-seconds "${TIME_BUDGET_SECONDS:-7200}" \
    "${INSIGHT_ARGS[@]}" \
    --toolset "$TOOLSET" \
    --traces "$RUNS_DIR/${SLUG}_run${RUN}_reasoning.jsonl" \
    --transcript "$RUNS_DIR/${SLUG}_run${RUN}_transcript.jsonl" \
    --summary "$RUNS_DIR/${SLUG}_run${RUN}_summary.json" \
    --store "$RUNS_DIR/${SLUG}_run${RUN}_submissions.jsonl" \
    --samples-log "$RUNS_DIR/${SLUG}_run${RUN}_samples.jsonl"
