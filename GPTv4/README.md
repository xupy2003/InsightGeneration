# GPTv4: a model-specific insight engine based on the reasoning graph

Design and rationale in [plan.md](plan.md). In one sentence: the insight is a cut of the graph: from the node set this model reaches by itself in its no-hint runs,
to the key node of some END route, the missing nodes are the content; the wording of each node targets this model's own wrong statements; each round is evaluated with real agentv3 runs (×5),
then the hinted runs are graded with **the same graph**, and the grading decides what to change in the next round.

**One node at a time (`step` mode, the default since the evening of 2026-11-03)**: round 1 writes only the first node on the route that the model does not hold; after each round's grading, look at the route's "frontier":
the first node not held by **all** runs (3/3) (held = the run derived it by itself, or the hint gave it and the run did not overturn it; given but overturned does not count. If a majority of runs (2 of 3) accept the frontier node but not all, it is not escalated yet: its hint is kept and the next node that a majority of runs also lack is added, so the next round tests both at once (user, 2026-11-04: on 2023/J Qwen two of three runs accepted N2 and went on to N4, yet the one run that contradicted it made the loop escalate three levels in a row grinding on N2); only a node that a majority of runs contradict is escalated. When the frontier node's hint is already at L4 or above and still not accepted by a majority, it is not escalated or blocked right away: if most failed runs get stuck (the grader's stuck) at a node further along the route, they have already passed the frontier and are working on later things, and their "contradictions" of the frontier are only slips along the way, so the L4 hint is kept and the first later node that a majority of runs also lack is added; only when the sticking point is the frontier itself (or earlier) does escalation continue, and the node is blocked only when L5 (pseudocode of the whole procedure, a step-by-step walk through an example, then a statement of what the model's own approach gives on that example) still fails; a stopped loop can be replanned under the new rules from the record of its last round and continued with `--reopen` (the lesson of 2023/J Nemotron r4: N2 at L4 was contradicted by 2/3, but all three runs were stuck at N4, and on N2 they only made small mistakes such as missing the last bridge crossing or a capacity off by 1). Nodes already passed (the prefix the profile shows as mastered, or ones passed 3/3 in some earlier round) stay passed unless a majority of this round's runs overturn them: one run not restating a node is just noise and does not move the frontier back (the lesson of 2024/G Nemotron r4: N4 at L4 was accepted by all three runs, but because one run left N1 in working the round was judged passed 0 and the loop stopped by mistake)). The frontier is still the node just given → that sentence was not taken up, escalate one level (conclusion → a negation aimed at the model's own misreading →
an executable rule → the rule plus a small worked example → pseudocode of the whole procedure plus a step-by-step walk through an example, L5); the frontier has moved past it → that sentence worked and the model went a few more steps by itself; add a level-1 item at the new frontier. After 5/5, compaction tries only the earlier items
(later items may have made them redundant), level downgrades, hazards, behavior. `cut` mode (`--mode cut`) is the old flow: write all missing nodes in round 1, then ablate; kept for comparison.

When every node on the route has been given and no run contradicts any of them, but some runs still did not solve (and did not reach END), there is no frontier to hint; then the route node where most of these failed runs stop (the grader's stuck node; ties go to the earlier one on the route) is escalated one level, one node per round, instead of rerunning the same text until the stall rule stops the loop (2024/G Nemotron r6: all five nodes given, 1/3, the two failures stopped at N4 and N5 respectively).

## Running

On the login node (API + sbatch), inside tmux: a round takes about 2.5 hours (3 GPU runs of 2 h in parallel + grading); confirmation rounds and control arms run 5 runs.

```bash
source ../env.sh && cd GPTv4                 # from the repo root
python3 -m unittest discover -s tests -t . -v                 # offline tests: fake API, fake solver, fake grader

python3 loop.py --problem 2024/G-kindergarten --model nemotron --write-only   # write round 1's insight only (calls the API, no GPU)
python3 loop.py --problem 2024/G-kindergarten --model nemotron                # end to end; Ctrl-C any time, a rerun resumes from state.json
python3 loop.py --problem 2024/G-kindergarten --model nemotron --status
python3 loop.py --problem 2024/G-kindergarten --model nemotron --control keynode   # control arm: one sentence for the key node only
python3 report.py [--problem P --model M] [--out report.md]
```

Common flags: `--mode step|cut --rounds1 12 --rounds2 6 --runs 3 --confirm-runs 5 --gate-runs 5 --phase2-runs 5 --phase2-min 3 --no-gate --no-confirm --dry-run` (writes the insight only and runs `sbatch --test-only`).

## What a round does (`loop.py`)

| Step | Module | What it does |
|---|---|---|
| 0 | `graph.py` | read `ReasoningGraph/graph/graphs/<slug>/graph.json`; if missing, call `explore.py` to build the graph |
| 0 | `grading.py` + `profile.py` | grading of this model's no-hint runs (first reads ReasoningGraph's `grade/runs/<slug>/pilot/runs.jsonl`, else grades the runs in RunPool, else runs the baseline arm itself) → `profile.json`: per node held / wrong / stuck, wrong statements (verbatim quotes), behavior profile (`behavior.py`) |
| 0 | `diagnose.py` | choose the route: least cost of the missing nodes, Σ(1 + wrong_rate); round 1's items: step mode = the first node on the route that is not held (cut mode = all of them), level 1 |
| 1 | `write.py` | one API call (gpt-6-astra) per item that has no text; level 1 writes only the conclusion, 2 adds a negating clause aimed at this model's misreading, 3 writes it as a case list / pseudocode, 4 adds a tiny worked example; checks: ASCII, no blank lines, solver-token cap (`tokens.py`), no complete program, no copying from the reference program / route programs (COPY_RUN 16), no node ids, no answer tables |
| 2 | `compose.py` | behavior item → node items (graph order) → hazard items, separated by blank lines → `r<k>/insight.txt` |
| 3 | `adapters/solver_agentv3.py` | `sbatch contest.sh` × 3 (confirmation rounds × 5; qwen 80G / nemotron 64G, 2.5 h), wait, read back solved and output tokens (sum of `completion_tokens` over the transcript's rounds) |
| 4 | `grading.py` | `ReasoningGraph/grade/grade.py` grades these runs blind (cache `grade_cache/`) |
| 5 | `loop.py` | score = (solved, END count, number of route nodes passed, mean depth reached on the route, −mean number of route nodes stated wrong), lexicographic; accepted if not worse than the best, otherwise roll back to the best round's snapshot (the rejected wording goes into history as a "worse" version) |
| 6 | `diagnose.update` | step: the frontier node has an item → escalate one level, it has none → add level 1 (if the same level already has a "worse" version, jump to a higher level); cut: the item at which failed runs are stuck → escalate one level; in both modes: a node the grader did not find in the hint → rewrite; a hazard tripped on END+fail → hazard item; a route node the final program contradicts → escalate and give the program evidence; stalled / zero submissions / END+fail/other in more than half → behavior item. Still stuck at the top level → that node is blocked, switch to the cheapest route without it; more than half of the failed runs stuck at a node off the route → switch to a route containing that node; jump (user, 2026-11-05): a route node after the frontier, or a node on a parallel route, overturned in each of the last 2 rounds by ≥½ of the runs (solved ones included) → immediately add an L1 item (one per round, the most overturned first), escalate if it keeps being overturned, no blocking at the top level, no route switch (2023/F Qwen overturned N9 3/3 for 7 rounds in a row while the loop was still hinting N2–N6) |

After 3/3 the round first goes through the **gate (`g<k>`)**, then compaction (user, 2026-11-06): that round's **same text** is rerun once on 5 fresh seeds (101–105),
and it passes only if solved ≥ GATE_RUNS − GATE_TOLERANCE (5 − 1 = 4). Passing goes to phase 2; failing returns to phase 1, which plans the next round from the grading of the gate's own 5 runs (more reliable than a round's 3);
the gate counts neither toward phase 1's budget nor toward stall; gates are tracked by insight text, so the same text is never tested twice, and if after a failed gate the diagnosis has nothing to change, the loop stops right away.
Reason: on 2025/J Nemotron, r2 solved all three runs, compaction ran for 6 rounds, and the final confirmation was only 3/5, so all of that compaction was wasted.

**Phase 2 compaction**: the candidate groups (step mode) are, in order, hazards, behavior, escalated items lowered back to level 1, the nodes one at a time except the last one added (in route order),
and last "shorten": all remaining items are rewritten shorter at their current levels, with a target of SHORTEN_SHARE (0.65) times the token count, no lower than SHORTEN_MIN (20); if accepted, shorten one more round.
Each group gets **PHASE2_RUNS = 5 runs** and is accepted only if solved ≥ 5 − PHASE2_TOLERANCE (4) and the END count does not drop (`PHASE2_REQUIRE_END`, currently off).
A compaction round is itself confirmation-sized, so an accepted insight gets no separate confirmation round, and **the first rejection ends phase 2** (`PHASE2_STOP_ON_FAIL`, user, 2026-11-06, "until one fails";
setting it to False restores the old binary search, which splits the rejected group in half and keeps trying). When a rewrite cannot fit the target length, the original text is kept.

The **confirmation round (`f<k>`)** has only one use left: when phase 1 has used up its budget without any round solving every run, it measures the solve rate of the best text on 5 runs (target = the best round's solve rate scaled to 5 runs, with a tolerance of 1).

## Layout

```
config.py  api.py  tokens.py  behavior.py        paths / API / solver-tokenizer counts / behavior profile (the last two copied from GPTv3)
adapters/problems.py  adapters/solver_agentv3.py problem loading (via ReasoningGraph/problems.py, ICPC) / Slurm adapter
graph.py  grading.py  profile.py  diagnose.py  write.py  compose.py  loop.py  report.py
tests/                                           offline tests (the toy graph in fixtures.py)
runs/<slug>/<model>/
    profile.json  state.json  loop.log  sessions.jsonl  grade_cache/  grade.log
    r<k>/{insight.txt, items.json, eval/<run files>, grade/runs.jsonl}      phase-1 rounds
    g<k>/...  c<k>/...  f<k>/...  ctl_keynode/...                             gate, phase 2, confirmation rounds, control arm
```

Limitation: only ICPC WF problems are supported.

Grading of the no-hint runs in step 0: the repo does not include ReasoningGraph's grading records (`ReasoningGraph/grade/runs/`), so by default the runs in `RUNPOOL` are graded with the API
(at most 10 per problem per model); to reuse old gradings, copy the old `grade/runs/<slug>/pilot/runs.jsonl` to the same location. Trace paths from before the move in old records
(`codebase/agent*`) are rewritten to point under `Solver/` by `grading.fix_trace`.

## Status (2026-11-08)

All 14 loops, 7 editorial-resistant problems × 2 models, have finished: baseline is 0/5 on all 14 pairs; the engine reaches ≥4/5 on 7 pairs,
5 of which have an editorial arm at ≤1/5 (the flagship is 2024/K: Qwen 4/5, Nemotron 5/5, editorial 0/5 on both models). 2023/J and 2024/G are stuck at N4.
The per-round outputs (`runs*/`) are not in the repo.
