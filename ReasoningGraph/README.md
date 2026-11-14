# ReasoningGraph Ver2: predefined graph → grading → validation

Design: see [design.md](design.md). Three stages:

1. **graph/** graph building (`explore.py`, the default since 2026-10-30). The explorer (gpt-6-astra) **sees only the
   statement** and explores freely: it works out an approach, writes the intermediate claims it rests on as nodes
   (`routes` = alternative combinations of earlier nodes it is derived from), and submits a C++ program that the judge
   runs on all tests; **only an AC makes it a path in the graph** (one route of END); otherwise it fixes the program and
   resubmits, and an approach is abandoned after `MAX_PATH_ATTEMPTS` consecutive failures.
   It is then asked "is there an essentially different approach that rests on at least one new claim?"; if so it
   continues, until the explorer calls `finish_exploration` to say it has exhausted them, or `MAX_PATHS` is reached
   (since 2026-11-03: 20 paths, `MAX_SUBMISSIONS` 60). **The judge decides whether it is fast enough** (2026-11-03): a
   simpler but asymptotically slower approach (brute force, dense simulation, skipping an optimization step) must be
   submitted as long as it has its own algorithm node; it may be left unsubmitted only when it exceeds the limits by an
   astronomical margin; after a TLE it gets at most one more try and is recorded in considered.
   The explorer never sees the editorial or the reference code; afterwards a reviewer uses them to check the nodes'
   truth and wording (only the text may change; the structure, verified by the judge, stays as is).
   The `hazards` on the END→CODE edge are implementation constraints the explorer found while implementing. Whether the
   graph fits real solvers is answered only by steps 2 and 3, grading and validating reasoning traces
   (the calibration that read only AC programs was removed on 2026-10-30: a program can only show the algorithm at the
   key node level, not that the solver reasoned its way to the lemmas).
   **Editorial path** (`--editorial missing`, the default): when the reviewer finds that the editorial's approach is not
   in the graph, an integrator session that sees the editorial and the reference code adds it as a path (reusing
   existing nodes, not bound by the path and node limits, no judge needed: the reference code is its program).
   Nodes do not record their origin and are the same as explored nodes; only `paths[].source` records that the path
   came from the editorial.
   `--editorial always|never` changes this behavior; `--editorial-only` runs this step alone on an existing graph.
   `build.py` is the earlier, editorial-based way of building the graph, kept for comparison.
2. **grade/** grading. For each run it reads **the last substantive round and all the short rounds after it** (the
   tail, 2026-11-03, off with `--no-tail`; optionally also the first round), cut within each round into 24k windows read
   in order; each window rates every node established / wrong / working / absent (with verbatim quotes, checked), and
   also records `off_graph` (substantive claims that no node of the graph covers); insight / editorial text
   first goes through a probe that yields `given` (recorded and used as prerequisites only, not counted toward END;
   since 2026-11-02). **Node states are decided by the windows alone** (2026-11-03): the program probe rates the final
   program holds / contradicts / not_needed and the hazards ok / tripped; the results go into `implemented` and the
   hazards, not into node states. The offline closure (`closure.py`) computes reached_end (key node held and no node on
   the route stated wrongly), derived_end, unsupported, frontier, stuck (falls back to the root when the frontier has no
   evidence), roots, code_gap and one of seven classes. Grading is blind by default (`--sighted` turns it off). When the
   last round (tail included) has every node absent, it automatically falls back to reading the previous substantive round.
   When the only defect in a window's answer is off_graph quotes that fail the check, those entries are dropped and the
   node ratings kept (salvage, 2026-11-03, recorded in `windows_salvaged`), instead of discarding the whole window.
   **Final review** (adjudication, 2026-11-03 evening): for a node whose final state after folding the windows is wrong,
   one more probe reads all its passages over the whole trace (each with the original text before and after it), each
   window's focus, and the last 8k characters of the run (the end of the last substantive round and the tail, possibly
   spanning windows; the final write-up and code), and rates the solver's **final operative version** of this step (the
   version it computes, decides or writes code from, or restates last): wrong / established / working;
   claims overridden by the solver's own computation, code or more detailed statements (summaries, labels, arithmetic
   errors in examples, abandoned branches, versions corrected later) are slips and must each be listed with an explanation;
   a wrong passage not listed as a slip stands, and the final state remains wrong. The windows' rating is kept as
   `window_final`, shown in the report as `x ⇒ +`. `--no-adjudicate` turns it off.
3. **validate/** validation. Soundness (AC ⇒ END), discrimination (fail ⇒ noEND or hazard), the END+fail/other residual,
   localization, the agreement rate between two gradings; per-node statistics; merge / split / missing-path suggestions
   are written to `feedback.json`, which `build.py --revise-from` reads directly;
   `--apply-traps` writes the wrong claims of failed runs back into the nodes' `traps`.

## Running

Run everything from the `ReasoningGraph/` directory (after `source ../env.sh`); graph building and grading must run on
the login node (API). Offline tests:

```bash
python3 -m unittest discover -s tests -t . -v        # 39 tests, fake API, no network
```

Graph building (exploration):

```bash
python3 graph/explore.py --problems 2025/J-stacking-cups        # writes graph/graphs/2025_J-stacking-cups/
python3 graph/explore.py --problems P --force [--max-paths 12] [--no-review] [--editorial missing|always|never]
python3 graph/explore.py --editorial-only --problems P           # run only the editorial path step on an existing graph
python3 graph/explore.py --revise-from validate/reports/<slug>/feedback.json --problems P   # text-only revision from the validation results
```

The criterion for END is the **key node**: **the path's output rule** (`end.keys`), named explicitly by the explorer /
integrator when it submits a path: the construction or algorithm claim that decides what the program outputs for each
input (kind must be algorithm / construction; for a problem whose output is a construction, the key is the construction
node, not a formula for the optimal value; complexity claims, feasibility claims and proof steps cannot be keys,
enforced by check_path; since 2026-11-03, before which keys were often written as closing claims such as "the whole
algorithm fits the limits" that hold even without the steps). The rules require every other node in end_route to be an
ancestor of it, so a path builds up step by step. A solver reaches END when its text holds the key node and no node on
that route is stated wrongly; skipping an intermediate claim is not an error, stating it wrongly is. Only key nodes
connect to END in the graph. Complexity is not a node of its own; it goes into the accept of the algorithm node it qualifies.

Two conventions since 2026-10-30: a node's statement states only the claim itself (no complexity, scan order,
tie-break, placement of special cases, or one particular formula among equivalent ones; these go into accept as
"also counts" examples); grading is relaxed to match: `wrong` records only substantive errors that make the claim wrong,
and an algorithm described correctly but with a different order, complexity or representation counts as established
(the probe cache version is bumped to 2). validate's feedback.json is fed back through `--revise-from` as text-only
revisions; a missing path goes through the editorial path step or a new exploration.

```bash
python3 graph/explore.py --list
python3 graph/judge.py 2025/J-stacking-cups some.cpp             # run the judge once on its own
```

During exploration, graph.json / graph.md / graph.png are rewritten after every accepted path (status `exploring`), so
they can be viewed at any time. `paths/P<k>.cpp` is the AC program of each path; `judged.jsonl` and `judged/` record
every submission.

The old editorial-based way (for comparison): `python3 graph/build.py --problems P [--audit-only|--revise-from F]`.

Problem names are written `2025/J-stacking-cups` (`wf2025/J-...` is also accepted). This repo ships only the ICPC WF
loader; AtCoder names are recognized, but their loader (CategoryEval) is not here.

Grading (first `--dry-run` to see what will be read):

```bash
python3 grade/grade.py --graph graph/graphs/2025_J-stacking-cups/graph.json \
    --runs '/path/to/runs/*/baseline/2025_J-stacking-cups_run*_transcript.jsonl' \
    --out grade/runs/2025_J-stacking-cups/baseline --first-round --dry-run
python3 grade/grade.py ... --out grade/runs/2025_J-stacking-cups/baseline --first-round --workers 8
```

Validation and feeding back:

```bash
python3 validate/validate.py --graph graph/graphs/2025_J-stacking-cups/graph.json \
    --runs grade/runs/2025_J-stacking-cups/*/runs.jsonl --out validate/reports/2025_J-stacking-cups \
    [--compare grade/runs/2025_J-stacking-cups-seed2/*/runs.jsonl] [--apply-traps]
python3 graph/build.py --revise-from validate/reports/2025_J-stacking-cups/feedback.json --problems 2025/J-stacking-cups
```

Changing the graph changes its version; grading results record `graph_version`, and validate warns when the versions
differ. The cache is keyed on (request content, graph version), so unchanged content is not requested again.

End to end (build the graph → grade the runs listed in `grade/runs/<slug>/pilot_runs.txt` → validate):

```bash
bash run_pilot.sh 2024/J-the-silk-road-with-robots        # logs in graph/logs/<slug>_{explore,pilot}.log, grade/runs/<slug>/pilot_grade.log
```

Building graphs in batch from a list (one explore.py process and one `graph/logs/<slug>_explore.log` per problem, N in
parallel, problems that already have a graph.json are skipped, exit statuses recorded in
`graph/logs/explore_list_<date>.log`; on the login node, preferably inside tmux):

```bash
bash explore_list.sh problems.txt                                # 4 in parallel
bash explore_list.sh LIST 2 --max-paths 8                        # 2 in parallel, remaining arguments passed through to explore.py
```

`pilot_runs.txt` has one transcript path per line (absolute or relative to `ReasoningGraph/`, `#` for comments);
`RUNLIST=<file>` uses a different list.
agentv2 / agentv3 transcripts and the runs of the GPTv3 insight arm can all be read (the hint markers are the same).

**Blind grading** (`--blind`, 2026-10-31): originally grading was not blind by default: the windows include the
tool_result returned by the judge (the last round contains `AC -- Accepted`, `TLE`, etc.), and the program probe's
request also states the verdict. `--blind` removes the tool_result units entirely, gives the program probe no verdict,
and switches both probes to instructions that do not mention verdicts (`WINDOW_INSTRUCTIONS_BLIND` /
`PROGRAM_INSTRUCTIONS_BLIND`); results record `blind: true`. The request content differs, so the caches are separate by
construction, but use a separate `--out`. Mentions such as "WA last time" in the solver's own text cannot be removed.
Blind grading is now the default (`config.GRADE_BLIND`); `--sighted` turns it off.

## Files

| Directory / file | Contents |
|---|---|
| `config.py` | Paths, models, limits on node count / word count / windows, etc. |
| `api.py` | OpenAI client (`OPENAI_API_KEY`); strict tools; usage; retries; JSONL logging |
| `problems.py` | Problem name normalization, slug, `ProblemContext` (statement = the message `Solver/agent_prompt.py` gives the solver, byte for byte) |
| `graph/rules.py` | Structural rules, `depths`, `reachable`, `version_of`, `graph_text` |
| `graph/prompts.py` | Instructions for the explorer / integrator / reviewer / revision / old builder |
| `graph/explore.py` | Exploration-based graph building and CLI (default); `graphs/<slug>/{graph.json, review.json, graph.md, graph.dot/png, sessions.jsonl, judged.jsonl, paths/, judged/, history/}` |
| `graph/judge.py` | Runs all tests with the problem loader and judge from `Solver/`; samples first, then secret tests |
| `graph/build.py` | Editorial-based graph-building loop (for comparison); explore.py reuses its reviewer calls and file writing |
| `graph/render.py` | graph.md / graph.dot / graph.png |
| `grade/rounds.py` | Reads rounds; picks the last substantive round / the tail of short rounds after it / the first round / the fallback; extracts the insight text |
| `grade/windows.py` | Cuts units and windows (never across rounds) |
| `grade/probe.py` | The three probes (window / insight / program), quote checking, cache |
| `grade/programs.py` | Picks the programs to read |
| `grade/closure.py` | Node state aggregation, END / unsupported / frontier / stuck / roots / class |
| `grade/grade.py` | CLI; `runs/<slug>/<cohort>/{runs.jsonl, grade.json, report.md, cache/, sessions.jsonl}` |
| `validate/validate.py` | Metrics, suggestions, agreement rate; `reports/<slug>/{report.md, report.json, feedback.json}` |
| `tests/` | Offline tests |

## Status

Graphs for 30 ICPC WF problems are in `graph/graphs/` (the repo keeps only `graph.json`, `graph.md` and `review.json`
per problem; exploration sessions, each path's AC program, grading records and validation reports are not in the repo:
regenerate them or copy them in from the old working directory; these directories are gitignored).
On these 30 problems and 309 no-hint runs: soundness 188/195 (96%), discrimination 113/114 (2026-11-03).
