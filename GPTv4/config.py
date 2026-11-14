"""Paths, models and knobs of the GPTv4 insight engine. Standard library only.

The engine runs on the login node: it calls the API (gpt-6-astra), submits agentv3 jobs to Slurm, and
runs ReasoningGraph's explorer and grader as subprocesses. Nothing here needs a GPU.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOLVER = REPO / "Solver"                            # the harness (agentv3)
REASONING_GRAPH = REPO / "ReasoningGraph"           # graphs (graph/graphs), grader (grade/), validate
RUNS = HERE / "runs"                                # runs/<slug>/<model>/{profile.json, state.json, r<k>/...}

# Outside the repository; the environment overrides each default (see env.example.sh).
DATA = Path(os.environ.get("INSIGHT_DATA") or REPO / "data")
ICPC_ARCHIVE = Path(os.environ.get("WF_ARCHIVE") or DATA / "ICPC_WF")   # the statements the runs saw
RUNPOOL = Path(os.environ.get("RUNPOOL") or DATA / "RunPool")    # optional: earlier solver runs, index.jsonl
MODELS_DIR = Path(os.environ.get("MODELS_DIR") or REPO / "models")    # the solver checkpoints
CONDA_ENVS = Path(os.environ.get("CONDA_ENVS") or Path.home() / ".conda" / "envs")   # <env>/bin/python

# The solver models: checkpoint, conda env (its tokenizer runs there) and the job's memory, as
# GPTv3/launch_eval.sh requested them (80G / 64G: smaller requests start sooner on ailab).
SOLVERS = {
    "qwen": {"path": MODELS_DIR / "Qwen3.6-35B-A3B", "conda_env": "qwen", "mem": "80G"},
    "nemotron": {"path": MODELS_DIR / "Nemotron-Cascade-2-30B-A3B", "conda_env": "nemotron", "mem": "64G"},
}

# --- Slurm (adapters/solver_agentv3.py); sbatch also reads SBATCH_ACCOUNT from the environment
PARTITION = os.environ.get("SLURM_PARTITION", "ailab")
JOB_TIME = "02:30:00"           # a run is 2 h of contest plus model loading
MAX_TOKENS_PER_ROUND = 262144   # a turn may use the whole context (contest.sh's 131072 cut Qwen's turns short)
TOOLSET = "v3"
POLL_S = 120                    # squeue polling while jobs run
SBATCH_RETRIES = 30             # sbatch attempts per job when the controller refuses ("job queue full"), SBATCH_RETRY_S apart
SBATCH_RETRY_S = 60
RUNS_PER_ROUND = 3              # agent runs per round (3: a round decides by majority; the final insight gets CONFIRM_RUNS)
CONFIRM_RUNS = 5                # runs of the confirmation round (and of a control arm)
CONFIRM_SEED_BASE = 100         # confirmation and control runs use seeds CONFIRM_SEED_BASE+1..: the solver replays the same first round
                                # for the same seed and prompt, so the rounds' seeds 1..RUNS_PER_ROUND must not be reused

# --- the API (api.py)
API_MODEL = "gpt-6-astra"
WRITE_EFFORT = "high"
API_RETRIES = 8                 # waits on rate limits, timeouts and server errors, per request
ASK_ATTEMPTS = 3                # answers failing the checks are sent back this many times

# --- the model's profile (profile.py): which nodes it holds by itself
HELD_MIN = 0.6                  # held: established in at least this share of its no-hint runs ...
WRONG_MAX = 0.2                 # ... and wrong in at most this share
MIN_PROFILE_RUNS = 3            # fewer graded no-hint runs than this: grade more (RunPool) or run a baseline
TRAPS_PER_NODE = 6              # distinct mistaken claims shown to the writer per node
EVIDENCE_PER_NODE = 2           # the model's own wording on the node (working / established quotes)

# --- diagnosis (diagnose.py)
LEVELS = (1, 2, 3, 4, 5)
LEVEL_TOKENS = {1: 70, 2: 130, 3: 220, 4: 320, 5: 450}   # per node item, in the solver's tokens
MOVE_ON_LEVEL = 4               # a frontier item at this level or above that the failed runs mostly work past is kept as it
                                # is and the later node hinted (diagnose.past_frontier); below it the item escalates
HAZARD_TOKENS = 60
SHORTEN_SHARE = 0.65            # phase 2 'shorten': an item is rewritten at its level within this share of its tokens ...
SHORTEN_MIN = 20                # ... but never asked to go below this many tokens
BEHAVIOR_SHARE = 0.5            # behaviour item when at least this share of failed hinted runs stalled / never submitted
IMPL_SHARE = 0.5                # ... or are END+fail/other (idea right, program wrong) -> testing procedure
MIN_GIVEN = 0.5                 # an item the grader recognizes in fewer hinted runs than this share is restated
JUMP_WRONG_SHARE = 0.5          # jump: a node beyond the frontier, on the route or on a parallel route, that is wrong in at
                                # least this share of the runs (solved runs count too) ...
JUMP_ROUNDS = 2                 # ... in each of the last this many scored rounds is hinted now, from level 1, instead of when
                                # the step order reaches it (user 2026-11-05: 2023/F Qwen contradicted N9 in 3/3 runs for 7 rounds)

# --- what a round hints (diagnose.py)
MODE = "step"                   # "step": one route node per round, the first one the model does not hold;
                                # "cut": every missing node of the route in round 1, compaction afterwards
                                # a hinted node is passed only when every run of the round holds it (diagnose.pass_min)

# --- the loop (loop.py)
ROUNDS1 = 12                    # phase 1 rounds (content), at most: a step-mode route may need one per node
ROUNDS2 = 6                     # phase 2 rounds (compaction), at most
PHASE2_MIN_SOLVED = RUNS_PER_ROUND   # phase 2 starts when the best round solved this many (--phase2-min)
PHASE2_REQUIRE_END = False      # True: a compaction is accepted only if the END count does not drop either; off since
                                # 2026-11-05 (user): a noEND+AC run is analysed by hand (2025/A Nemotron c5: the final program
                                # implemented N6 and matched the reference, the text only lacked the complexity argument)
CONFIRM_RETRIES = 2             # confirmation rounds that may undo the last accepted compaction
CONFIRM_TOLERANCE = 1           # the confirmation may fall this many runs short of the best round's rate scaled to CONFIRM_RUNS
GATE_RUNS = CONFIRM_RUNS        # the entry confirmation: a phase-1 round that solves every run is rerun on this many fresh
                                # seeds BEFORE compaction starts, and compaction starts only if it reproduces (user
                                # 2026-11-06). 2025/J Nemotron compacted an r2 that was 3/3 on three runs but only 3/5 on
                                # five, so six compaction rounds and a confirmation were spent on a text that never held.
GATE_TOLERANCE = CONFIRM_TOLERANCE   # the gate may fall this many runs short of GATE_RUNS
PHASE2_RUNS = CONFIRM_RUNS      # runs of a compaction round. They are confirmation-sized, so an accepted compaction is
                                # already confirmed and no confirmation round follows phase 2.
PHASE2_TOLERANCE = CONFIRM_TOLERANCE   # a compaction is accepted when it falls at most this many runs short of PHASE2_RUNS
PHASE2_STOP_ON_FAIL = True      # the first rejected compaction ends phase 2 (user 2026-11-06, "直到失败为止"). False restores
                                # the older search, which split a failed group in halves and went on through the queue.
STALL_ROUNDS = 2                # rounds without a better score once every target is at its top level -> stop
GRADE_WORKERS = 8

# --- writing rules (write.py)
COPY_RUN = 16                   # code tokens in a row an item may share with a program (GPTv3's threshold)
ANSWER_NUMBERS = 8              # distinct integers absent from the statement that make a text an answer table
STATED_SHARE = 0.9              # the writer is told this share of a token limit (it misjudges the solver's tokens)
