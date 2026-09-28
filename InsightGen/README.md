# InsightGen — generating short insights for ICPC problems

For each problem, a generator model writes a short "insight" (a hint). The
target agent in `../agent`
([Nemotron-Cascade-2-30B-A3B](https://huggingface.co/nvidia/Nemotron-Cascade-2-30B-A3B))
then solves the problem 5 times with that insight. The generator sees how
those runs went and writes a better insight. This repeats for 10 rounds per
problem.

The goal is the **shortest insight with which the agent does at least as well
as with the full human-written editorial**. An insight succeeds when both of
these hold:

- solved runs ≥ the editorial arm's;
- mean completion tokens ≤ 1.5 × the editorial arm's, with an unsolved run
  counted as 3M tokens.

There are two generators:

| dir | generator 
|---|---|
| `GPT/` | GPT-6 Astra through the Responses API 
| `SelfGen/` | the target agent itself

Both use the same round message, tools (`get_insight`, `get_run`,
`get_submission`, `check_insight`, `submit_insight`), insight rules and scoring
(`history.py`, which is identical in both dirs).

## Files

```
GPT/openaiGen.py              the loop: OpenAI session, Slurm, scoring, --report
GPT/eval_insight.py           GPU side: run the agent with one insight on seeds 1-5
GPT/eval_job.sh               its Slurm wrapper
GPT/plot_insight_vs_output.py insight length vs. agent output tokens
GPT/history.py                score, success rule, insight rules, what the generator sees
SelfGen/selfGen.py            submits and watches one job per problem; --report
SelfGen/generate.py           the generation session on the local model (tool-call parsing)
SelfGen/job.py                a problem's rounds on one GPU: generate, run, score
SelfGen/job.sh                its Slurm wrapper
SelfGen/history.py            copy of GPT/history.py
```

## Layout it expects

This code imports the agent from `../../agent` and reads problems from
`../../data/problems`, which is this repo's layout:

```
InsightGeneration/
  agent/          # the target agent
  InsightGen/     # this directory
  data/problems/  # the problem archive
```

The success thresholds come from the agent's editorial-arm results.

## Run

```bash
export MODEL_PATH=/path/to/Nemotron-Cascade-2-30B-A3B

cd InsightGen/GPT
export OPENAI_API_KEY=...
python3 openaiGen.py --problems 2025/J --show-prompt        # print what the model gets
python3 openaiGen.py --problem-list ../../agent/problems.txt
python3 openaiGen.py --report

cd ../SelfGen
python3 selfGen.py --problems 2025/J --stop-after-round 1   # one-round pilot
python3 selfGen.py --problem-list ../../agent/problems.txt
python3 selfGen.py --report
```

Results are written under `GPT/runs_gpt/` and `SelfGen/runs_self/` as
`<year>_<slug>/roundNN/`.
