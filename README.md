# InsightGeneration

Model-specific insights for weak solver models, written from a reasoning graph. For each problem we build a graph of
intermediate conclusions, grade the solver's reasoning traces against it, find the nodes this model does not reach by
itself, write hints for the missing nodes only, evaluate them with real solver runs, and revise them round by round from
the grading.

| Directory | Contents |
|---|---|
| [`ReasoningGraph/`](ReasoningGraph/) | Graph building (`graph/explore.py`: the explorer sees only the statement, and an approach becomes a path once its program is accepted by the judge; a reviewer and an integrator check it against the editorial and add the editorial's path when missing), grading (`grade/`: a run's text, window by window, into per-node states established / wrong / working / absent) and validation (`validate/`: soundness and discrimination). The graphs of 30 ICPC WF problems are in `graph/graphs/`. |
| [`GPTv4/`](GPTv4/) | The insight engine (`loop.py`): model profile → choose an END route → write hints node by node → run the solver on Slurm → grade with the same graph → escalate / move the frontier / compact → confirm. |
| [`Solver/`](Solver/) | The solver harness (agentv3): a tool-calling agent on vLLM, the ICPC judge, and `contest.sh` (one Slurm job = one 2 h run). |

Design details: [ReasoningGraph/design.md](ReasoningGraph/design.md) and [GPTv4/plan.md](GPTv4/plan.md). Each directory's
README has the full set of commands.

## Setup

```bash
pip install -r requirements.txt        # login node: openai, pytest
cp env.example.sh env.sh               # fill in OPENAI_API_KEY, the problem archive, models, conda, Slurm; env.sh is git-ignored
source env.sh
```

External data (not in the repository; `env.sh` gives the paths):

- `WF_ARCHIVE`: the ICPC WF archive, one directory per problem (statement, `data/sample`, `data/secret`, `solution.tex`, `solution.cpp`), plus `_verify/judging.json`.
- `MODELS_DIR`: the solver checkpoints `Qwen3.6-35B-A3B/` and `Nemotron-Cascade-2-30B-A3B/`; the `qwen` / `nemotron` environments under `CONDA_ENVS` (vLLM, transformers).
- `RUNPOOL` (optional): earlier solver runs (`index.jsonl`), which GPTv4 grades for the model's no-hint profile; without it, a baseline arm runs on the GPU first.

## Checks

```bash
(cd ReasoningGraph && python3 -m pytest -q tests)      # 39 offline tests (fake API)
(cd GPTv4 && python3 -m pytest -q tests)               # 40 offline tests (fake API, fake solver, fake grader)
(cd Solver && python3 -m pytest -q tests)              # 8 sample-runner tests (need WF_ARCHIVE)
python3 ReasoningGraph/graph/judge.py 2024/K-tower-of-noiha $WF_ARCHIVE/2024/K-tower-of-noiha/solution.cpp   # AC
```

## Running

```bash
cd ReasoningGraph
python3 graph/explore.py --problems 2025/J-stacking-cups              # build a graph (API, 20 min to 2 h)
python3 grade/grade.py --graph graph/graphs/2025_J-stacking-cups/graph.json --runs '<transcripts>' --out grade/runs/2025_J-stacking-cups/x
python3 validate/validate.py --graph graph/graphs/2025_J-stacking-cups/graph.json --runs grade/runs/2025_J-stacking-cups/x/runs.jsonl --out validate/reports/2025_J-stacking-cups

cd ../GPTv4                                                           # on a login node, inside tmux
python3 loop.py --problem 2024/K-tower-of-noiha --model qwen --dry-run      # grade the profile + write round 1's insight (API); jobs only go through sbatch --test-only
python3 loop.py --problem 2024/K-tower-of-noiha --model qwen                # end to end; after Ctrl-C, rerunning resumes from state.json
python3 report.py
```
