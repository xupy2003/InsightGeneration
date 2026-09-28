# agent — ICPC World Finals with a tool-using model

The same live-contest simulation as `../LLM` (the baseline), with
the same 24 problems, judge and two arms (no insight, and a human-written
editorial as the insight). The one change is where the model's history lives.

Each submission goes into a submission store, only the last few turns stay in the
conversation, and the model calls tools to read earlier ones back.

| tool | what it does |
|---|---|
| `submit` | compile and judge a C++ program; returns only the verdict |
| `list_submissions` | id, verdict, time, length and recorded approach of each submission |
| `get_submission` | one earlier submission in full |
| `diff_submissions` | unified diff between two submissions |
| `search_submissions` | regex search over sources and approach lines |

## Files

```
run.py            CLI, model loading (vLLM), the contest loop, transcript and summary
agent_prompt.py   system message, problem message, judge replies
tools.py          tool schemas, <tool_call> parsing, dispatch
store.py          the submission store (one JSONL per run)
judge.py          compile + judge (same as ../LLM)
problem.py        problem loading (same as ../LLM)
prompt.py         statement / insight rendering (same as ../LLM)
report.py         summarise a sweep across repeat runs
contest.sh        Slurm job: one problem
sweep.sh          Slurm array: all problems, one arm, one repeat
problems.txt      the 24 problems
```

## Setup

The problem archive is not included. Point `WF_ARCHIVE` at it
(`<year>/<slug>/` with `statement.txt`, `data/`, `meta.json`, ...);
`contest.sh` looks in `./data/problems` and then `../data/problems`.

```bash
export MODEL_PATH=/path/to/Nemotron-Cascade-2-30B-A3B
export WF_ARCHIVE=/path/to/data/problems
```

## Run

```bash
./sweep.sh -n          # dry run
./sweep.sh -r 1        # no-insight arm, repeat 1  -> runs_baseline/
./sweep.sh -i -r 1     # editorial arm, repeat 1  -> runs_insight/
python3 report.py 3 -d runs_insight   # summarise 3 repeats of an arm

# one problem
python3 run.py --model "$MODEL_PATH" --problem 2025/J --seed 1 [--insight]
```
