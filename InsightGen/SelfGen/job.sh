#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --mem=150G
#SBATCH --cpus-per-task=8
#SBATCH --time=1-00:00:00
#SBATCH --partition=ailab
#
# Rounds FIRST_ROUND..LAST_ROUND of one problem, one model load: each round
# writes its insight, runs five seeds and is scored before the next begins.
# Submitted by selfGen.py, which sets --job-name, --output, --time and
# --partition on the command line and passes everything below through the
# environment:
#
#   GEN_DIR            this directory (Slurm runs a spooled copy of the script)
#   PROBLEM            <year>/<letter>-<slug>
#   PROBLEM_DIR        runs_self/<year>_<slug>, with reference.json in it
#   FIRST_ROUND, LAST_ROUND, ROUNDS
#                      the rounds this job does, and how many the loop has
#   MODEL_PATH         the checkpoint: the generator and the agent
#   GEN_TIME_SECONDS   the generation session's clock
#   GEN_ONLY           set to anything to write one insight and stop
#
# The contest knobs are ../GPT/eval_job.sh's: contest.sh's defaults, except
# the clock, TIME_BUDGET_SECONDS (1h) instead of 2h.

set -x

cd "${GEN_DIR:?}" || exit 1
[ -f job.py ] || { echo "no job.py in $GEN_DIR"; exit 1; }

export WF_ARCHIVE="${WF_ARCHIVE:-$(cd "$GEN_DIR/../../data/problems" && pwd)}"
[ -d "$WF_ARCHIVE" ] || { echo "no problem archive at $WF_ARCHIVE"; exit 1; }

source "${CONDA_SH:-/scratch/gpfs/PMITTAL/peiyang/px4668/anaconda3/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV:-nemotron}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

python3 job.py \
    --problem "${PROBLEM:?}" \
    --model "${MODEL_PATH:?}" \
    --problem-dir "${PROBLEM_DIR:?}" \
    --first-round "${FIRST_ROUND:?}" \
    --last-round "${LAST_ROUND:?}" \
    --rounds "${ROUNDS:?}" \
    --gen-time-seconds "${GEN_TIME_SECONDS:-7200}" \
    $([ -n "${GEN_ONLY:-}" ] && echo --gen-only) \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
    --max-tokens-per-round "${MAX_TOKENS_PER_ROUND:-131072}" \
    --keep-last-turns "${KEEP_LAST_TURNS:-3}" \
    --max-rounds "${MAX_ROUNDS:-200}" \
    --time-budget-seconds "${TIME_BUDGET_SECONDS:-3600}"
