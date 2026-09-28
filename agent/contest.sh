#!/bin/bash
#SBATCH --job-name=wfa
#SBATCH --output=logs/wfa_%A_%a.out
#SBATCH --error=logs/wfa_%A_%a.out
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
RUNS_DIR="${RUNS_DIR:-$REPO/runs_$ARM}"
mkdir -p "$RUNS_DIR"

# The archive is shared with the ../llm arm and lives one level up, beside the
# two of them, rather than inside either. Set WF_ARCHIVE to override.
if [ -z "${WF_ARCHIVE:-}" ]; then
    if [ -d "$REPO/data/problems" ]; then
        export WF_ARCHIVE="$REPO/data/problems"
    else
        export WF_ARCHIVE="$REPO/../data/problems"
    fi
fi
[ -d "$WF_ARCHIVE" ] || { echo "no problem archive at $WF_ARCHIVE"; exit 1; }

source "${CONDA_SH:-/scratch/gpfs/PMITTAL/peiyang/px4668/anaconda3/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV:-nemotron}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "PROBLEM=$PROBLEM RUN=$RUN ARM=$ARM RUNS_DIR=$RUNS_DIR WF_ARCHIVE=$WF_ARCHIVE"
python3 run.py \
    --model "${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}" \
    --problem "$PROBLEM" \
    --seed "$RUN" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
    --max-tokens-per-round "${MAX_TOKENS_PER_ROUND:-131072}" \
    --keep-last-turns "${KEEP_LAST_TURNS:-3}" \
    --max-rounds "${MAX_ROUNDS:-200}" \
    --time-budget-seconds "${TIME_BUDGET_SECONDS:-7200}" \
    $([ "$ARM" = insight ] && echo --insight) \
    --transcript "$RUNS_DIR/${SLUG}_run${RUN}_transcript.jsonl" \
    --summary "$RUNS_DIR/${SLUG}_run${RUN}_summary.json" \
    --store "$RUNS_DIR/${SLUG}_run${RUN}_submissions.jsonl"
