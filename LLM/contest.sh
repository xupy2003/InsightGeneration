#!/bin/bash
#SBATCH --job-name=wf
#SBATCH --output=logs/wf_%A_%a.out
#SBATCH --error=logs/wf_%A_%a.out
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --mem=150G
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --partition=ailab

set -x

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

source "${CONDA_SH:-/scratch/gpfs/PMITTAL/peiyang/px4668/anaconda3/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV:-nemotron}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "PROBLEM=$PROBLEM RUN=$RUN ARM=$ARM RUNS_DIR=$RUNS_DIR"
python3 run.py \
    --model "${MODEL_PATH:?set MODEL_PATH to the checkpoint directory}" \
    --problem "$PROBLEM" \
    --seed "$RUN" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
    --max-tokens-per-round "${MAX_TOKENS_PER_ROUND:-131072}" \
    --keep-last-rounds "${KEEP_LAST_ROUNDS:-1}" \
    --time-budget-seconds "${TIME_BUDGET_SECONDS:-7200}" \
    $([ "$ARM" = insight ] && echo --insight) \
    --transcript "$RUNS_DIR/${SLUG}_run${RUN}_transcript.jsonl" \
    --summary "$RUNS_DIR/${SLUG}_run${RUN}_summary.json"
