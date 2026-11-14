# Copy to env.sh (git-ignored), fill in, and `source env.sh` before running anything.
# Every variable has a default under this repository (data/, models/), so only the ones that differ are needed.

# OpenAI API (graph explorer, grader, insight writer)
export OPENAI_API_KEY=

# ICPC WF archive: one directory per problem (<year>/<L>-<slug>/ with the statement, data/sample, data/secret,
# solution.tex, solution.cpp) plus _verify/judging.json. Default: data/ICPC_WF
export WF_ARCHIVE=/path/to/ICPC_WF

# Optional: earlier solver runs (index.jsonl + <dir>/<slug>_runN_transcript.jsonl). GPTv4 grades the model's
# no-hint runs from here; without it, it runs a baseline arm on the GPU first. Default: data/RunPool
export RUNPOOL=/path/to/RunPool

# Solver checkpoints: $MODELS_DIR/Qwen3.6-35B-A3B and $MODELS_DIR/Nemotron-Cascade-2-30B-A3B. Default: models/
export MODELS_DIR=/path/to/models

# Conda: the solver jobs `conda activate qwen|nemotron` (vLLM); GPTv4 counts tokens with
# $CONDA_ENVS/<env>/bin/python (transformers). Default CONDA_SH: from `conda info --base`.
export CONDA_SH=/path/to/anaconda3/etc/profile.d/conda.sh
export CONDA_ENVS=/path/to/conda_envs

# Slurm: partition of the solver jobs (default ailab) and the account sbatch charges
export SLURM_PARTITION=ailab
export SBATCH_ACCOUNT=
