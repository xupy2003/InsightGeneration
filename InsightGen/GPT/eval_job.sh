#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --mem=150G
#SBATCH --cpus-per-task=8
#SBATCH --time=05:00:00
#SBATCH --partition=ailab
#
# One insight, five seeds, one model load. Submitted by openaiGen.py, which
# sets --job-name, --output, --time and --partition on the command line and
# passes everything below through the environment:
#
#   GEN_DIR        this directory (Slurm runs a spooled copy of the script)
#   PROBLEM        <year>/<letter>-<slug>
#   INSIGHT_FILE   the insight, as the agent will see it
#   OUT_DIR        where the per-seed files go
#   SEEDS          space-separated, e.g. "1 2 3 4 5"
#   MODEL_PATH     the target checkpoint
#
# The contest knobs default to contest.sh's, except the clock: one run gets
# TIME_BUDGET_SECONDS (1h) instead of 2h.

set -x

cd "${GEN_DIR:?}" || exit 1
[ -f eval_insight.py ] || { echo "no eval_insight.py in $GEN_DIR"; exit 1; }

export WF_ARCHIVE="${WF_ARCHIVE:-$(cd "$GEN_DIR/../../data/problems" && pwd)}"
[ -d "$WF_ARCHIVE" ] || { echo "no problem archive at $WF_ARCHIVE"; exit 1; }

source "${CONDA_SH:-/scratch/gpfs/PMITTAL/peiyang/px4668/anaconda3/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV:-nemotron}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# SEEDS is deliberately unquoted: it is a list.
python3 eval_insight.py \
    --problem "${PROBLEM:?}" \
    --model "${MODEL_PATH:?}" \
    --insight-file "${INSIGHT_FILE:?}" \
    --out-dir "${OUT_DIR:?}" \
    --seeds ${SEEDS:?} \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
    --max-tokens-per-round "${MAX_TOKENS_PER_ROUND:-131072}" \
    --keep-last-turns "${KEEP_LAST_TURNS:-3}" \
    --max-rounds "${MAX_ROUNDS:-200}" \
    --time-budget-seconds "${TIME_BUDGET_SECONDS:-3600}"
