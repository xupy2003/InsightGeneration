# GPTv4: a model-specific insight engine based on the reasoning graph (implementation plan, 2026-11-03)

Goal: for a problem the solver model (Qwen3.6-35B-A3B / Nemotron-Cascade-2-30B-A3B, agentv3 harness) cannot solve, automatically generate a **compact**
insight that gets it solved, with fewer reasoning tokens than the editorial arm. Requirements: effect ≥ editorial / simple hint; fully automatic; end to end; the engine core is not tied to ICPC.

## 0. Inventory (this plan builds on these existing pieces)

| Piece | Location | Interfaces usable directly |
|---|---|---|
| Solver harness | `Solver/agentv3` | `run.py --insight-file F`; `contest.sh` (Slurm ailab, 1 GPU, 2 h); output `<slug>_runN_{transcript,submissions,reasoning,samples}.jsonl + summary.json`; the transcript has `completion_tokens` per round (= the measure of reasoning tokens) |
| Reasoning graph | `ReasoningGraph/graph` | `explore.py --problems P` builds the AND-OR graph from the statement only (30 problems built); `graph.json`: nodes(statement/accept/routes/traps), end.routes + keys, hazards, paths/P*.cpp |
| Grading | `ReasoningGraph/grade` | `grade.py --graph G --runs ... --out D`: per run `results[N]` (trajectory, final, claims with verbatim quotes), `given`, `established`, `reached_end`, `frontier`, `stuck`, `root`, `class`, `implemented`, `code_gap`, `hazards_tripped`, `off_graph`; blind grading and adjudication on by default |
| Validation | `ReasoningGraph/validate` | 30 problems, 309 runs: soundness 188/195, discrimination 113/114 → the grader can now serve as the loop's signal source (the "when to switch" condition left in design.md §5 is met) |
| Run pool | `RunPool` | 2485 runs, `index.jsonl` (model/problem/source/solved/insight); every problem has baseline, editorial and GPT insight arms for both models |
| Old engine | `InsightGen/GPTv3` | reusable: the writing rules and checks of `PricedGuidance/hints.py` (ASCII, COPY_RUN=16, ANSWER_NUMBERS=8, no `#include`/`main(`), `tokens.py` (counts with the solver's own tokenizer), `ErrorAnalysis/behavior.py` (behavior profile), the Slurm pattern of `launch_eval.sh` (paths are stale: agentv3 moved to `Solver/`) |
| API | `GeneralGenV2/session.py` via `ReasoningGraph/api.py` | gpt-6-astra, strict tool, retries, JSONL logging |

Conclusions left by GPTv3, adopted by GPTv4 as they are:
- Own-rate / per-token pricing / multiple-choice difficulty do not predict real solves → **the only signal is real runs + the grader**.
- Rounds going 0/5 → 0/5 carried no signal at all in GPTv3, and the loop degenerated into a random walk → GPTv4 replaces the single solve count with **progress** on the graph (depth of the nodes reached, number of ENDs).
- The best MA-07 rounds all exceeded the "½ editorial" cap, and compressing first and deleting afterwards loses formula precision → phase 1 sets no hard cap and gets compactness from "write only the nodes the model lacks"; phase 2 then does ablation compaction.
- Behavior instructions given alone (beh_only) got 0/5 on 2021/D for both models, and +1/5 when added to the editorial → the behavior layer is added only when the diagnosis finds a behavior-type failure, not by default.
- 2025/J Qwen: 3 rounds, 57 words, 0/5→5/5; editorial 776 words → compact is feasible; never succeeded on Nemotron → needs a model-specific route and wording.

## 1. Core idea

Define the insight as **a cut of the graph**: from the node set H_M that the model already reaches by itself in its no-hint runs, to the key node of some END route,
the few missing nodes are the content of the insight; the wording of each node targets the model's **own wrong statements** at that node (the grader's claims/quotes).
Different model → different H_M, different sticking points, different wrong statements → a different route chosen, different nodes written, different wording; this is the entire source of model specificity, with no guessing.

Each round is evaluated with real agentv3 runs (×5), and the hinted runs are graded with **the same graph**:
- `given` (where the insight got through) vs `established` (what the model itself took up) → a node not taken up gets a new wording / is escalated;
- new `stuck` / `root` → the next node to write;
- `hazards_tripped` / `code_gap` / `END+fail` → implementation-layer items;
- `stalled` / zero submissions / blind submissions → behavior-layer items (or change the harness).

Progress measure (per run, per round, fully offline): the depth of the deepest node on the target route that is held with no wrong, the number of reached_end, the number solved, output tokens.
This makes rounds at 0/5 comparable with each other too, so keep-best has a gradient.

## 2. Engine flow (`loop.py`, one command end to end)

```
python3 loop.py --problem 2024/G-kindergarten --model nemotron      # --resume available; state in runs/<slug>/<model>/state.json
```

1. **ensure_graph**: if `graph/graphs/<slug>/graph.json` does not exist, call `ReasoningGraph/graph/explore.py` (a new problem gets its graph automatically).
2. **round 0**: take the model's no-hint runs (RunPool first; if there are fewer than 5, run baseline with `launch` to fill up), grade them (for the 30 problems already graded, read `grade/runs/<slug>/pilot/runs.jsonl` directly).
   This gives the model profile `profile.json`: per node the held rate / wrong rate / number of times it is the stuck node, clusters of wrong statements (traps), hazards, behavior profile (behavior.py).
3. **diagnose**:
   - **Choose the route**: for each END route compute cost = Σ_{node ∉ H_M} w(node), with w set by this model's wrong rate at the node and the node's depth; take the minimum. The two models may choose different routes.
   - **Target set**: the nodes on the route ∉ H_M, in topological order. **Changed on the evening of 2026-11-03 to one node at a time (step mode)**: round 1 writes only the first missing node; after each round's grading, look at the frontier
     (the first node held in <3/5 runs): the frontier is still the node just given → escalate one level; the frontier moved past it → add a level-1 item at the new frontier; compaction comes last.
     The original "write everything in round 1, then ablate" is kept as cut mode for comparison: it can solve in round 1, but it hides "which sentence got the model past which node", compaction can only try group by group,
     and the 2025/J compaction showed that the fully given text contained at least three nodes the model could have derived by itself.
   - **Levels**: L1 conclusion only (≤ 40 words); L2 conclusion + the negation of the condition this model got wrong (from quotes); L3 case list / pseudocode of the output rule; L4 adds a tiny worked example. Escalate only when the grader judges "given but not established / wrong".
   - **Extra items**: hazards (only those this model tripped); implementation constraints for code_gap; behavior instructions (only when class is stalled, zero submissions, or END+fail/other is the majority).
4. **write** (gpt-6-astra): one call per item, input = the node's statement/accept, this model's wrong claims at this node verbatim, the previous wording and whether it was taken up, the node's predecessors in the graph (already written);
   output one paragraph of pure ASCII. Checks: COPY_RUN (against `paths/P*.cpp` and solution.cpp), ANSWER_NUMBERS, no code skeleton, solver-token count (`tokens.py`).
5. **compose**: items in route order → hazards → behavior (placed first); written to `insight.txt`.
6. **launch**: `Solver/agentv3/contest.sh` × 5 seeds (Slurm, `--insight-file`, `MAX_TOKENS_PER_ROUND=262144`), wait for completion (squeue polling, resumable).
7. **grade**: `ReasoningGraph/grade/grade.py` grades these 5 runs (blind; same graph, same cache).
8. **score / keep-best**: score = (solved, number of reached_end, mean target-route depth, −mean output tokens, −insight tokens), lexicographic; accepted only if not worse than the best, otherwise roll back to the best round's snapshot, and the writer sees the version as "tried, worse".
9. Stop: 5/5 → phase 2; round cap (default 8); a target node escalated to L4 and still not taken up, with no progress for 2 consecutive rounds → report "content failure / behavior failure" and stop.
10. **Phase 2 compaction** (default 6 rounds): ablation by group: remove the nodes this model can already establish by itself in the hinted runs (still held outside given), lower high levels to L1, remove hazards / behavior; 5 runs each time, accepted only at 5/5 with the END count not dropping, otherwise bisect; at the end a confirmation round of 5 runs.
11. **report**: baseline / editorial / the engine's final version: solved, insight tokens, mean output tokens of solved runs, per-node take-up rate.

## 3. Where model specificity lands

| Layer | Source (all from this model's own runs) | Approach |
|---|---|---|
| route choice | held set of the no-hint runs | different models take the path they are closer to (2025/L Qwen's sort + segment-tree DP is exactly the kind the explorer did not think of but that was added to the graph) |
| content nodes | stuck / root / frontier | write only what is missing, not what it already knows → compact |
| wording | verbatim quotes of the wrong claims at the node | the writer writes negated conditions aimed directly at the model's misunderstanding; escalate only when not taken up, never escalate in advance |
| implementation layer | hazards_tripped, implemented.contradicts, code_gap | added only on END+fail, one constraint per item |
| behavior layer | behavior.py profile (Nemotron blind submits / hallucinated tools; Qwen rewrites after CE, zero submissions from the 131k truncation) | added only when the diagnosis triggers it; if it has no effect for two rounds, change the harness (the user has agreed to this route) and stop spending insight length on it |
| representation | take-up rate of the previous round | for Qwen the formula version has a high take-up rate (2025/J 0.95), Nemotron not yet tested; the writer may switch representation when escalating |

## 4. Evaluation protocol (effect ≥ human-written hint / simple hint)

- Problem set: first the **six editorial-resistant problems** (2023/J, 2024/G, 2024/K, 2025/A, 2023/F, 2022/U; agentv3 baseline+editorial arms exist, graphs built, no-hint runs graded)
  + **2025/J** (has GPTv3's ground truth). Then extend to 2024/J, 2025/B, 2024/I (agentv2 arms only, see §6).
- Controls: baseline (exists), editorial (exists, not rerun), **key-node-only** (one sentence for the graph's key node, generated automatically, as the "simple hint" control, 5 runs).
- Metrics: solved/5 (final + confirmation round, 10 in total); the insight's solver tokens; mean output tokens of solved runs; unsolved runs count at their actual tokens over 2 h.
  Pass line: solved ≥ editorial and insight tokens < editorial tokens; then report the ratio of output tokens.
- Cost: per round 5 GPU runs (2.5 h wall clock, in parallel) + grading about 0.5–1.5M input tokens + writing about 50k; one problem × one model, phases 1+2, about 14 rounds ≈ 35 h wall clock;
  QOS 16 GPUs → 3 (problem, model) pairs in parallel.

## 5. Layout and implementation order

```
GPTv4/
  plan.md README.md config.py        # paths, models, levels, round counts, score definition
  adapters/problems.py               # → ReasoningGraph/problems.py (ICPC + AtCoder already supported)
  adapters/solver_agentv3.py         # launch / wait / collect (Slurm; paths point to Solver/agentv3)
  graph.py   grade.py                # call ReasoningGraph's explore / grade, read graph.json / runs.jsonl
  profile.py                         # model profile: held/wrong/stuck/traps/hazards/behavior
  diagnose.py                        # route choice, target set, levels, extra items, take-up check
  write.py   compose.py              # writer prompt, checks, assembly
  loop.py    report.py               # state machine + report
  tests/                             # offline tests with a fake API + fake solver
  runs/<slug>/<model>/round<k>/{diagnosis.json, items.json, insight.txt, eval/, grade/}
```

Order:
1. `config/adapters/graph/grade/profile` + offline tests (read the existing 30 problems' runs.jsonl, no API calls, no GPU): half a day.
2. `diagnose/write/compose` + fake-API tests; on 2024/G and 2023/J, generate the round-1 insight for each of the two models and review it by hand: half a day.
3. `loop` + Slurm adapter + `report`; get one round through on 2025/J Qwen (known to reach 5/5 in 3 rounds, serves as the smoke test): 1 day.
4. Real runs, six problems × two models (3 in parallel): about 1 week wall clock; along the way, fix the engine rather than the measurement, following the stop reports of §2.9.
5. Generalization check: one AtCoder problem through the whole chain (problems.py already supports it), confirming the engine core has no ICPC-specific code.

## 6. Points for the user to decide (I go with the recommendation for now; can be vetoed)

1. 2025/J, 2024/J, 2025/B, 2024/I only have agentv2 baseline/editorial arms; recommendation: do the six hard2 problems + 2025/J first; for now these four are compared against the agentv2 arms, noted as such, without running agentv3 editorial arms for them (consistent with "do not re-measure the editorial").
2. Phase 1 sets no hard cap on insight length and only reports cases above ½ editorial; phase 2 compacts.
3. The behavior layer is off by default and triggered by the diagnosis; if it has no effect for two rounds, change the harness.
4. Optional cheap pre-screen (run only 1 round and only judge whether the first round takes up the target node, about 15 min of GPU): not done for now; add it in stage 4 if iterating on wordings gets too expensive.
