# ReasoningGraph Ver2: predefined graph + trace grading

Design draft of 2026-10-30, no code yet. Goal: for a problem, first build a **predefined reasoning graph** (nodes = lemmas /
intermediate conclusions, converging on END = the full editorial, with one more edge from END to CODE); then have a strong model
grade a weak model's run as a trajectory on this graph; finally validate and correct the graph's granularity with "AC runs reach
END, failed runs get stuck partway".

## 0. Relation to Ver1 / GPTv3

Ver1 went from a chain (layers-v2) to a DAG with per-result `uses` (layers-v3), and each of the three stages has already run into
its own problems:

| Lesson from Ver1 / GPTv3 | Constraint on Ver2 |
|---|---|
| v2 wrote the reference code's implementation choices into results; 5 of the 7 AC programs of 2013/G were judged wrong at L3.2 | A node states only "a conclusion that holds in every correct solution"; different solutions are different paths on the graph, not the wording of one result |
| v3 was fixed only by the reviewer's `route_independent` plus calibration against AC programs | Calibration is inherited directly: an AC program marks a node `not_needed` ⇒ the graph is missing a path |
| The failed baselines all got stuck at L1.1 (modeling the problem statement), a step the editorial does not write | The graph's first layer must build the problem model from the statement; it cannot start from the editorial |
| AC runs with an insight do not derive L1 at all; `strict_frontier` is all null | "AC ⇒ a path exists" holds directly only for runs without an insight; for an insight run the insight itself is first mapped to given nodes |
| Event extraction of one long trace costs about 5 million tokens; compression drops 90% of the candidates | The grader does not use Event; it reads snapshot rounds (§2.1) + programs |
| v2 put 64-bit arithmetic and exact square roots into L4.4, otherwise the chain broke | Implementation does not go into the lemma graph; it sits on the END→CODE edge as hazards |

Code reused directly: the builder / rules / reviewer loop of `InsightGen/GPTv3/Subtask/layers.py` (with a changed schema and
prompts), the chunking and the verbatim quote checks of `InsightGen/GPTv3/ErrorAnalysis/{windows,probe,programs}.py` (phases.py is
no longer needed), and the API calls of `InsightGen/GeneralGenV2/session.py`. By repository convention they are copied into this
directory (`ReasoningGraph/`) and modified there, with no cross-directory imports.

## 1. Definition of the graph (Stage A, `graph/`)

### 1.1 Nodes

A node is a conclusion about **the objects of this problem** that meets three conditions:

1. **Decidable**: a self-contained statement of ≤ 50 words ("the height of P(b,S) is max(2n−1, n−b+Σ(2x−1))"), not "derive a formula".
2. **Implementation-independent within its path**: state "what every correct solution that takes this path must obtain", not what
   the reference code does. Different proofs of the same conclusion go into `accept` (the grader accepts any correct proof); only
   **different intermediate conclusions** are different nodes.
3. **Separable**: some reasonable solver has its prerequisites but not the node (otherwise merge it into its prerequisites); and no
   reasonable solver gets only half of it (otherwise split it). This is the definition of granularity; §3.4 tests it with grading data.

Node fields:

| Field | Meaning |
|---|---|
| `id`, `name`, `kind` | `N1..Nk`, in topological order; a problem-specific name of ≤ 8 words; modeling / reformulation / key_property / algorithm / construction |
| `statement` | the conclusion itself |
| `routes` | **OR of AND**: `[["N2","N3"], ["N5"]]` means "obtainable from N2+N3, or from N5". `[[]]` means obtained directly from the statement (START implied) |
| `accept` | how a reader of the reasoning or the code decides that it holds; which other proofs also count |
| `anchors`, `source` | as in v3: names of objects in the statement; from statement / editorial / reference code |
| `traps` | empty in the first version; after grading, back-filled by clustering the wrong claims of failed runs (§3.4); the builder does not guess them |
| `depth` | derived: the longest path to START |

Three special nodes:

- **START**: the statement, implied.
- **END**: `routes` lists the **solution families**; each route is a set of nodes, and holding all of one set equals holding the
  content of the full editorial. Its `statement` says "a solver holding this set of conclusions lacks only routine coding".
- **CODE**: the single edge END→CODE carries `hazards`: constraints every correct program must meet that are not part of the
  algorithm ("n² reaches 4·10^10, beyond 32 bits", "tiles that only touch without overlapping must not be counted; zero area must be
  told apart from positive area").
  The user's hypothesis "holding the full editorial yet failing to write the code = implementation, which an insight cannot fix"
  **becomes a measurable quantity** here: the grader splits runs that reach END but fail into "tripped a named hazard" (fixable by a
  one-sentence insight; the 64-bit issue of 2025/J is one) and "other" (genuine coding problems).
  The ratio of the two is reported by §3.3, not assumed.

Why an AND-OR graph rather than a set of explicit paths: the editorial gives only one path, and "all possible solutions" cannot be
listed completely in one proposal. With AND-OR, a new path adds only the nodes of its **different intermediate conclusions**; shared
modeling nodes are not duplicated. In this representation a "path" is a **derivation**: a subgraph that contains END and in which
every node has at least one route lying entirely inside the subgraph.

### 1.2 Structural rules (Python, blocking, no model calls)

- (On 2026-10-30 all count caps were removed at the user's request: the number of nodes, routes per node, prerequisites per route,
  END routes, hazards and anchors are no longer limited; only the old build.py still keeps 5–20 nodes.)
- A path is added only with evidence: the editorial, an alternative solution the reviewer writes out and argues to be correct and
  fast enough, or an AC program that marks an existing node not_needed.
  In the AC programs of the three pilot problems (2024/I, 2025/J, 2023/C) each problem has only 1–2 solution families, and the
  divergence is concentrated in 1–2 nodes (the feasibility check of 2024/I, the subset construction of 2025/J);
  guessed paths only dilute the grader's attention, because every window judges every node once.
- A route references only smaller ids (DAG); every node is on some derivation of END, otherwise the graph is sent back (the first
  version has no dead-end nodes).
- At least one node with `routes == [[]]` (obtained directly from the statement).
- Two routes of the same node must not be equal or a subset of one another; nor may two routes of END.
- Word caps are kept only for the few fields the probes depend on: name ≤ 8, statement ≤ 50, accept ≤ 80, hazard 40 / 60; a name
  is not a generic step (`GENERIC_NAME`); a statement is not an answer table (`ANSWER_NUMBERS`).
- Anchors only produce warnings (not in the problem statement, not mentioned by the node's statement, no anchor), never a send-back.
  The code-copy check was removed (the explorer never sees the reference code anyway).

### 1.3 Building the graph: free exploration from the statement alone (changed 2026-10-30, `graph/explore.py`)

The user asked that graph building not be based on the editorial: GPT gets only the statement and explores freely; any solution it
believes correct is wrapped up as a path as long as it is correct, until it has exhausted the solutions it can think of.
Implementation:

1. **Explorer** (one long session, sees only the statement): comes up with a solution → writes the intermediate conclusions it
   depends on as new nodes (it may reference existing nodes) → submits a C++ program, `submit_path`. The judge runs the program on
   all tests (`graph/judge.py`; ICPC: samples first, then secret tests); **only AC is accepted**, and the path's END route enters the
   graph; otherwise the explorer gets the verdict, the failing test's input and a correct answer, and fixes the program; a solution
   that fails `MAX_PATH_ATTEMPTS` times in a row is recorded in `rejected` and abandoned.
2. After an acceptance the explorer is asked "is there another solution that depends on at least one conclusion not on the graph":
   if so, it goes on; if not, it calls `finish_exploration`, attaching the ideas it considered but dropped.
   Caps: `MAX_PATHS` paths, `MAX_SUBMISSIONS` submissions (20 / 60 since 2026-11-03, 12 / 40 before: once "slow approaches" were
   allowed, 2021/G and 2025/L hit 12); the number of nodes is not capped.
   The explorer does not decide for itself whether an approach is fast enough (2026-11-03): a simpler but asymptotically slower
   approach must be submitted too, and the judge decides; only an astronomically over-limit one may go unsubmitted.
   The reason: 7 no-hint AC runs on 2021/L, 2021/G and 2025/L took exactly the approaches the explorer had left unsubmitted as "too
   slow" (dense refinement with 2×10⁸ table lookups in 0.5–2.5 s and brute force with 2×10⁹ comparisons in 2.2 s are both within the
   time limit). The rules (§1.2) are checked on the merged graph, plus `check_path`:
   new nodes must be on the derivation of this path's END route, and the END route must not equal an existing one or be a subset or
   superset of it.
3. **Reviewer** (new session, sees the editorial and the reference code) judges nodes only on specific / correct / judgeable /
   route_independent (blocking) and separable / atomic / missing / end_ok / editorial_found (advisory); blocking findings go back to
   the explorer session, which **may only change text** (`revise_nodes`); ids, routes and END routes were verified by the judge and
   stay fixed. There is no longer a coverage review in which the reviewer proposes alternative solutions.
4. **No more calibration** (removed 2026-10-30). Reading AC programs alone can only show the algorithm at the key-node level; it
   cannot show that the solver reasoned its way to the lemmas, which is not what a reasoning graph is about. Whether the graph fits
   the solver is answered by steps 2 and 3, the grading and the validation of reasoning traces; validate's feedback.json is fed back
   through `explore.py --revise-from` as a text-only revision.
5. Every accepted path rewrites graph.json / png (status `exploring`); at the end the review and the history are written.
6. **Editorial fill-in** (added by the user, 2026-10-30): when the reviewer judges that the editorial's solution is not among the
   paths, an integrator session (sees the statement, the editorial, the reference code and the graph) adds the editorial as a path:
   it reuses existing nodes, is not bound by the path / node caps, and needs no judge (the reference code is the program; the judge
   runs once only for the record); the merged graph then gets one more review round (still text-only). Nodes do not record their
   origin (user's requirement); only `paths[].source` records it. So the final graph = the solutions GPT explored itself + the
   editorial's solution.

Below is the earlier editorial-based flow (`graph/build.py`, kept for comparison).

### 1.3-old Building the graph (v3's three-stage flow, plus one item)

1. **Builder** (gpt-6-astra, high): reads the statement the agent sees, the editorial and solution.cpp; calls `submit_graph`.
   Prompt essentials: model the problem from the statement; list conclusions along the editorial; **for each node ask "is there
   another intermediate conclusion that could replace it on the way to END"**, and if so add a route;
   implementation choices are not nodes, constraints are written as hazards; every node must be a place where a solver can "get stuck".
2. **Rules**: §1.2, at most 3 send-backs.
3. **Reviewer** (new session): per node judges `specific / correct / judgeable / route_independent / separable / atomic`;
   per graph judges `missing` (necessary steps not written, including problem modeling) and **`coverage`**: the reviewer itself
   writes out 1–2 other solutions it believes correct and fast enough, and checks one by one whether each can be expressed as a
   derivation on the graph; those that cannot become `missing_route` (blocking). `separable=false` ⇒ merge suggestion,
   `atomic=false` ⇒ split suggestion (advisory).
4. **Calibration** (v3's code and prompt, used directly): for ≤ 6 historical AC programs, each node is holds / contradicts /
   not_needed, with code quotes. A program marks a node `not_needed` and also marks `not_needed` the alternative nodes on all of its
   routes ⇒ missing path; `contradicts` ⇒ the node is written too narrowly. Both are blocking.
5. **Revision**: ≤ 3 rounds; the builder revises in its original session and may hold its ground in `notes`, with reasons.
6. **Output** `graph/graphs/<slug>/`: `graph.json` (schema `reasoning-graph-v2`, `version` = content hash), `graph.md`,
   `graph.dot/png`, `review.json`, `calibration.json`, `sessions.jsonl`, `history/graph_<version>.json`. Every grading result
   records `graph_version`.

Cost of the same order as v3: 3–6 high-effort calls per problem, each with the statement + editorial + code, about 100k–300k tokens.

## 2. Grading runs with a strong model (Stage B, `grade/`)

Input: a run's `*_transcript.jsonl` + `*_submissions.jsonl` + `*_summary.json` (the format of the agentv2/agentv3 solver harness,
now `Solver/`), plus `graph.json`.
Output: each node's state trajectory over time, the final states, whether END was reached, the stuck point, and the run's class.

### 2.1 What to read: snapshot rounds (settled 2026-10-30)

agentv2/v3 (the solver harness, now `Solver/`) keep only the tool calls of the last 3 rounds and no reasoning, so in every round the
model restates the problem, its own model and its plan from scratch: one round is a snapshot of the solver's belief state at that time.
Checked on the 652 runs archived by Ver1 ErrorAnalysis: reading only the windows of the last round, the stuck point of failed runs
agrees with reading all 21 windows in 81–91% of cases, for AC runs in 96–100%; reading only the first round gives 39–67% and 31–49%,
and most disagreements are first-round misunderstandings that were corrected later, the run ending up stuck elsewhere.

1. **The last substantive round** (default, always read): the last round whose reasoning has ≥ `MIN_ROUND_CHARS` characters
   (tentatively 5k) and contains a restatement of the plan; the contest stops at AC, so the last round of an AC run is the AC round.
   It gives the final states, `reached_end` and the stuck point.
   When the last round does not mention the stuck conclusion (5–11% of failed runs in Ver1 data), fall back to the previous
   substantive round. The short rounds after it (tail, each under `MIN_ROUND_CHARS`) are read together with it (2026-11-03,
   `--no-tail` turns this off): corrections in short rounds belong to the final state (2025/D Qwen run4 fixed the bug in the starting
   point of its permutation enumeration only in round 22, while the grader read only up to round 20); only 3 of the 309 graded runs
   have a tail, so the cost is negligible.
2. **The first round** (optional, `--first-round`): the initial model from the statement alone, comparable across runs and arms; an
   insight's direct effect shows here; 9/10 failed runs of 2025/J get L1.1 wrong within the first 4%.
3. **Programs**: the final program plus the programs submitted within the rounds read, ≤ 3.

**Within a round the text is still cut into windows of ≤ 24k characters, read in order.** Windows do not correspond to nodes: a
window is a time slice, every window judges the state of every node once, and a node's state is the aggregate of the windows over
time (§2.3). Two reasons to keep windows:
a round is not one state but a trajectory: in Ver1 data, 51–57% of last rounds have a node state that flips between windows of the
round, more so with Qwen's long rounds; and 24k is the size at which Ver1 verified that quote checks and judgments are reliable: one
Qwen round of 130k–300k characters is 10–12 windows, one Nemotron round 2–3, and a whole round in one call leaves the model to
resolve the back-and-forth within the round by itself, which is hard to check. A window size of 48k can be tried for Qwen in the
pilot, decided by grader agreement.

### 2.2 Two probes

**Window probe** (one call per window): for each node it gives

| State | Criterion |
|---|---|
| `established` | the current window's account of this step is substantially correct: it states or uses this conclusion (in any form `accept` admits, including correct variants that differ in order, complexity or representation); no proof required, imprecise wording also counts |
| `wrong` | states or uses something that **would make the conclusion wrong** (a rule, formula, bound or construction that gives a wrong answer on some valid input), not corrected within the window; a different correct route, a method that is slower but fast enough, or an incomplete argument does not count (narrowed 2026-10-30) |
| `working` | working on the question this node answers, but has neither obtained it nor gotten it wrong |
| `absent` | not touched |

The first three each need a **verbatim quote** (checked by the program to be a substring of the window's text) and one sentence of
the solver's own claim. The claims of `wrong` are kept for back-filling `traps` in §3.4.
There is also `off_graph` (2026-11-03): substantive conclusions the solver states or uses in the window that no node of the graph
covers, ≤ 5, with quotes, `wrong` marking whether each would make the answer wrong;
when only the off_graph entries of an answer fail the checks (a quote not from the text, etc.), after `ATTEMPTS` tries these entries
are dropped and the node judgments kept (salvage, 2026-11-03; before, the whole window was discarded, which made 2021/G Nemotron run5
fall back to an older round);
validate clusters them by text and writes them into feedback.json as candidates for new nodes or traps. The hint text gets the same
record, `hint_off_graph` (what the editorial says that the graph lacks).

**Program probe** (one call per program): for each node holds / contradicts / not_needed, for each hazard `ok / tripped`, all with
code quotes. **Since 2026-11-03 it no longer takes part in node states**: its results go only into `implemented` (the final
program's holds / contradicts / not_needed for each node) and the hazards; `code_gap` = the nodes on the reached END route that the
program contradicts, used only for diagnosing END+fail.
Reason: a node asks whether the solver holds the conclusion, and code can only show what the program does; editorial-arm runs write
AC programs by following the recipe while their model of the problem is wrong (four cases on 2025/J), and mixing programs into node
states would hide that.

**given nodes** (insight / editorial arm): the insight text goes through the window probe as one window, and the nodes judged
`established` are recorded as `given`. This also shows "where on the graph the insight puts the model".

The grader sees the graph (statement + accept) and the windows, **not the editorial**, so that it does not read the editorial's
content into the solver.

**Does the grader know the run's outcome** (checked 2026-10-31; blind by default since 2026-11-03, `--sighted` turns it off): at
first the default was not blind. Window units come from `assistant_raw` (reasoning + reply) and `tool_results`;
the latter are the judge's responses, so the last round read for an AC run always contains `Submission #k: AC -- Accepted`, and
failed runs often contain `TLE/WA`; the program probe's request stated the verdict outright. An offline check on 40 runs of four
problems: recomputing the closure without the program probe, reached_end is unchanged on 40/40 and the class changes for only 1 (the
stuck point moves to another node); of the 444 wrong and 1000 established pieces of evidence the probes quoted, none came from a
tool_result. What cannot be ruled out is a hidden bias of "judging more leniently after seeing Accepted",
hence `--blind`: drop the tool_result units, give no verdict, and use instructions that do not mention verdicts (the `_BLIND`
variants in `probe.py`); `runs.jsonl` / `grade.json` record `blind`. Verdicts the solver mentions in its own text (32 of the 40 runs)
belong to the trace itself and are not removed.
Blind and sighted grading are compared per run and per node with `validate.py --compare`.

### 2.3 Offline aggregation (`closure.py`, pure Python)

Checkpoints in time order: the windows of the first round (if read), the windows of the last substantive round, the windows of the
short rounds after it (tail), the programs submitted within that round, the final program.

- Node states are decided by the window checkpoints alone (2026-11-03; program checkpoints do not take part): within one checkpoint
  `wrong` beats `established` beats `working`; otherwise absent.
  Final state = the last state that is not absent. `S*` = the nodes the run itself ends up establishing (window or program). given is
  only recorded and used as prerequisites (frontier / unsupported are computed over S* ∪ given), and **does not count toward END**
  (changed 2026-11-02; before, S* included given, so a run whose editorial wrote out the key node necessarily reached END, and the
  editorial arm had zero discrimination).
- Adjudication (2026-11-03 night): a node whose final state after folding the windows is wrong gets one more reading of its whole
  trail (every window passage on the node + 1200 / 2000 characters of raw text before / after + each window's focus + the last 8k
  characters of the run, i.e. the end of the last substantive round and its tail, possibly spanning windows),
  which judges the solver's **final operative version**: the version it computes, decides, codes from or last restates. Claims it
  overturns (summaries / labels / arithmetic in examples / abandoned branches / versions corrected later)
  are slips, which must be listed one by one with explanations; a wrong passage not listed as a slip stands ⇒ final state wrong.
  Origin: on 2023/B the noEND of three AC runs came from a wrong summary in the last window
  (ceil/floor), a slip in side arithmetic, and a label error calling the endpoint gap cyclic, whereas N4 of 2024/G is an incomplete
  decision rule asserted repeatedly and written into the code; the two can only be told apart by reading the whole trail.
- `reached_end` ⇔ some END route has its **key node** ∈ S* **and no node of that route finally wrong** (2026-11-03: skipping is
  fine, getting it wrong is not);
  `derived_end` ⇔ some route lies entirely in S* (reported only, not a threshold: only about 1/6 of no-hint AC runs write out a full
  route). The key node is named explicitly by the explorer / integrator
  when it submits a path (`end.keys`), **defined as the path's output rule**: the construction or algorithm assertion that decides
  what the program outputs for each input (kind must be algorithm /
  construction; for a problem whose output is a construction, the key is the construction node, not the formula for the optimal
  value; complexity claims, feasibility assertions and proof steps cannot be keys, enforced by `rules.check_path`,
  and the reviewer also has key_ok). Before, a key only had to be the last conclusion such that "holding it equals holding the
  solution"; to satisfy "depends on the whole path" the explorer often wrote closing assertions such as "the whole algorithm runs
  within the limits", which the solver and the program probe could both hold detached from the earlier steps; all 6 residual runs of
  2026-11-02 came from this. The rules still require every other node of end_route
  to be an ancestor of the key node; reaching the key node counts as reaching END, and skipping intermediate conclusions on the way
  is not an error (user, 2026-10-30); intermediate nodes serve diagnostics such as unsupported,
  frontier and wrong-blocking. validate uses the same criterion; old graphs without `keys` fall back to the terminal node.
- `unsupported` = the nodes of S* none of whose routes is ⊆ S* (a conclusion established without its prerequisites). Normal in
  insight runs; many in baseline runs ⇒ the node and its prerequisites are inseparable (merge signal, §3.4), or the grader misjudged.
- `frontier` = the nodes not established but with all prerequisites of some route in S* (what can be done next).
- `stuck` = the frontier node with the most `wrong` or `working` evidence (`stuck_source` = frontier); if the frontier has no
  evidence but some node is finally wrong
  ⇒ fall back to root (the shallowest finally wrong node, `stuck_source` = root; 2026-11-03, before, such runs that "skip the
  frontier and go wrong deeper" were classed as stalled);
  if neither, and the run has `off_graph` wrong conclusions ⇒ `noEND+fail/off_graph` (working on the problem, but on things the
  graph does not have); otherwise `stalled`
  (not working on the problem: a behavior-level problem, corresponding to the blind submits / hallucinated tools of
  model-failure-profiles).
- `root` = the shallowest node that is finally wrong and none of whose used prerequisites is wrong (v2's roots rule).
- Classes:

| class | Meaning |
|---|---|
| `END+AC` | the graph covers the run correctly |
| `END+fail/hazard:Hk` | right idea, tripped a named implementation constraint; an insight can fix it |
| `END+fail/other` | right idea, a coding problem; the part that, by the user's hypothesis, an insight cannot fix |
| `noEND+AC` | the graph misses a path, the grader missed something, or too few windows were read: first escalate the run to `--plan all` and regrade; only if it is still noEND does it count as a graph problem |
| `noEND+fail/stuck:Nk` | a stuck point, the target of an insight |
| `noEND+fail/off_graph` | working on the problem, but the conclusions it states are not covered by any node (the graph misses a node or a trap) |
| `noEND+fail/stalled` | never entered the graph |

### 2.4 Output and cost

`grade/runs/<slug>/<cohort>/runs.jsonl`: one line per run, with given, each checkpoint's node states and quotes, the program
judgments, hazards, the final S*, unsupported, frontier, stuck, root, class, `graph_version`. `cache/` caches by (window hash, graph
version), `sessions.jsonl` records usage.

Per run: the last round is 2–3 windows for Nemotron and 10–12 for Qwen, doubled when the first round is read too, plus ≤ 3 programs
and 1 insight; about 5–25 calls and 50k–250k input tokens. 30 runs of one problem take about 3–5 million, as much as Event
extraction of **one** trace.

## 3. Validating the graph design (Stage C, `validate/`)

### 3.1 Which runs

We need both AC and failed runs without an insight, otherwise solved/unsolved is confounded with insight/no insight (the lesson of
Ver1 Profile). Census of the existing runs (`*_summary.json`, baseline = no insight):

| Problem | baseline AC | baseline fail | Notes |
|---|---|---|---|
| 2024/I steppe-on-it | 3 | 17 | both models |
| 2023/C three-kinds-of-dice | 4 | 6 | Nemotron |
| 2018/G panda-preserve | 4 | 3 | Nemotron |
| 2025/J stacking-cups | 1 | 21 | known Ver1 stuck point L1.1; also 237 AC runs with an insight |
| 2016/G oil, 2021/L, 2025/E | 5–8 | 2 | on the easy side |

Pilot: **2025/J** (ground truth to compare against), **2024/I** (enough AC and fail, no insight confound), **2023/C**. Then extend to
the 11 problems of `Subtask/problems.txt` and the three MA-07 problems.

### 3.2 Metrics

- **soundness** = the share of **no-hint** AC runs with reached_end (2026-11-03): a run that solved the problem on its own
  necessarily has the solution's idea in its text, and failing to find it is a problem of the graph or the grader.
  Hinted AC runs are reported separately as `hinted_ac_end` and `recipe_rate` = 1 − that: in the editorial arm, noEND+AC is not an
  error; it means the editorial supplied the method and the run gives no evidence of understanding it
  (four editorial-arm runs on 2025/J wrote AC programs following the editorial's construction while their model of how the cups stack
  was wrong). Target ≥ 0.9; each counterexample is inspected by hand once: missing path / grader miss / too few windows.
- **discrimination** = the share of failed runs that are (noEND or hazard). Target ≥ 0.8; the remaining share of `END+fail/other` is
  reported separately: it is the actual size of the "implementation dimension".
- **localization**: the stuck distribution of failed runs, aggregated per model. A graph that is too coarse (extreme: END as the only
  node) satisfies the first two trivially, so stuck must fall on ≥ 2 nodes, or agree with known results (2025/J should concentrate on
  the problem-modeling node).
- **grader reliability**: regrade 20% of the runs with another seed and compute agreement on node states; spot-check 10 quotes per
  problem by hand.

soundness and localization together pin the granularity from both sides: too coarse → localization carries no information; too fine
→ many `unsupported` in baseline AC runs (the solver never takes the two steps separately).

### 3.3 Report

`validate/reports/<slug>/report.md`: the run table (model, arm, verdict, reached_end, stuck, root, unsupported, hazards, class),
the four metrics, per-node statistics (times established and times wrong in AC / fail runs, times as stuck, co-occurrence rate with
its prerequisites), the suggestions of §3.4, and a spot-check list.
Also writes `feedback.json`, in the same format as the reviewer's findings; `build.py --revise-from feedback.json` feeds it straight
back into the builder's revision round.

### 3.4 Empirical granularity rules (inferred from data)

| Signal | Action |
|---|---|
| node N is established together with the prerequisites of some route in both AC and fail runs, is never stuck, and is often unsupported in baselines | merge it into the prerequisites |
| N is a stuck point, and the wrong claims of fail runs on N cluster into ≥ 2 kinds | split it into two nodes, one per kind; back-fill the claims into `traps` |
| the nodes of some route are not_needed / absent in every AC run | nobody takes the path: keep it but mark it `unused`; still unused after two consecutive rounds ⇒ it may be deleted |
| `noEND+AC` is still noEND after the `--plan all` re-check, and the program probe gives a set of not_needed nodes | missing path: hand it to the builder to add a route |

After a graph change the version changes and the affected windows are regraded (the cache is keyed by version); unchanged nodes are
not asked again.

## 4. Layout and implementation order

```
ReasoningGraph/
  design.md README.md config.py api.py problems.py problems.txt
  graph/    explore.py judge.py build.py rules.py prompts.py render.py  graphs/<slug>/...     # Stage A
  grade/    rounds.py windows.py probe.py programs.py closure.py grade.py  runs/<slug>/<cohort>/...   # Stage B
  validate/ validate.py  reports/<slug>/...                              # Stage C
  tests/    offline: rules, closure, the probe's quote checks, build / grade / validate end to end with a fake API
```

Implemented on 2026-10-30 (see README.md) and run on the real API since; 39 offline tests.

1. `config.py` + schema + `rules.py` + `closure.py` + tests (no API calls).
2. `build.py`: adapt the schema and the three-stage prompts from `GPTv3/Subtask/layers.py`, add the coverage review; run on 2025/J
   and compare with the existing 15-result chain.
3. `grade/`: copy the chunking and the probes from `GPTv3/ErrorAnalysis`; add round selection (`rounds.py`), the `working` state, the
   program probe and given; run on 2025/J's 10 failed baselines + 1 baseline AC + 5 editorial AC runs, compare with Ver1's "all stuck
   at L1.1".
4. `validate.py` + report + feeding `feedback.json` back; one full cycle on 2024/I: build the graph → grade → revise the graph →
   regrade.
5. Extend to 11 + 3 problems.

Everything runs on the login node (API); no GPU needed.

## 5. Trade-offs made and open questions

- END→CODE carries hazards rather than being a bare edge: this keeps the "implementation constraints a one-sentence insight can fix"
  confirmed in Ver1, and makes the user's implementation hypothesis measurable.
- The grader reads the snapshot of the last substantive round rather than everything: a 10–30× difference in cost; `noEND+AC` is
  escalated separately to a full read, so that reading too little is not counted as a graph error.
  Within a round, the 24k windows and the aggregation over time are kept, rather than putting a whole round into one call.
- No trap nodes in the first version: wrong conclusions come from failed runs; the builder does not guess them from the editorial.
- 5–20 nodes, ≤ 3 routes per node, END ≤ 4 routes: to be tuned on the pilot results.
- The editorials of 87 WF problems are GPT-generated: the builder prompt must say the editorial may be wrong, and solution.cpp and
  the judge take precedence.
- Open: when the insight engine (the GPTv3 loop) switches to reading stuck / root from `runs.jsonl` instead of ErrorAnalysis's
  blocking. Suggestion: switch once soundness meets its target on the three pilot problems.
