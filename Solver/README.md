> 本目录是 `agentv3` harness 的代码（GPTv4 用它在 Slurm 上跑 solver）。下文提到的 `../agent`、`agentv2` 是更早的版本，
> 不在本 repo 里（`legacy` 分支有早期的 `agent/`）。路径、conda、Slurm 设置见根目录的 `env.example.sh`；
> 单独跑：`source ../env.sh && MODEL_PATH=$MODELS_DIR/Qwen3.6-35B-A3B CONDA_ENV=qwen PROBLEM=2024/K-tower-of-noiha sbatch contest.sh`。

# agentv3: agentv2 with a sample runner

agentv3 is agentv2 (below) with one sandbox added, because on hard problems agentv2's model kept
submitting programs that failed the statement's own samples without any way of knowing it:

* `run_samples(code)` (toolset `v3`, the default) compiles a program exactly as `submit` does and
  runs it on the problem's `data/sample-*` tests only -- never a secret test (judge.run_samples
  asserts it, tests/test_samples.py checks it). For each sample it shows the program's output next
  to the expected answer, whether the problem's checker accepts it, the running time and the end of
  stderr. It is free: not a submission, and passing the samples solves nothing. Every call is logged
  to `<slug>_runN_samples.jsonl` (--samples-log) for the analysis afterwards.
* The system message (agent_prompt.SYSTEM_V3) replaces "there is no sandbox" with that tool and
  allows debugging output on stderr.
* A compile error shows the compiler's first errors (from the first `error:` line, at most 40
  lines) instead of the 2000-character tail, which was mostly template candidate notes.
* A turn without a tool call never ends the contest (`--max-no-tool-rounds 0`, since 2026-10-28):
  it gets a nudge, and the next turn goes on. agentv2's rule (2: one nudge, then the contest is
  over) ended 4 of the first 106 agentv3 runs, two of them within 6 minutes and before any
  submission, after Nemotron kept calling a tool that does not exist. The agentv3 baseline and
  editorial arms of 2026-10-27 ran with that old rule.
* There is no turn cap by default (`--max-rounds 0`): the 2 h clock is the only limit. A sample run
  counts as work, not idling, for the idle-round reminder.
* `check_samples.py --problem P --code FILE` runs one program on the samples the same way and
  prints the result as JSON, without vllm: the GPTv3 insight engine uses it on the login node to
  check a failed run's last program (`patch_includes` moved from run.py to judge.py for it).

Everything else -- the judge, the bare submit verdict, the store and reasoning tools, the prompts'
problem message -- is agentv2's. Compare arms only within one agent version.

# agentv2: the agent arm, with its own reasoning on tap

The contest, judge, problems and harness of `../agent`, with two changes:
a tool-call bug fixed, and a second toolset that lets the model read back its
own earlier reasoning. Everything not described here is as in
`../agent/README.md`, which remains the reference for the design.

## What the model could not see before

`../agent` keeps the last three turns in the window, and strips the reasoning
from all of them -- reasoning is the largest thing a turn produces (6.9k
tokens at the median, 131k at worst), and replaying it is exactly the cost the
arm exists to avoid. What survives a turn is its tool calls, its submitted
code (in the submission store) and a one-line `approach` note. The thinking
behind them is gone the moment the turn ends: why a greedy was dropped, a
case already ruled out, two thirds of a derivation the token budget cut off.

## The v2 toolset

`--toolset v2` (the default) adds three free, read-only tools over a second
store, `trace_store.py`, which keeps every turn's reasoning word for word:

| tool | what it does |
|---|---|
| `list_rounds` | one line per earlier turn: when it ended, tokens, how many parts its reasoning has, what it did (`submit #3 -> WA`, `get_submission(id=2)`, `cut off by the token limit`) |
| `get_reasoning(round, part=1)` | one turn's reasoning in parts of 12,000 characters, split at line breaks; the header gives the part count and the last part adds what the turn wrote after its reasoning |
| `search_reasoning(pattern, round=None)` | case-insensitive regex over every turn's reasoning, at most 6 matches shown per turn, each with the part to fetch |

With them come four smaller changes, all on in v2 and off in v1:

* The system message gains one section saying reasoning is saved and how to
  read it (`agent_prompt.SYSTEM_V2`); v1 gets `../agent`'s message byte for
  byte.
* The submission table, pinned and listed, and `get_submission` show the
  round each submission was made in -- the link from a program to the
  reasoning behind it.
* A turn cut off by the token limit is stored like any other, and its nudge
  points at it: `get_reasoning(round=3, part=4) returns where it stopped`.
* The reasoning is pointed to where it is needed, not only described up
  front. A wrong verdict, and `get_submission` on any program, end with the
  call that returns the reasoning behind it: `The reasoning that led to this
  program is saved as round 4: get_reasoning(round=4, part=7) returns the part
  where you decided to submit it; parts 1-7 hold all of it.` In the first real
  v2 run, before this, the model read its earlier programs back three times
  after wrong verdicts and its reasoning never.
* An older `get_reasoning` result in the window becomes a pointer, as an
  older `get_submission` result already did.

Only the model's own words are stored. The verdicts in `list_rounds` go
through the same `_only_verdict` as every submission tool, so nothing here can
show a judge detail the model was not shown at the time.

## Fixes that apply to both toolsets

* **Calls made from inside the reasoning** (`in_think`). The model often
  ends a turn on a complete `<tool_call>` without ever closing `</think>`.
  `../agent` filed the whole turn as reasoning, dropped the call, and ended the
  contest after two such turns. On the Qwen3.6 runs that was 258 of 342
  no-call turns, and 14 of the 22 unsolved no-insight runs ended on it rather
  than on the clock; Nemotron's runs have the same pattern. The trailing call
  blocks of a turn that stopped on its own are now run and recorded as format
  `in_think`. A block followed by more reasoning is a draft and is not run.
  `--no-in-think-calls` turns the repair off.
* **Older turns showed a tool result in place of the model's words.**
  `run()` reused the variable `content` for each tool result, so the elided
  copy of every older assistant turn carried a clip of its last tool result.
  It now carries what the model wrote.
* **The repeated-call rule** keyed a call on its name and arguments only,
  assuming nothing changes between submissions. That was already wrong for
  `list_submissions` after a submission, and `list_rounds` changes every turn.
  A call now counts as a repeat only if what it reads has not changed
  (`run._read_version`); fetching the same submission or reasoning part twice
  still does.
* **Token counting under transformers 5** (`return_dict=False`), as in
  `../agent`.

## Run it

Same as `../agent`, with `TOOLSET` (default `v2`) choosing the toolset and
the results directory `runs_<arm>_<toolset>`:

```bash
export MODEL_PATH=$MODELS_DIR/Qwen3.6-35B-A3B
export CONDA_ENV=qwen

./sweep.sh -n                    # dry run
./sweep.sh -r 1                  # no insight, v2   -> runs_baseline_v2/
./sweep.sh -i -r 1               # editorial,  v2   -> runs_insight_v2/
TOOLSET=v1 ./sweep.sh -r 1       # no insight, v1   -> runs_baseline_v1/

python3 run.py --model "$MODEL_PATH" --problem 2025/J --seed 1             # one problem
python3 run.py --model "$MODEL_PATH" --problem 2025/J --seed 1 --toolset v1
./report.py 5 -d runs_baseline_v2
```

Each run writes four files, one more than `../agent` for v2:

```
runs_<arm>_<toolset>/<year>_<slug>_run<N>_summary.json
                                     _transcript.jsonl
                                     _submissions.jsonl
                                     _reasoning.jsonl     v2 only: one line per turn
```

The summary adds `toolset`, `in_think_calls` and, for v2, `reasoning_store`.
Each transcript round carries `did`, the same phrase `list_rounds` shows.

## Files

```
run.py            the contest loop; toolset, reasoning store, the fixes above
tools.py          v1's five tools + REASONING_TOOLS; TOOLSETS; parsing per toolset
trace_store.py    new: the reasoning store and its three renderers
store.py          the submission store; optional round column
agent_prompt.py   SYSTEM (v1, unchanged) and SYSTEM_V2
prompt.py  problem.py  judge.py    unchanged copies from ../agent
contest.sh  sweep.sh  report.py    as in ../agent, plus TOOLSET
problems.txt      the 24 problems
```
