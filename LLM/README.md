# ICPC World Finals under contest rules, with and without the idea

A live-contest simulation over the 24 ICPC World Finals problems in `data/`
(2021–2025). The model is shown a statement, submits C++ to a real judge, and
gets back the bare verdict — `AC`/`WA`/`TLE`/`RTE`/`CE`, with no indication of
which test failed. It may resubmit until it solves the problem or the two-hour
clock runs out.

Two arms, differing in exactly one block of the prompt:

| arm | prompt | answers |
|---|---|---|
| baseline | statement, samples, limits | can the model find the idea *and* implement it? |
| insight | the same, plus the problem's `solution.tex` write-up | given the idea, can it implement it? |


## Setup

### 1. The data

Download the problems into `data/`, beside the scripts:

```bash
hf download xupy21/ICPC_Data --repo-type=dataset --local-dir data
```

```
.
├── run.py, prompt.py, problem.py, judge.py
├── contest.sh, sweep.sh, problems.txt
└── data/
    ├── problems/<year>/<slug>/   # statement, samples, secret tests, solution.cpp, solution.tex
    ├── problems/_verify/         # the checkers and interactor 4 problems need
    ├── runs/                     # our own transcripts, for comparison
    └── manifest.json
```


### 2. The model

```bash
hf download nvidia/Nemotron-Cascade-2-30B-A3B --local-dir /path/to/Nemotron-Cascade-2-30B-A3B
export MODEL_PATH=/path/to/Nemotron-Cascade-2-30B-A3B
```


### 3. The environment

What these runs used, which is the model's own recommended setup:

| | |
|---|---|
| Python | 3.11 |
| vLLM | 0.18.1 (the model card requires ≥ 0.17.1) |
| PyTorch | 2.10.0+cu128 |
| transformers | 4.57.6 |
| numpy | any — one checker, `2021/H-prehistoric-programs`, imports it |
| g++ | 11.5 or newer; `judge.py` compiles submissions with `-std=gnu++20` |

```bash
conda create -n nemotron python=3.11 && conda activate nemotron
pip install "vllm>=0.17.1" numpy
```


## Run it

```bash
./sweep.sh -n            # dry run: show what would be submitted
./sweep.sh               # baseline, run 1      -> runs_baseline/
./sweep.sh -r 2          # baseline, run 2
./sweep.sh -i            # insight,  run 1      -> runs_insight/
./sweep.sh -i -r 3       # insight,  run 3
```

A full evaluation is both arms at three seeds — six sweeps, 144 runs:

```bash
for r in 1 2 3; do ./sweep.sh -r $r; ./sweep.sh -i -r $r; done
```

Three repeats is the useful unit. A problem solved 1 of 3 times and one solved
3 of 3 are very different results, and a single run cannot tell them apart.
Each job is one GPU for up to 3h; a finished problem is skipped, so an
interrupted sweep resumes where it stopped.

`sweep.sh` submits to Slurm. Without a cluster, run problems directly:

```bash
python3 run.py --model "$MODEL_PATH" --problem 2025/J --seed 1
python3 run.py --model "$MODEL_PATH" --problem 2025/J --seed 1 --insight
```

`--problem` takes `2025/J`, `2025/J-stacking-cups`, or a path.



## Files

```
run.py        CLI, model loading, the contest loop, transcript and summary
prompt.py     the prompt the model sees; the feedback it gets back
problem.py    the World Finals archive: one problem, loaded
judge.py      compile, run and validate one submission
contest.sh    one Slurm job = one problem
sweep.sh      all 24, one arm, one repeat
problems.txt  the 24 problems
```


## Results

One summary and one transcript per problem per run:

```
runs_<arm>/<year>_<slug>_run<N>_summary.json
runs_<arm>/<year>_<slug>_run<N>_transcript.jsonl
```


`data/runs/` holds our own transcripts for the same 24 problems in the
baseline arm, if you want something to compare against.
