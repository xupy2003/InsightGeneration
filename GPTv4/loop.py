"""The GPTv4 insight engine, end to end, for one problem and one solver model (plan.md §2).

    python3 loop.py --problem 2024/G-kindergarten --model nemotron          # resumes from runs/<slug>/<model>/state.json
    python3 loop.py --problem P --model M --write-only                      # round 1's insight only, no GPU
    python3 loop.py --problem P --model M --control keynode                 # the key-node-only control arm
    python3 loop.py --problem P --model M --status

Round 0: the graph (ReasoningGraph's explorer builds it if missing), the model's graded no-hint runs
(ReasoningGraph's pilot grading when it exists, else RunPool runs graded here, else a baseline arm run
here), the profile (profile.py), the route and the first items (diagnose.py).
Phase 1 (content), at most ROUNDS1 rounds: write the items that have no text (write.py), compose the
insight (compose.py), run RUNS_PER_ROUND agentv3 jobs (adapters/solver_agentv3.py), grade them with the
same graph (grading.py), score, keep the best (not worse = accepted), and let the hinted runs' grading
decide the next changes (diagnose.update): escalate where failed runs stop, restate what the grader did
not find, add tripped hazards, add the behavior item for behavior-type failures, switch route when a
node resists at the top level or the model keeps going elsewhere.
The gate: a phase-1 round that solves every run is rerun on GATE_RUNS fresh seeds before anything is
compacted. Reproducing it (within GATE_TOLERANCE) opens phase 2; failing it returns the loop to phase 1,
which plans the next round from the gate's own grading.
Phase 2 (compaction), at most ROUNDS2 rounds: try removing groups of items (diagnose.ablation_groups) on
PHASE2_RUNS runs each, accept a removal that still solves within PHASE2_TOLERANCE (and, with
PHASE2_REQUIRE_END, does not drop END). A compaction round is confirmation-sized, so the accepted insight
needs no confirmation afterwards and the first rejected round ends the phase (PHASE2_STOP_ON_FAIL).
A confirmation round (f) is left for the other exit: phase 1 using its budget without ever solving every
run, where it measures the best insight's rate on CONFIRM_RUNS runs.
Every step is saved to state.json; a rerun resumes. The engine runs on the login node (API, sbatch); put
it in tmux: a round is about 3 hours.
"""
import argparse
import copy
import hashlib
import json
import logging
import statistics
import sys
import time
from pathlib import Path

import api as A
import behavior as B
import compose as CP
import config as C
import diagnose as D
import grading as GR
import graph as G
import profile as P
from adapters.problems import Problem, normalize, slug_of
from write import Writer, ascii

log = logging.getLogger("gptv4.loop")


class Stop(Exception):
    pass


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 1) if xs else None


def runpool_traces(problem: str, model: str, limit_fail: int = 5, limit_ac: int = 5,
                   min_runs: int = C.MIN_PROFILE_RUNS) -> list:
    """No-hint runs of the model on the problem from RunPool, preferring the current harness: up to
    limit_fail failed and limit_ac accepted. Runs that never submitted come last and are taken only
    while fewer than min_runs others exist (they still show where the model's reasoning stops; a
    baseline arm on the GPU is the fallback after them)."""
    index = C.RUNPOOL / "index.jsonl"
    if not index.exists():
        return []
    slug = slug_of(problem)
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("model") == model and r.get("problem") == slug and not r.get("insight")]
    rank = {"agentv3": 0, "agentv2_hard": 1, "agentv2": 2, "agent": 3}
    rows.sort(key=lambda r: ((r.get("num_submissions") or 0) == 0, rank.get(str(r.get("source")).split("-")[0], 9),
                             r.get("run") or 0))
    out, n_fail, n_ac = [], 0, 0
    for r in rows:
        trace = next((f for f in r.get("files") or [] if f.endswith("_transcript.jsonl")), None)
        if not trace:
            continue
        if (r.get("num_submissions") or 0) == 0 and len(out) >= min_runs:
            continue
        if r.get("solved") and n_ac < limit_ac:
            n_ac += 1
        elif not r.get("solved") and n_fail < limit_fail:
            n_fail += 1
        else:
            continue
        out.append(str(C.RUNPOOL / r["dir"] / trace))
    return out


def primary(score: dict) -> list:
    """The ranking of a phase-1 round, best first: solved runs (the objective), then among equals the runs
    solved with the route's END reasoning (END+AC) before noEND+AC ones (an AC whose text does not carry the
    route: a judge-data gap, 2025/J f2 run 102, or a program right where the graph grades the text wrong,
    2023/F Qwen r3 and r6), END count, passed route nodes, mean reached, few wrong nodes. Solved stays first:
    ranking END+AC first (2026-11-05 00:28 to 05:50) threw away 2023/F Qwen r6, 2/3 solved with both ACs
    noEND, for r4 with one END+fail run."""
    end_ac = sum(1 for x in score.get("per_run") or [] if x.get("class") == "END+AC")
    return [score["solved"], end_ac, score["ends"], score["passed"], round(score["reached"], 1), -round(score["wrong"], 1)]


class Loop:
    def __init__(self, problem: str, model: str, *, runs_root: Path | None = None, solver=None, grader=None,
                 writer_factory=None, client=None, count=None, rounds1: int = C.ROUNDS1, rounds2: int = C.ROUNDS2,
                 runs_per_round: int = C.RUNS_PER_ROUND, phase2_min: int | None = None, confirm: bool = True,
                 gate_runs: int = C.GATE_RUNS, phase2_runs: int = C.PHASE2_RUNS, gate: bool = True,
                 dry: bool = False, problem_loader=None, graph_loader=None, mode: str | None = None,
                 confirm_runs: int = C.CONFIRM_RUNS):
        self.problem, self.model = normalize(problem), model
        self.slug = slug_of(problem)
        self.dir = (Path(runs_root) if runs_root else C.RUNS) / self.slug / model
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self.dry = dry
        self.rounds1, self.rounds2, self.runs_per_round = rounds1, rounds2, runs_per_round
        self.confirm_runs = confirm_runs
        self.gate_runs, self.phase2_runs, self.gate_enabled = gate_runs, phase2_runs, gate
        self.phase2_min = runs_per_round if phase2_min is None else min(phase2_min, runs_per_round)
        self.confirm_enabled = confirm
        self.solver = solver
        self.grader = grader or GR.grade
        self.writer_factory = writer_factory
        self._client, self._count = client, count
        self.problem_loader = problem_loader or Problem
        self.graph_loader = graph_loader or (lambda p: G.ensure(p, dry=dry))
        self.record = A.Recorder(self.dir / "sessions.jsonl")
        self.graph = self.pb = self.profile = None
        self._writer = None
        self._setup_logging()
        self.state = self._load_state()
        if mode and self.state.get("mode") and mode != self.state["mode"]:
            log.warning(f"--mode {mode} ignored: this loop's state is in {self.state['mode']} mode")
        self.state.setdefault("mode", mode or C.MODE)
        self.mode = self.state["mode"]

    # --- state and logging

    def _setup_logging(self):
        root = logging.getLogger()
        if not any(getattr(h, "_gptv4", False) for h in root.handlers):
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            fh = logging.FileHandler(self.dir / "loop.log", encoding="utf-8")
            fh.setFormatter(fmt)
            fh._gptv4 = True
            root.addHandler(fh)
            if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
                sh = logging.StreamHandler(sys.stderr)
                sh.setFormatter(fmt)
                root.addHandler(sh)
            root.setLevel(logging.INFO)
            for noisy in ("httpx", "openai", "httpcore"):
                logging.getLogger(noisy).setLevel(logging.WARNING)

    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"problem": self.problem, "model": self.model, "slug": self.slug,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"), "phase": 1, "profile": None, "baseline": None,
                "route": None, "items": {}, "rounds": [], "best": None, "blocked": [], "route_history": [],
                "ablation": None, "gates": [], "confirmed_by": None, "confirmations": [], "controls": {},
                "stopped": False, "stop_reason": None}

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_path)

    def stop(self, reason: str):
        self.state["stopped"], self.state["stop_reason"] = True, reason
        self.state["phase"] = "done"
        self.save()
        log.info(f"stopped: {reason}")

    # --- lazies

    def client(self):
        if self._client is None:
            self._client = A.client()
        return self._client

    def count(self, text: str) -> int:
        if self._count is None:
            import tokens as T
            self._count = T.counter(self.model)
        return self._count(text)

    def writer(self):
        if self._writer is None:
            codes = [self.pb.reference] if self.pb and self.pb.reference else []
            prog = G.route_program(self.graph, self.problem, self.route()) if self.route() else None
            if prog:
                codes.append(prog)
            if self.writer_factory:
                self._writer = self.writer_factory(self)
            else:
                self._writer = Writer(self.client(), self.record, self.count, self.pb.statement, codes, log=log)
        return self._writer

    def route(self) -> dict | None:
        return self.state.get("route")

    def route_dir(self, condition: str) -> Path:
        d = self.dir / condition
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- round 0

    def prepare(self):
        if self.graph is None:
            self.graph = self.graph_loader(self.problem)
        if self.pb is None:
            self.pb = self.problem_loader(self.problem)
        if not self.state.get("profile"):
            self.build_profile()
        self.profile = P.load(self.dir / self.state["profile"])
        if self.state.get("stopped"):
            return
        if not self.state.get("route"):
            route = D.choose_route(self.graph, self.profile)
            if route is None:
                raise Stop("no END route in the graph")
            route["statements"] = {nid: G.by_id(self.graph)[nid]["statement"] for nid in route["nodes"]}
            self.state["route"] = route
            self.state["route_history"].append({"round": 0, "index": route["index"], "why": "cheapest missing set"})
            self.state["items"] = D.initial_items(self.graph, self.profile, route, self.mode)
            log.info(f"route {route['index']} ({'+'.join(route['nodes'])}, key {route['key']}): missing "
                     f"{route['missing']}, held {route['held']}; alternatives: "
                     + "; ".join(f"R{t['index']} cost {t['cost']}" for t in D.route_table(self.graph, self.profile)))
            self.save()

    def build_profile(self):
        records = GR.of_model(GR.pilot_records(self.problem), self.model, hinted=False)
        source = "ReasoningGraph pilot grading"
        if len(records) < C.MIN_PROFILE_RUNS:
            traces = runpool_traces(self.problem, self.model)
            source = "RunPool runs graded here"
            if len(traces) < C.MIN_PROFILE_RUNS:
                traces = self.baseline_arm()
                source = "baseline arm run here"
            if traces:
                records = GR.of_model(self.grader(self.problem, traces, self.route_dir("r0") / "grade",
                                                  self.dir / "grade_cache", log_path=self.dir / "grade.log"),
                                      self.model, hinted=False)
        if not records:
            raise Stop("no no-hint runs of this model to profile")
        prof = P.build(self.graph, records, self.model, traces=[r["trace"] for r in records if r.get("trace")])
        P.save(prof, self.dir / "profile.json")
        self.state["profile"] = "profile.json"
        self.state["baseline"] = {"runs": prof["runs"], "solved": prof["summary"]["solved"], "source": source,
                                  "groups": prof["sources"]}
        log.info(f"profile from {prof['runs']} runs ({source}): {prof['summary']['solved']} solved; held "
                 f"{prof['held']}; stuck {prof['summary']['stuck']}")
        if prof["summary"]["solved"] == prof["runs"]:
            self.stop("the model solves the problem without a hint in every profiled run")
        self.save()

    def baseline_arm(self) -> list:
        eval_dir = self.route_dir("r0") / "eval"
        jobs = self.solver.launch(self.problem, self.model, eval_dir, "baseline", None, range(1, self.runs_per_round + 1))
        self.solver.wait(jobs, "baseline runs")
        return [r["trace"] for r in self.solver.collect(eval_dir, self.slug, range(1, self.runs_per_round + 1))]

    # --- writing

    def mistakes(self, nid: str, hinted_records: list | None = None, all_runs: bool = False) -> list:
        """The model's mistaken claims on a node: from the failed hinted runs (all hinted runs for a jump item: the
        signal that added it counts solved runs too), then the profile's."""
        rows = []
        if hinted_records:
            rows += P.distinct_claims([r for r in hinted_records if all_runs or r.get("solved") is False], nid)
        seen = {P._normal(r["claim"]) for r in rows}
        for c in (self.profile["nodes"].get(nid) or {}).get("claims") or []:
            if P._normal(c["claim"]) not in seen:
                rows.append(c)
        return rows[:C.TRAPS_PER_NODE]

    def program_errors(self, nid: str, hinted_records: list | None) -> list:
        out = []
        for r in hinted_records or []:
            imp = (r.get("implemented") or {}).get(nid) or {}
            if imp.get("status") == "contradicts":
                out.append({"quote": imp.get("quote"), "reason": imp.get("reason")})
        return out[:4]

    def hazard_evidence(self, hid: str, hinted_records: list | None) -> list:
        out = []
        for r in hinted_records or []:
            for p in r.get("programs") or []:
                for h in p.get("hazards") or []:
                    if h.get("hazard_id") == hid and h.get("status") == "tripped":
                        out.append({k: h.get(k) for k in ("quote", "reason", "note") if h.get(k)})
        return out[:4]

    def passed_nodes(self) -> list:
        """The route nodes passed so far (state), initialised from the route's profile-held prefix."""
        if self.state.get("passed_nodes") is None:
            self.state["passed_nodes"] = D.initial_passed(self.route())
            self.save()
        return list(self.state["passed_nodes"])

    def latest_records(self) -> list:
        best = self.state.get("best")
        rnd = next((r for r in self.state["rounds"] if best and r["round"] == best["round"]), None)
        return GR.load_records(self.dir / rnd["condition"] / "grade" / "runs.jsonl") if rnd and rnd.get("grade") else []

    def round_records(self, rnd: dict) -> list:
        return GR.load_records(self.dir / rnd["condition"] / "grade" / "runs.jsonl") if rnd.get("grade") else []

    def scored_before(self, r: dict) -> list:
        """The scored phase-1 rounds before r, in order (the jump rule's earlier windows)."""
        return [x for x in self.state["rounds"] if x["phase"] == 1 and x["status"] == "scored" and x["round"] < r["round"]]

    def node_route(self, nid: str) -> dict:
        """The route a node item is written against: the current route when the node is on it, else the first
        END route through the node with its statements (a jump item may hint a parallel route's node)."""
        route = self.route()
        if nid in route["nodes"]:
            return route
        own = next((x for x in G.end_routes(self.graph) if nid in x["nodes"]), None)
        if own is None:
            return route
        return dict(own, statements={x: G.by_id(self.graph)[x]["statement"] for x in own["nodes"]})

    def behavior_lines(self, hinted_records: list | None) -> list:
        traces = [r["trace"] for r in hinted_records or [] if r.get("trace")]
        beh = B.analyze(traces)["instructions"] if traces else []
        if not beh and self.profile.get("behavior"):
            beh = [tuple(x) for x in self.profile["behavior"].get("instructions") or []]
        return beh

    def write_items(self, r: dict):
        items = self.state["items"]
        records = self.latest_records() if r["phase"] == 1 else []
        held = P.held_set(self.profile)
        route = self.route()
        for it in CP.ordered({k: dict(v, text=v.get("text") or "?") for k, v in items.items()}, self.graph):
            it = items[it["id"]]
            if it.get("text"):
                continue
            previous = [{"level": h["level"], "text": h["text"], "what_the_runs_did": h.get("uptake"), "verdict": h.get("verdict")}
                        for h in it.get("history") or []][-3:]
            shorten = it.get("shorten")          # phase 2: rewrite the same content in fewer tokens
            try:
                if it["kind"] == "node":
                    node = G.by_id(self.graph)[it["node"]]
                    wroute = self.node_route(it["node"])
                    text = self.writer().node_item(
                        node, it["level"], wroute, items, held,
                        self.mistakes(it["node"], records, all_runs=it.get("rule") == "jump"),
                        (self.profile["nodes"].get(it["node"]) or {}).get("wording") or [], previous=previous,
                        program_errors=self.program_errors(it["node"], records),
                        route_program=G.route_program(self.graph, self.problem, wroute) if it["level"] >= 3 else None,
                        approach=wroute.get("approach"),
                        other_mistakes=[c for rec in records if rec.get("solved") is False
                                        for c in [x.get("claim") for x in rec.get("off_graph") or [] if x.get("wrong")]][:5],
                        shorten=shorten)
                elif it["kind"] == "hazard":
                    hz = G.hazard(self.graph, it["hazard"]) or {"id": it["hazard"], "statement": it["hazard"], "check": ""}
                    text = self.writer().hazard_item(hz, it["level"], self.hazard_evidence(it["hazard"], records), previous,
                                                     shorten=shorten)
                else:
                    text = B.text(self.behavior_lines(records), it["level"])
                    if not text:
                        text = B.text(B.instructions({"tested_share": 0.0}, B.DEFAULT_REFERENCE), it["level"])
            except A.ApiError as e:
                if shorten is None or getattr(e, "fatal", False):
                    raise
                log.warning(f"{it['id']}: no version within {shorten['limit']} tokens ({e}); keeping the longer text")
                text = shorten["from"]
            it.pop("shorten", None)
            it["text"], it["tokens"], it["written_round"] = text, self.count(text), r["condition"]
            self.save()
            log.info(f"wrote {it['id']} L{it['level']} ({it['tokens']} tok): {text[:100]!r}")
        self.freeze(r)

    def freeze(self, r: dict):
        items = self.state["items"]
        insight = CP.assemble(items, self.graph)
        errors = CP.check_insight(insight, [c for c in self.writer().codes] if self._writer else [])
        for e in errors:
            log.warning(f"{r['condition']}: {e}")
        r["insight"], r["insight_tokens"] = insight, self.count(insight)
        r["items_snapshot"] = copy.deepcopy(items)
        r["status"] = "written"
        d = self.route_dir(r["condition"])
        (d / "insight.txt").write_text(insight, encoding="utf-8")
        (d / "items.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
        self.save()
        log.info(f"{r['condition']}: insight of {r['insight_tokens']} tokens\n{CP.describe(items, self.graph)}")

    # --- evaluation and grading

    def evaluate(self, r: dict):
        d = self.route_dir(r["condition"])
        eval_dir = d / "eval"
        n = r.setdefault("n_runs", self.runs_per_round)
        # the gate and the confirmation rerun an insight a round already ran, so they need seeds that round did not use
        base = C.CONFIRM_SEED_BASE if r.get("phase") in ("confirm", "control", "gate") else 0
        seeds = range(base + 1, base + n + 1)
        if r["status"] == "written":
            r["jobs"] = self.solver.launch(self.problem, self.model, eval_dir, r["condition"], d / "insight.txt", seeds)
            r["status"] = "launched"
            self.save()
        if self.dry:
            raise Stop("dry run: the jobs were not submitted")
        self.solver.wait(r.get("jobs") or [], f"{n} runs of {r['condition']}")
        runs = self.solver.collect(eval_dir, self.slug, seeds)
        if len(runs) < n:
            missing = sorted(set(seeds) - {x["seed"] for x in runs})
            log.warning(f"{r['condition']}: seeds {missing} have no summary; relaunching them")
            r["jobs"] = self.solver.launch(self.problem, self.model, eval_dir, r["condition"], d / "insight.txt", missing)
            self.save()
            self.solver.wait(r["jobs"], f"relaunched seeds {missing}")
            runs = self.solver.collect(eval_dir, self.slug, seeds)
            if len(runs) < n:
                raise Stop(f"{r['condition']}: seeds without a summary after a relaunch: "
                           f"{sorted(set(seeds) - {x['seed'] for x in runs})}")
        r["runs"], r["status"] = runs, "evaluated"
        self.save()
        log.info(f"{r['condition']}: {sum(x['solved'] for x in runs)}/{len(runs)} solved, output tokens "
                 f"{[x['output_tokens'] for x in runs]}")

    def grade(self, r: dict) -> list:
        d = self.route_dir(r["condition"])
        records = self.grader(self.problem, [x["trace"] for x in r["runs"]], d / "grade", self.dir / "grade_cache",
                              log_path=self.dir / "grade.log")
        r["grade"], r["status"] = str((d / "grade" / "runs.jsonl").relative_to(self.dir)), "graded"
        self.save()
        return records

    def score(self, r: dict, records: list) -> dict:
        route = self.route()["nodes"]
        runs = r["runs"]
        by_seed = {x["seed"]: x for x in runs}
        prog = [GR.route_progress(rec, route) for rec in records]
        solved = sum(bool(x["solved"]) for x in runs)
        ends = sum(p["end"] for p in prog)
        reached = _mean([p["reached"] for p in prog]) or 0.0
        wrong = _mean([len(p["wrong"]) for p in prog]) or 0.0
        passed = D.passed_depth(records, route, self.passed_nodes())
        s = {"solved": solved, "runs": len(runs), "ends": ends, "passed": passed, "reached": reached, "wrong": wrong,
             "output_tokens": _mean([x["output_tokens"] for x in runs]),
             "solved_output_tokens": _mean([x["output_tokens"] for x in runs if x["solved"]]),
             "insight_tokens": r["insight_tokens"],
             "classes": dict(P.summary(records)["classes"]),
             "stuck": dict(P.summary(records)["stuck"]),
             "per_run": [{"seed": rec.get("run"), "solved": rec.get("solved"), "class": rec.get("class"),
                          "given": rec.get("given"), "held": p["held"], "wrong": p["wrong"], "reached": p["reached"],
                          "output_tokens": (by_seed.get(rec.get("run")) or {}).get("output_tokens")}
                         for rec, p in zip(records, prog)]}
        s["primary"] = primary(s)
        return s

    # --- phase 1

    def new_round(self, phase, condition_prefix: str) -> dict:
        k = len(self.state["rounds"]) + 1
        n = sum(1 for x in self.state["rounds"] if x["phase"] == phase) + 1
        r = {"round": k, "phase": phase, "condition": f"{condition_prefix}{n}", "status": "planned",
             "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.state["rounds"].append(r)
        self.save()
        return r

    def current_round(self) -> dict | None:
        return next((r for r in self.state["rounds"] if r["status"] != "scored"), None)

    def run_round(self, r: dict):
        if r["status"] == "planned":
            self.write_items(r)
        if r["status"] in ("written", "launched"):
            self.evaluate(r)
        if r["status"] == "evaluated":
            self.grade(r)
        records = GR.load_records(self.dir / r["grade"])
        if r["status"] == "graded":
            r["score"] = self.score(r, records)
            r["status"] = "scored"
            self.save()
            log.info(f"{r['condition']}: score {r['score']['primary']} (solved, END+AC, END, passed, reached, -wrong); "
                     f"classes {r['score']['classes']}")
        return records

    def phase1_round(self):
        r = self.current_round() or self.new_round(1, "r")
        if r["phase"] != 1:
            return {2: self.phase2_round, "gate": self.gate_round}.get(r["phase"], self.confirm_round)()
        records = self.run_round(r)
        best = self.state.get("best")
        accepted = best is None or primary(r["score"]) >= primary(best["score"])
        improved = best is None or primary(r["score"]) > primary(best["score"])
        r["accepted"] = accepted
        if accepted:
            self.state["best"] = {"round": r["round"], "condition": r["condition"], "primary": r["score"]["primary"],
                                  "score": r["score"], "insight": r["insight"], "insight_tokens": r["insight_tokens"],
                                  "items": copy.deepcopy(r["items_snapshot"])}
        log.info(f"{r['condition']}: {'accepted' if accepted else 'rejected'} (best round {self.state['best']['round']})")
        if r["score"]["solved"] == r["score"]["runs"] and self.enter_gate():
            return
        self.plan_next(r, records, improved)

    def plan_next(self, r: dict, records: list, improved: bool, count_stall: bool = True):
        """The next round's items from a scored phase-1 round: diagnose.update on the round's records (the best
        round's when the round was rejected), the writer's history, a route switch or a stop when a node blocks,
        the stall rule and the phase-1 budget. improved: whether the round beat the previous best; count_stall:
        False when the round was planned before (reopen), so it is not counted twice."""
        accepted = r["accepted"]
        # the next round's items, from the accepted round's records (or the best round's when rejected). A
        # failed gate is the exception: its runs are the best insight's own runs, more of them than the round
        # had, so they are the evidence even though the gate is marked not accepted
        base_items = copy.deepcopy(self.state["best"]["items"])
        base_records = records if (accepted or r["phase"] == "gate") else self.latest_records()
        # the jump rule's windows: this round's records and the scored rounds before it, newest first
        recent = [records] + [self.round_records(x) for x in self.scored_before(r)[::-1][:max(C.JUMP_ROUNDS - 1, 0)]]
        upd = D.update(self.graph, self.profile, self.route(), base_items, base_records, self.mode,
                       passed=self.passed_nodes(), recent=recent)
        items = upd["items"]
        self.state["passed_nodes"] = upd["passed_nodes"]
        # stall: rounds that did not improve on the best while there is nothing left to change, or every
        # node item is at the top level
        top_now = all(it["level"] >= max(C.LEVELS) for it in r["items_snapshot"].values() if it["kind"] == "node")
        if improved:
            self.state["stall"] = 0
        elif count_stall and (top_now or not upd["changes"]):
            self.state["stall"] = self.state.get("stall", 0) + 1
        if not accepted:      # the rejected round's texts become "worse" versions the writer sees
            for iid, old in r["items_snapshot"].items():
                if iid not in items:
                    continue
                hist = items[iid].setdefault("history", [])
                # the rejected round's item carries the worse versions of the rejected rounds before it, which
                # the best round's items never saw (an item the best round lacks is re-added from scratch every
                # plan: 2023/J Qwen r5-r7 added N4 at L2, L3, L4 and each plan knew only the latest)
                for h in old.get("history") or []:
                    if h.get("verdict") == "worse" and not any(x.get("round") == h.get("round") and x.get("verdict") == "worse"
                                                               for x in hist):
                        hist.append(copy.deepcopy(h))
                if old.get("text") and old["text"] != (self.state["best"]["items"].get(iid) or {}).get("text") \
                        and not any(h.get("round") == r["condition"] and h.get("verdict") == "worse" for h in hist):
                    hist.append({"round": r["condition"], "level": old["level"], "text": old["text"], "verdict": "worse",
                                 "uptake": (r["score"].get("stuck") or {})})
        for ch in upd["changes"]:
            it = items.get(ch["item"])
            if it is None:
                continue
            if ch["change"] in ("escalate", "restate", "add"):
                old = (self.state["best"]["items"].get(ch["item"]) or {})
                if ch["change"] in ("escalate", "add") and it["kind"] == "node":
                    # a level already tried and found worse is skipped (an added item carries the worse
                    # versions of a rejected round that added it before)
                    tried = [h["level"] for h in it.get("history") or [] if h.get("verdict") == "worse"]
                    if tried and it["level"] <= max(tried):
                        it["level"] = max(tried) + 1
                    if it["level"] > max(C.LEVELS):
                        if ch.get("rule") == "code_gap" and old.get("text"):
                            # the code-gap rule escalates a node the runs already hold; when its stronger
                            # version was tried and found worse, the node keeps the version that passed: the
                            # frontier is the work, and a side escalation must not block the loop (2023/J
                            # Nemotron r8: N2 passed at L4, L5 worse, the loop stopped on "N2 resists")
                            it.update({"level": old["level"], "text": old["text"], "tokens": old.get("tokens"),
                                       "reason": old.get("reason")})
                            ch["change"], ch["why"] = "kept", ch["why"] + "; its stronger version was worse, kept"
                            continue
                        it["level"] = max(C.LEVELS)
                        if ch.get("rule") != "jump":     # a jump item never blocks the loop: rewritten at the top instead
                            upd["blocked"].append(it["node"])
                    it["text"] = None
                if old.get("text") and not any(h.get("round") == self.state["best"]["condition"] and h.get("text") == old["text"]
                                               for h in it.get("history") or []):
                    it.setdefault("history", []).append(
                        {"round": self.state["best"]["condition"], "level": old["level"], "text": old["text"],
                         "verdict": "not taken up" if ch["change"] == "escalate" else "not recognized",
                         "uptake": upd["uptake"].get(it.get("node"))})
        r["plan"] = {"changes": upd["changes"], "blocked": upd["blocked"], "off_route": dict(upd["off_route"]),
                     "uptake": upd["uptake"], "frontier": upd.get("frontier"), "passed": upd.get("passed"),
                     "majority_frontier": upd.get("majority_frontier"), "past_frontier": upd.get("past_frontier"),
                     "jump": upd.get("jump")}
        log.info(f"{r['condition']}: passed {upd.get('passed')} route nodes, frontier {upd.get('frontier')}"
                 + (f" (majority frontier {upd['majority_frontier']})" if upd.get("majority_frontier") not in (None, upd.get("frontier")) else "")
                 + (f" (the failed runs stop past it at {upd['past_frontier']})" if upd.get("past_frontier") else "")
                 + (f"; jump {upd['jump']}" if upd.get("jump") else "")
                 + f"; changes {[(c['item'], c['change']) for c in upd['changes']]}; "
                 f"blocked {upd['blocked']}; off-route stuck {dict(upd['off_route'])}")
        n_fail = r["score"]["runs"] - r["score"]["solved"]
        want = D.wants_switch(upd, n_fail)
        blocked = sorted(set(self.state["blocked"]) | set(upd["blocked"]))
        if upd["blocked"] or want:
            self.state["blocked"] = blocked
            new_route = D.choose_route(self.graph, self.profile, blocked=blocked, must_contain=want) if want else None
            if new_route is None or new_route["index"] == self.route()["index"]:
                new_route = D.choose_route(self.graph, self.profile, blocked=blocked)
            if new_route and new_route["index"] != self.route()["index"]:
                new_route["statements"] = {nid: G.by_id(self.graph)[nid]["statement"] for nid in new_route["nodes"]}
                items = D.switch_route(self.graph, self.profile, items, new_route, self.mode)
                self.state["route"] = new_route
                self.state["passed_nodes"] = D.initial_passed(new_route, self.state["passed_nodes"])
                self.state["route_history"].append({"round": r["round"], "index": new_route["index"],
                                                    "why": f"blocked {upd['blocked']}, off-route {want}"})
                self._writer = None
                log.info(f"switching to route {new_route['index']} ({'+'.join(new_route['nodes'])})")
            elif upd["blocked"] and not want:
                self.state["items"] = items
                self.save()
                self.stop(f"nodes {upd['blocked']} resist at the top level and no other route avoids them")
                return
        self.state["items"] = items
        self.save()
        if not any(it.get("text") is None for it in items.values()):
            log.info(f"{r['condition']}: nothing to change; the next round repeats the insight")
            if r["phase"] == "gate":
                self.stop(f"the gate {r['condition']} did not confirm {self.state['best']['condition']} "
                          f"({r['score']['solved']}/{r['score']['runs']}) and the diagnosis has nothing to change")
                return
        if self.state.get("stall", 0) >= C.STALL_ROUNDS:
            self.stop(f"no better score for {C.STALL_ROUNDS} rounds with every node item at the top level")
            return
        if sum(1 for x in self.state["rounds"] if x["phase"] == 1) >= self.rounds1:
            log.info(f"phase 1 budget ({self.rounds1} rounds) used; best {self.state['best']['condition']} "
                     f"{self.state['best']['score']['solved']}/{self.state['best']['score']['runs']}")
            if self.state["best"]["score"]["solved"] >= self.phase2_min:
                if self.enter_gate():
                    return
                # the gate already measured this insight on gate_runs runs and it did not hold: nothing left to confirm
                self.stop(f"phase 1 budget used; the gate did not confirm {self.state['best']['condition']}")
            else:
                self.state["phase"] = "confirm" if self.confirm_enabled else "done"
                self.save()

    def reopen(self):
        """Continue a loop that stopped in phase 1 (a node resisting at the top level) under rules since changed:
        the stop is dropped and the next round is planned again from the last scored round's records, exactly as
        plan_next did when that round was scored, so the current rules decide (they may stop it again); the round
        is not counted again by the stall rule."""
        if not self.state.get("stopped"):
            log.info("reopen: the loop is not stopped")
            return
        r = self.state["rounds"][-1] if self.state["rounds"] else None
        if r is None or r["phase"] != 1 or r["status"] != "scored":
            raise Stop(f"reopen: the last round is not a scored phase-1 round ({r and r['condition']})")
        reason = self.state.pop("stop_reason", None)
        self.state["blocked"] = sorted(set(self.state.get("blocked") or []) - set((r.get("plan") or {}).get("blocked") or []))
        self.state["stopped"], self.state["phase"] = False, 1
        self.prepare()
        log.info(f"reopen: dropping the stop '{reason}'; planning again after {r['condition']} under the current rules")
        self.plan_next(r, GR.load_records(self.dir / r["grade"]), improved=False, count_stall=False)
        self.save()

    # --- the gate: the entry confirmation of a round that solved every run

    @staticmethod
    def insight_sha(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]

    def gate_of(self, round_no, insight: str | None = None) -> dict | None:
        """The gate run on that round, or on the same insight text under another round number: the loop may
        reach the same text again, and a text whose gate failed must not be paid for twice."""
        gates = reversed(self.state.get("gates") or [])
        sha = self.insight_sha(insight) if insight is not None else None
        return next((g for g in gates if g["of"] == round_no or (sha and g.get("sha") == sha)), None)

    def enter_gate(self) -> bool:
        """-> whether the loop moved on. A round that solved every run is rerun on gate_runs fresh seeds before
        anything is compacted, because three runs decide little: 2025/J Nemotron compacted an r2 that was 3/3 on
        three runs and 3/5 on five. False means this insight already failed its gate, and the caller goes on
        improving it instead."""
        best = self.state["best"]
        if not self.gate_enabled:
            self.enter_phase2()
            return True
        g = self.gate_of(best["round"], best.get("insight"))
        if g is not None:
            if g["ok"]:
                self.enter_phase2()
                return True
            return False
        self.state["items"] = copy.deepcopy(best["items"])
        self.state["phase"] = "gate"
        self.save()
        log.info(f"gate: confirming {best['condition']} ({best['score']['solved']}/{best['score']['runs']}, "
                 f"{best['insight_tokens']} tokens) on {self.gate_runs} fresh runs before compacting it")
        return True

    def gate_round(self):
        r = self.current_round()
        if r is None or r["phase"] != "gate":
            r = self.new_round("gate", "g")
            r["n_runs"], r["of"] = self.gate_runs, self.state["best"]["round"]
            self.state["items"] = copy.deepcopy(self.state["best"]["items"])
            self.save()
        records = self.run_round(r)
        n = r["score"]["runs"]
        want = max(1, n - C.GATE_TOLERANCE)
        ok = r["score"]["solved"] >= want
        r["accepted"] = ok
        self.state.setdefault("gates", []).append(
            {"round": r["round"], "condition": r["condition"], "ok": ok, "solved": r["score"]["solved"],
             "runs": n, "want": want, "of": r["of"], "sha": self.insight_sha(r.get("insight"))})
        self.save()
        log.info(f"{r['condition']}: gate {r['score']['solved']}/{n} (needs {want}) -> "
                 f"{'compacting' if ok else 'back to phase 1'}")
        if ok:
            self.state["confirmed_by"] = r["condition"]
            self.enter_phase2()
            return
        # a failed gate is not a phase-1 attempt, so it does not count against the stall rule; its grading is
        # richer than a round's, and the next round is planned from it
        self.state["phase"] = 1
        self.save()
        self.plan_next(r, records, improved=False, count_stall=False)

    # --- phase 2: compaction

    def finish_phase2(self, reason: str):
        """Phase 2 is over. A gate round and a compaction round are both confirmation-sized, so an insight that
        passed one is confirmed already; only one that never passed either gets a confirmation round."""
        if self.state.get("confirmed_by"):
            self.stop(f"confirmed on {self.state['confirmed_by']} ({reason})")
            return
        self.state["phase"] = "confirm" if self.confirm_enabled else "done"
        self.save()

    def enter_phase2(self):
        best = self.state["best"]
        if best["score"]["solved"] < self.phase2_min or self.rounds2 <= 0:
            self.finish_phase2("no compaction")
            return
        self.state["items"] = copy.deepcopy(best["items"])
        self.state["ablation"] = {"queue": D.ablation_groups(self.graph, best["items"], self.profile, self.mode),
                                  "accepted": [], "entry_round": best["round"]}
        self.state["phase"] = 2
        self.save()
        log.info(f"phase 2: {len(self.state['ablation']['queue'])} candidate groups; best {best['condition']} "
                 f"{best['insight_tokens']} tokens")

    def apply_group(self, items: dict, group: dict, r: dict) -> dict:
        items = copy.deepcopy(items)
        for iid in group["members"]:
            if iid not in items:
                continue
            if group["op"] == "drop":
                del items[iid]
            elif group["op"] == "level1":
                it = items[iid]
                old = next((h for h in reversed(it.get("history") or []) if h.get("level") == 1 and h.get("text")), None)
                it.setdefault("history", []).append({"round": r["condition"], "level": it["level"], "text": it["text"],
                                                     "verdict": "compacted"})
                it["level"] = 1
                it["text"] = old["text"] if old else None
                it["tokens"] = self.count(it["text"]) if it["text"] else None
            elif group["op"] == "shorten":
                it = items[iid]
                tokens = it.get("tokens") or (self.count(it["text"]) if it.get("text") else 0)
                limit = max(C.SHORTEN_MIN, int(C.SHORTEN_SHARE * tokens))
                if not it.get("text") or limit >= tokens:
                    continue                                    # at the floor already: nothing to gain
                it.setdefault("history", []).append({"round": r["condition"], "level": it["level"], "text": it["text"],
                                                     "verdict": "shortened"})
                it["shorten"] = {"from": it["text"], "limit": limit}
                it["text"], it["tokens"] = None, None
        return items

    @staticmethod
    def differs(a: dict, b: dict) -> bool:
        """Whether two item sets differ in membership, text or level (a group that changes nothing is skipped)."""
        return set(a) != set(b) or any((a[k].get("text"), a[k].get("level")) != (b[k].get("text"), b[k].get("level")) for k in a)

    def phase2_round(self):
        ab = self.state["ablation"]
        r = self.current_round()
        if r is None:
            while True:
                if not ab["queue"]:
                    self.finish_phase2("every compaction tried")
                    return
                if sum(1 for x in self.state["rounds"] if x["phase"] == 2) >= self.rounds2:
                    self.finish_phase2(f"phase 2 budget ({self.rounds2} rounds) used")
                    return
                group = ab["queue"].pop(0)
                r = self.new_round(2, "c")
                r["group"], r["n_runs"] = group, self.phase2_runs
                items = self.apply_group(self.state["best"]["items"], group, r)
                if self.differs(items, self.state["best"]["items"]):
                    break
                log.info(f"{r['condition']}: {group['op']} {group['name']} changes nothing; skipped")
                self.state["rounds"].pop()
            self.state["items"] = items
            self.save()
            log.info(f"{r['condition']}: trying {group['op']} {group['name']} ({group['members']})")
        records = self.run_round(r)
        best = self.state["best"]
        # a compaction round runs phase2_runs times, so its own rate is the confirmation of the shorter insight
        ok = r["score"]["solved"] >= max(1, r["score"]["runs"] - C.PHASE2_TOLERANCE) and (
            not C.PHASE2_REQUIRE_END or r["score"]["ends"] >= best["score"]["ends"])
        r["accepted"] = ok
        if ok:
            self.state["confirmed_by"] = r["condition"]
            ab["accepted"].append({"round": r["round"], "group": r["group"], "previous_best": best})
            self.state["best"] = {"round": r["round"], "condition": r["condition"], "primary": r["score"]["primary"],
                                  "score": r["score"], "insight": r["insight"], "insight_tokens": r["insight_tokens"],
                                  "items": copy.deepcopy(r["items_snapshot"])}
            log.info(f"{r['condition']}: accepted; insight now {r['insight_tokens']} tokens")
            if r["group"]["op"] == "shorten":           # keep shortening while it is accepted; the floor ends it
                k = r["group"].get("pass", 1) + 1
                ab["queue"].insert(0, dict(r["group"], name=f"shorter wording, pass {k}", **{"pass": k}))
        else:
            log.info(f"{r['condition']}: rejected ({r['score']['solved']}/{r['score']['runs']}, ends {r['score']['ends']})")
            if C.PHASE2_STOP_ON_FAIL:
                self.state["items"] = copy.deepcopy(self.state["best"]["items"])
                self.save()
                self.finish_phase2(f"{r['condition']} is the first compaction the insight does not survive")
                return
            members = r["group"]["members"]
            if len(members) > 1:
                half = len(members) // 2
                ab["queue"][0:0] = [dict(r["group"], members=members[:half], name=r["group"]["name"] + " (1/2)"),
                                    dict(r["group"], members=members[half:], name=r["group"]["name"] + " (2/2)")]
        self.state["items"] = copy.deepcopy(self.state["best"]["items"])
        self.save()

    # --- confirmation

    def confirm_round(self):
        r = self.current_round()
        if r is None:
            best_round = self.state["best"]["round"]
            confs = self.state["confirmations"]
            # a confirmation is of the best round it ran on ("of"); the current best may have one already (an
            # undone compaction returns to a confirmed insight; a reopened phase 2 that accepts nothing keeps it)
            last = next((c for c in reversed(confs) if c.get("of", best_round) == best_round), None)
            if last is not None:
                self.stop("confirmed" if last["ok"] else "confirmation round done (nothing to undo)")
                return
            if sum(1 for c in confs if not c["ok"]) > C.CONFIRM_RETRIES:
                self.stop("confirmation retries used up")
                return
            r = self.new_round("confirm", "f")
            r["n_runs"], r["of"] = self.confirm_runs, best_round
            self.state["items"] = copy.deepcopy(self.state["best"]["items"])
            self.save()
        self.run_round(r)
        # after an accepted compaction the final insight must solve (nearly) every run again; otherwise the
        # confirmation only asks whether the best round's rate is reproduced, within the tolerance
        n, b = r["score"]["runs"], self.state["best"]["score"]
        want = n if (self.state.get("ablation") or {}).get("accepted") else round(b["solved"] / b["runs"] * n)
        ok = r["score"]["solved"] >= want - C.CONFIRM_TOLERANCE
        r["accepted"] = ok
        self.state["confirmations"].append({"round": r["round"], "condition": r["condition"], "ok": ok,
                                            "solved": r["score"]["solved"], "runs": n, "want": want,
                                            "of": r.get("of", self.state["best"]["round"])})
        if ok or not (self.state.get("ablation") or {}).get("accepted"):
            self.stop("confirmed" if ok else "confirmation round done: the best insight did not reach its score again")
            return
        undone = self.state["ablation"]["accepted"].pop()
        self.state["best"] = undone["previous_best"]
        self.state["items"] = copy.deepcopy(self.state["best"]["items"])
        self.save()
        log.info(f"{r['condition']}: {r['score']['solved']}/{r['score']['runs']}; undoing the compaction of round "
                 f"{undone['round']} ({undone['group']['name']}) and confirming again")

    # --- the control arm

    def control(self, kind: str):
        self.prepare()
        if self.state.get("stopped") and not self.state.get("best"):
            return
        if kind != "keynode":
            raise ValueError(f"unknown control {kind}")
        key = self.route()["key"]
        text = ascii(G.by_id(self.graph)[key]["statement"]).strip() + "\n"
        cond = "ctl_keynode"
        d = self.route_dir(cond)
        (d / "insight.txt").write_text(text, encoding="utf-8")
        ctl = self.state["controls"].get(kind) or {"condition": cond, "insight": text, "insight_tokens": self.count(text),
                                                  "status": "written"}
        self.state["controls"][kind] = ctl
        self.save()
        r = dict(ctl, phase="control", round=0, n_runs=self.confirm_runs)
        if ctl["status"] in ("written", "launched"):
            self.evaluate(r)
            ctl.update(jobs=r.get("jobs"), runs=r["runs"], status="evaluated")
            self.save()
        if ctl["status"] == "evaluated":
            records = self.grade(r)
            ctl.update(grade=r["grade"], score=self.score(r, records), status="scored")
            self.save()
        log.info(f"control {kind}: {ctl['score']['solved']}/{self.runs_per_round} solved, {ctl['insight_tokens']} tokens")

    # --- the driver

    def drive(self, write_only: bool = False):
        try:
            self.prepare()
            if self.state.get("stopped"):
                return self.state
            if write_only:
                r = self.current_round() or self.new_round(1, "r")
                if r["status"] == "planned":
                    self.write_items(r)
                print(r["insight"])
                return self.state
            while not self.state.get("stopped"):
                phase = self.state["phase"]
                if phase == 1:
                    self.phase1_round()
                elif phase == "gate":
                    self.gate_round()
                elif phase == 2:
                    self.phase2_round()
                elif phase == "confirm":
                    self.confirm_round()
                else:
                    break
        except Stop as e:
            log.info(f"stop: {e}")
            if self.state.get("stopped") is False and "dry run" in str(e):
                pass
            elif not self.state.get("stopped"):
                self.stop(str(e))
        except A.ApiError as e:
            log.error(f"API: {e}")
            self.save()
            raise
        return self.state

    def status_text(self) -> str:
        s = self.state
        lines = [f"{s['problem']} / {s['model']} ({s.get('mode', '?')} mode): phase {s['phase']}, {len(s['rounds'])} rounds"
                 + (f", stopped: {s['stop_reason']}" if s.get("stopped") else "")]
        if s.get("baseline"):
            lines.append(f"baseline: {s['baseline']['solved']}/{s['baseline']['runs']} ({s['baseline']['source']})")
        if s.get("route"):
            lines.append(f"route {s['route']['index']}: {'+'.join(s['route']['nodes'])} (missing {s['route']['missing']})")
        for r in s["rounds"]:
            sc = r.get("score") or {}
            snap = r.get("items_snapshot") or {}
            desc = " ".join(f"{it.get('node') or it.get('hazard') or it['id']}:L{it['level']}" for it in snap.values())
            lines.append(f"  {r['condition']} [{r['status']}] {sc.get('solved', '?')}/{sc.get('runs', '?')} solved, "
                         f"END {sc.get('ends', '?')}, passed {sc.get('passed', '?')}, reached {sc.get('reached', '?')}, "
                         f"insight {r.get('insight_tokens', '?')} tok, output {sc.get('output_tokens', '?')} tok"
                         + (" accepted" if r.get("accepted") else (" rejected" if r.get("accepted") is False else ""))
                         + (f" group={r['group']['name']}" if r.get("group") else "")
                         + (f"  [{desc}]" if desc else ""))
        for g in s.get("gates") or []:
            lines.append(f"gate {g['condition']} of round {g['of']}: {g['solved']}/{g['runs']} "
                         f"(needed {g['want']}) -> {'compaction' if g['ok'] else 'back to phase 1'}")
        if s.get("best"):
            b = s["best"]
            lines.append(f"best: {b['condition']} {b['score']['solved']}/{b['score']['runs']} solved, {b['insight_tokens']} tokens"
                         + (f", confirmed on {s['confirmed_by']}" if s.get("confirmed_by") else ""))
        for k, c in (s.get("controls") or {}).items():
            sc = c.get("score") or {}
            lines.append(f"control {k}: {sc.get('solved', '?')}/{sc.get('runs', '?')}, {c.get('insight_tokens')} tokens")
        return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GPTv4: a model-specific insight for one problem, end to end.")
    ap.add_argument("--problem", required=True)
    ap.add_argument("--model", required=True, choices=sorted(C.SOLVERS))
    ap.add_argument("--mode", choices=("step", "cut"), default=None,
                    help=f"step: one route node per round; cut: every missing node in round 1 (default {C.MODE}; "
                         "a resumed loop keeps its own)")
    ap.add_argument("--rounds1", type=int, default=C.ROUNDS1)
    ap.add_argument("--rounds2", type=int, default=C.ROUNDS2)
    ap.add_argument("--runs", type=int, default=C.RUNS_PER_ROUND, help="agent runs per round")
    ap.add_argument("--confirm-runs", type=int, default=C.CONFIRM_RUNS, help="runs of the confirmation round and of a control arm")
    ap.add_argument("--gate-runs", type=int, default=C.GATE_RUNS, help="runs of the gate: the entry confirmation before compaction")
    ap.add_argument("--phase2-runs", type=int, default=C.PHASE2_RUNS, help="runs of a compaction round")
    ap.add_argument("--no-gate", action="store_true", help="compact a round that solved every run without confirming it first")
    ap.add_argument("--phase2-min", type=int, default=None, help="solved runs the best round needs for phase 2 (default: all)")
    ap.add_argument("--no-confirm", action="store_true")
    ap.add_argument("--write-only", action="store_true", help="write the next round's insight and stop (no GPU)")
    ap.add_argument("--dry-run", action="store_true", help="write the insight and test the sbatch commands only")
    ap.add_argument("--control", choices=("keynode",), help="run a control arm instead of the loop")
    ap.add_argument("--reopen", action="store_true",
                    help="continue a stopped loop: drop the stop and plan the next round again from the last round's "
                         "records under the current rules")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--runs-root", type=Path, default=None, help=f"where runs/<slug>/<model> lives (default {C.RUNS})")
    args = ap.parse_args(argv)
    from adapters.solver_agentv3 import Solver
    loop = Loop(args.problem, args.model, runs_root=args.runs_root, solver=Solver(args.dry_run), rounds1=args.rounds1,
                rounds2=args.rounds2, runs_per_round=args.runs, phase2_min=args.phase2_min, confirm=not args.no_confirm,
                dry=args.dry_run, mode=args.mode, confirm_runs=args.confirm_runs,
                gate_runs=args.gate_runs, phase2_runs=args.phase2_runs, gate=not args.no_gate)
    if args.status:
        print(loop.status_text())
        return 0
    if args.control:
        loop.control(args.control)
    else:
        if args.reopen:
            loop.reopen()
        loop.drive(write_only=args.write_only)
    print(loop.status_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
