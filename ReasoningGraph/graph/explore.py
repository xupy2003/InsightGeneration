"""A problem's reasoning graph built by free exploration. The explorer (gpt-6-astra) sees the statement
only. It works out one approach after another, implements each one in C++, and a path (the chain of
claims the approach rests on, as nodes, with its END route) is added only when the judge accepts the
program on every test. The exploration ends when the explorer says that no genuinely different
approach is left, or when MAX_PATHS paths are in. The editorial and the reference solution are never
shown to the explorer: afterwards a reviewer uses them to check the claims (wording-only revisions go
back to the explorer's session). Whether the graph fits real solvers is measured by grading their
reasoning traces (grade/) and validating (validate/); validate's feedback comes back through --revise-from.

    python3 explore.py --problems 2025/J-stacking-cups
    python3 explore.py --problems P --force [--max-paths 12] [--no-review] [--editorial missing|always|never]
    python3 explore.py --editorial-only --problems P      # add the editorial's path to an existing graph
    python3 explore.py --render-only --problems P
    python3 explore.py --list

Writes graph/graphs/<slug>/{graph.json, graph.md, graph.dot, graph.png, review.json, sessions.jsonl,
judged.jsonl, paths/P<k>.cpp, judged/sub<n>.cpp} and history/graph_<version>.json. graph.json is
rewritten after every accepted path (status "exploring"), so a long exploration can be watched.
Login node only: the API, and the judge compiles and runs programs.
"""
import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

VER2 = Path(__file__).resolve().parents[1]
if str(VER2) not in sys.path:
    sys.path.insert(0, str(VER2))
import config as C  # noqa: E402
import api as A  # noqa: E402
from problems import ProblemContext, normalize, slug_of, graph_dir, read_problem_list  # noqa: E402
from graph import rules as R  # noqa: E402
from graph import prompts as PR  # noqa: E402
from graph import render  # noqa: E402
from graph import build as B  # noqa: E402
from graph import judge as JD  # noqa: E402

SCHEMA = "reasoning-graph-v2"
END_STATEMENT = ("A solver holding every node of one END route can write a correct, fast enough program by "
                 "routine coding; each route is an approach whose program the judge accepted.")

# ----------------------------------------------------------------------------- tools

_NODE_PROPS = {k: v for k, v in B._NODE_PROPS.items() if k != "source"}
_NODE = {"type": "object", "additionalProperties": False, "required": list(_NODE_PROPS), "properties": _NODE_PROPS}
SUBMIT_PATH = A.fn(
    "submit_path", "One approach you worked out and implemented: its new claims as nodes, its END route, new "
                   "hazards, and the program the judge will run.",
    approach={"type": "string", "description": "2 to 4 sentences: the approach, why it is correct, and why you expect "
                                                "it to fit the limits (or that you leave that to the judge)"},
    nodes={"type": "array", "items": _NODE, "description": "new nodes only, ids continuing the numbering"},
    end_route={"type": "array", "items": {"type": "string"},
               "description": "the nodes (existing and new) this approach rests on, the key node included"},
    key_node={"type": "string", "description": "the node of end_route that states this path's output rule: the "
                                               "construction or algorithm (kind construction or algorithm) that "
                                               "determines what the program outputs for every input; never a "
                                               "complexity claim or a proof step; every other node of end_route "
                                               "must be its prerequisite, directly or through routes"},
    hazards={"type": "array", "items": B._HAZARD, "description": "new hazards only, ids continuing the numbering"},
    program={"type": "string", "description": "one complete C++17 program"},
    notes={"type": "string"})
FINISH = A.fn(
    "finish_exploration", "No genuinely different approach that you believe correct is left (speed is the judge's "
                          "call: an approach dropped only for being slow must have been submitted first).",
    reason={"type": "string"},
    considered={"type": "array", "items": {"type": "string"},
                "description": "ideas you considered and dropped, each with why; one dropped for speed names the "
                               "judge's verdict on it"})
_EDITORIAL_PROPS = {k: v for k, v in SUBMIT_PATH["parameters"]["properties"].items() if k != "program"}
SUBMIT_EDITORIAL = A.fn(
    "submit_path", "The editorial's approach as a path: the claims the graph lacks as new nodes, its END route, "
                   "new hazards. No program: the reference solution is this path's program.", **_EDITORIAL_PROPS)
EDITORIAL_COVERED = A.fn(
    "editorial_covered", "The editorial's approach is already one of the graph's END routes.",
    route={"type": "array", "items": {"type": "string"}, "description": "that END route's nodes"},
    note={"type": "string"})
_TEXT_NODE_PROPS = {k: v for k, v in _NODE_PROPS.items() if k != "routes"}
REVISE_NODES = A.fn(
    "revise_nodes", "Every node and every hazard of the graph with revised texts; ids and routes stay.",
    nodes={"type": "array", "items": {"type": "object", "additionalProperties": False,
                                      "required": list(_TEXT_NODE_PROPS), "properties": _TEXT_NODE_PROPS}},
    hazards={"type": "array", "items": B._HAZARD},
    notes={"type": "string"})
_REVIEW_PROPS = {
    "nodes": {"type": "array", "items": B._REVIEW_NODE},
    "end_ok": {"type": "boolean"}, "end_note": {"type": "string"},
    "key_ok": {"type": "boolean"}, "key_note": {"type": "string"},
    "hazards_ok": {"type": "boolean"}, "hazards_note": {"type": "string"},
    "missing": {"type": "array", "items": {"type": "string"}},
    "editorial_found": {"type": "boolean"}, "editorial_note": {"type": "string"},
    "order": {"type": "string"}, "verdict": {"type": "string", "enum": ["accept", "revise"]}}
SUBMIT_REVIEW = A.fn("submit_review", "Your review of the explored graph.", **_REVIEW_PROPS)


# ----------------------------------------------------------------------------- the explorer's session

class Explorer:
    """One session (responses chained) that explores, and later revises texts. step() makes one call
    with the given tools and returns the function call, or None when the model made none."""

    def __init__(self, cl, log, record, effort: str, role: str = "explorer"):
        self.cl, self.log, self.record, self.effort, self.role = cl, log, record, effort, role
        self.prev, self.calls, self.usage = None, 0, Counter()

    def step(self, input_items: list, tools: list, tool_choice, instructions: str = PR.EXPLORE_INSTRUCTIONS):
        kw = dict(model=C.API_MODEL, instructions=instructions, input=input_items, tools=tools,
                  tool_choice=tool_choice, reasoning={"effort": self.effort})
        if self.prev:
            kw["previous_response_id"] = self.prev
        resp = A.respond(self.cl, self.log, self.record, self.role, **kw)
        self.usage += A.usage_of(resp)
        self.prev = resp.id
        self.calls += 1
        return A.function_call(resp)


def _args(call):
    try:
        return json.loads(call.arguments), None
    except json.JSONDecodeError:
        return None, "the arguments are not valid JSON"


def _graph_summary(state: dict) -> str:
    lines = [f"Graph now: {len(state['nodes'])} nodes, {len(state['paths'])} path(s), {len(state['hazards'])} hazard(s)."]
    for n in state["nodes"]:
        lines.append(f"  {n['id']} [{n['kind']}; routes {R.route_text(n['routes'])}] {n['name']}: {n['statement']}")
    for p in state["paths"]:
        lines.append(f"  {p['id']}: key node {p.get('key_node')}; END route {' + '.join(p['end_route'])}")
    for h in state["hazards"]:
        lines.append(f"  {h['id']}: {h['statement']}")
    lines.append(f"New node ids continue at N{len(state['nodes']) + 1}, hazard ids at H{len(state['hazards']) + 1}.")
    return "\n".join(lines)


def merged_graph(state: dict, new_nodes: list, end_route, new_hazards: list, key_node=None) -> dict:
    return R.derive({"solution_outline": "exploration", "nodes": state["nodes"] + new_nodes,
                     "end": {"statement": END_STATEMENT, "routes": state["end_routes"] + [end_route],
                             "keys": state.get("end_keys", []) + [key_node]},
                     "hazards": state["hazards"] + new_hazards})


def try_path(state: dict, args: dict, ctx: ProblemContext, out_dir: Path, submission: int,
             judge=JD.judge_program):
    """("rules", problems) | ("judge", result) | ("accepted", path). An accepted path updates state."""
    k = len(state["paths"]) + 1
    new_nodes = [dict(n, source="exploration", path=f"P{k}") for n in args.get("nodes") or []
                 if isinstance(n, dict)]
    new_ids = [n.get("id") for n in new_nodes]
    new_hazards = [dict(h) for h in args.get("hazards") or [] if isinstance(h, dict)]
    end_route, key = args.get("end_route"), args.get("key_node")
    merged = merged_graph(state, new_nodes, end_route if isinstance(end_route, list) else [], new_hazards, key)
    problems = R.check_graph(merged, ctx.statement)
    problems += R.check_path(merged, new_ids, end_route, key, state.get("end_keys", []))
    program = args.get("program") or ""
    if not program.strip():
        problems.append("program is empty")
    if problems:
        return "rules", problems
    (out_dir / "judged").mkdir(parents=True, exist_ok=True)
    (out_dir / "judged" / f"sub{submission:03d}.cpp").write_text(program, encoding="utf-8")
    result = judge(ctx.problem, program, workdir=out_dir / "judge")
    with (out_dir / "judged.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"submission": submission, "path": f"P{k}", "approach": args.get("approach"),
                            **{x: result.get(x) for x in ("verdict", "tests_run", "n_tests", "failing_test",
                                                          "max_time_s")},
                            "time": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n")
    if not result["accepted"]:
        return "judge", result
    (out_dir / "paths").mkdir(parents=True, exist_ok=True)
    (out_dir / "paths" / f"P{k}.cpp").write_text(program, encoding="utf-8")
    path = {"id": f"P{k}", "approach": args.get("approach", ""), "end_route": list(end_route), "key_node": key,
            "new_nodes": new_ids, "new_hazards": [h.get("id") for h in new_hazards],
            "program": f"paths/P{k}.cpp", "submission": submission,
            "judge": {x: result.get(x) for x in ("verdict", "tests_run", "n_tests", "max_time_s", "time_limit_s")},
            "notes": args.get("notes", "")}
    state["nodes"] = merged["nodes"]
    state["end_routes"].append(list(end_route))
    state.setdefault("end_keys", []).append(key)
    state["hazards"] = merged["hazards"]
    state["paths"].append(path)
    return "accepted", path


def outline_of(paths: list[dict]) -> str:
    parts = []
    for p in paths:
        first = re.split(r"(?<=[.!?])\s", (p.get("approach") or "").strip(), maxsplit=1)[0]
        parts.append(f"{p['id']}: {first}")
    return " ".join(parts) or "no accepted path"


def assemble(problem: str, ctx: ProblemContext, state: dict, status: str, provenance: dict) -> dict:
    return {"schema": SCHEMA, "mode": "exploration", "problem": problem, "title": ctx.title, "status": status,
            "version": R.version_of({"solution_outline": outline_of(state["paths"]), "nodes": state["nodes"],
                                     "end": {"statement": END_STATEMENT, "routes": state["end_routes"],
                                             "keys": state.get("end_keys", [])},
                                     "hazards": state["hazards"]}),
            "solution_outline": outline_of(state["paths"]), "nodes": state["nodes"],
            "end": {"statement": END_STATEMENT, "routes": state["end_routes"], "keys": state.get("end_keys", [])},
            "hazards": state["hazards"],
            "paths": state["paths"], "rejected": state["rejected"],
            "exploration": {"finished": state["finished"], "reason": state["reason"],
                            "considered": state["considered"], "submissions": state["submissions"]},
            "builder_notes": state.get("notes", ""), "open_issues": [], "advisories": [],
            "provenance": provenance}


def explore(cl, log, record, ctx: ProblemContext, out_dir: Path, args, judge=JD.judge_program) -> tuple[dict, Explorer]:
    """The exploration loop. Returns the state and the explorer (its session continues into the review)."""
    state = {"nodes": [], "end_routes": [], "end_keys": [], "hazards": [], "paths": [], "rejected": [],
             "considered": [], "finished": False, "reason": "", "submissions": 0, "notes": ""}
    ex = Explorer(cl, log, record, args.effort)
    tools = [SUBMIT_PATH, FINISH]
    items = [{"role": "user", "content": f"<problem>\n{ctx.statement.strip()}\n</problem>\n\nWork out your first "
                                         f"approach, implement it, and call submit_path. Node ids start at N1, "
                                         f"hazard ids at H1."}]
    failures, rule_failures, no_call, last_approach, last_verdict = 0, 0, 0, None, None

    def write_progress():
        doc = assemble(ctx.problem, ctx, state, "exploring",
                       {"model": C.API_MODEL, "explore_effort": args.effort, "usage": {"explorer": dict(ex.usage)},
                        "inputs": ctx.hashes(), "updated": time.strftime("%Y-%m-%d %H:%M:%S")})
        B.write_json_atomic(out_dir / "graph.json", doc)
        render.write_all(out_dir, doc, [])

    while True:
        call = ex.step(items, tools, "required")
        if call is None:
            no_call += 1
            if no_call > 3:
                state["reason"] = "the explorer stopped calling tools"
                break
            items = [{"role": "user", "content": "Call submit_path with a worked-out approach, or finish_exploration."}]
            continue
        a, err = _args(call)
        if err:
            items = [{"type": "function_call_output", "call_id": call.call_id, "output": f"Not accepted: {err}."}]
            continue
        if call.name == "finish_exploration":
            state.update(finished=True, reason=a.get("reason", ""), considered=a.get("considered") or [])
            record({"role": "explorer", "event": "finished", "reason": state["reason"], "considered": state["considered"]})
            log.info(f"exploration finished after {state['submissions']} submissions: {state['reason'][:200]}")
            ex.last_call = call
            break
        state["submissions"] += 1
        n = state["submissions"]
        last_approach = a.get("approach", "")
        kind, payload = try_path(state, a, ctx, out_dir, n, judge)
        record({"role": "explorer", "event": "submission", "submission": n, "kind": kind,
                "detail": payload if kind != "accepted" else payload["id"]})
        if kind == "rules":
            rule_failures += 1
            log.info(f"submission {n} not accepted by the rules: " + "; ".join(payload)[:300])
            output = ("Not accepted by the format checks (the program was not judged): " + "; ".join(payload)
                      + ". Fix these and call submit_path again with the whole path.")
            if rule_failures > C.MAX_FIXES:
                output += (f" This is the {rule_failures}th format failure in a row: simplify the path "
                           f"(fewer, clearer nodes) or move on to another approach.")
        elif kind == "judge":
            failures += 1
            last_verdict = payload["verdict"]
            log.info(f"submission {n}: {payload['verdict']} after {payload['tests_run']} tests")
            output = JD.judge_text(payload)
            if failures >= C.MAX_PATH_ATTEMPTS:
                state["rejected"].append({"approach": last_approach, "last_verdict": last_verdict,
                                          "attempts": failures, "submission": n})
                output += (f"\nThis approach has failed {failures} times. Abandon it: work out a genuinely "
                           f"different approach and call submit_path, or call finish_exploration.")
                failures = 0
            else:
                output += ("\nFix the approach or the program and call submit_path again with the whole path, "
                           "or abandon this approach.")
        else:
            failures, rule_failures = 0, 0
            log.info(f"path {payload['id']} accepted: {len(payload['new_nodes'])} new nodes, END route "
                     f"{' + '.join(payload['end_route'])}; {payload['judge']['tests_run']} tests")
            write_progress()
            output = (f"Accepted: {payload['id']} added, program {payload['judge']['verdict']} on "
                      f"{payload['judge']['tests_run']} tests.\n{_graph_summary(state)}\nIs there another genuinely "
                      f"different approach, resting on at least one claim the graph does not have? If so, work it "
                      f"out, implement it and call submit_path; otherwise call finish_exploration.")
            if len(state["paths"]) >= args.max_paths:
                output += f"\nThe graph has reached its limit of {args.max_paths} paths: call finish_exploration."
                tools = [FINISH]
        if state["submissions"] >= C.MAX_SUBMISSIONS and FINISH in tools and len(tools) > 1:
            output += f"\nThe limit of {C.MAX_SUBMISSIONS} submissions is reached: call finish_exploration."
            tools = [FINISH]
        items = [{"type": "function_call_output", "call_id": call.call_id, "output": output}]
    if not state["finished"]:
        state["reason"] = state["reason"] or "stopped by the limits"
    return state, ex


# ----------------------------------------------------------------------------- review and wording revision

def check_review(rev: dict, doc: dict) -> list[str]:
    want = R.node_ids(doc)
    got = [r.get("id") for r in rev.get("nodes") or []]
    return [] if sorted(got) == sorted(want) else [f"give exactly one entry per node {want}; you gave {got}"]


def classify(rev: dict) -> tuple[list[str], list[str]]:
    blocking, advisory = [], []
    for r in rev.get("nodes") or []:
        bad = [f for f in B.BLOCKING if not r.get(f, True)]
        soft = [f for f in B.ADVISORY if not r.get(f, True)]
        words = [B.BLOCKING[f] for f in bad] + [B.ADVISORY[f] for f in soft]
        if bad:
            blocking.append(f"{r['id']} ({'; '.join(words)}): {r.get('note', '')}")
        elif soft:
            advisory.append(f"{r['id']} ({'; '.join(words)}): {r.get('note', '')}")
    if not rev.get("hazards_ok", True):
        blocking.append(f"hazards: {rev.get('hazards_note', '')}")
    if not rev.get("end_ok", True):
        advisory.append(f"END: {rev.get('end_note', '')}")
    if not rev.get("key_ok", True):
        # Advisory, not blocking: a wording revision cannot move a key node, so a blocking item here would only
        # burn review rounds; the structural rules (rules.check_path) already reject a key that is not an
        # output rule, and the note is kept in review.json for the next build.
        advisory.append(f"key node: {rev.get('key_note', '')}")
    advisory += [f"missing (a claim the paths rest on that no node states): {m}" for m in rev.get("missing") or []
                 if m.strip()]
    if not rev.get("editorial_found", True):
        advisory.append(f"the editorial's approach is not among the paths: {rev.get('editorial_note', '')}")
    if (rev.get("order") or "").strip():
        advisory.append(f"order: {rev['order'].strip()}")
    return blocking, advisory


def review(cl, log, record, ctx: ProblemContext, doc: dict, effort: str) -> tuple[dict, Counter]:
    paths = "\n".join(f"{p['id']} (key node {p.get('key_node')}; END route {' + '.join(p['end_route'])}): {p['approach']}"
                      for p in doc["paths"])
    message = ctx.message() + f"\n\n<graph>\n{R.graph_text(doc)}\n</graph>\n\n<paths>\n{paths}\n</paths>"
    if (doc.get("builder_notes") or "").strip():
        message += f"\n\n<explorer_notes>\n{doc['builder_notes'].strip()}\n</explorer_notes>"
    return B._forced(cl, log, record, "reviewer", PR.REVIEW_EXPLORE_INSTRUCTIONS, SUBMIT_REVIEW, message, effort,
                     lambda ans: check_review(ans, doc), "the reviewer")


def apply_texts(doc: dict, args: dict, ctx: ProblemContext) -> tuple[dict | None, list[str]]:
    """The graph with the revised texts, or the problems with the revision."""
    by_id = {n.get("id"): n for n in args.get("nodes") or [] if isinstance(n, dict)}
    want = R.node_ids(doc)
    if sorted(by_id) != sorted(want) or len(by_id) != len(args.get("nodes") or []):
        return None, [f"give every node exactly once, with ids {want}"]
    want_h = [h["id"] for h in doc["hazards"]]
    hz = {h.get("id"): h for h in args.get("hazards") or [] if isinstance(h, dict)}
    if sorted(hz) != sorted(want_h):
        return None, [f"give every hazard exactly once, with ids {want_h}"]
    nodes = [{**n, **{k: by_id[n["id"]][k] for k in ("name", "kind", "statement", "accept", "anchors")}}
             for n in doc["nodes"]]
    hazards = [{**h, "statement": hz[h["id"]]["statement"], "check": hz[h["id"]]["check"]} for h in doc["hazards"]]
    new = {**doc, "nodes": nodes, "hazards": hazards, "builder_notes": args.get("notes", "")}
    problems = R.check_graph(new, ctx.statement)
    return (None, problems) if problems else (new, [])


def revise_texts(ex: Explorer, doc: dict, ctx: ProblemContext, blocking: list[str], advisory: list[str],
                 log, lead: str | None = None) -> dict:
    """A wording-only revision of the graph in session ex (the explorer's, the integrator's, or a fresh
    one): the findings and the current graph are in the request, so any session can do it."""
    findings = ["Blocking:"] + [f"- {b}" for b in blocking]
    if advisory:
        findings += ["", "Also consider (not blocking):"] + [f"- {a}" for a in advisory]
    text = ((lead or PR.REVISE_NODES_INSTRUCTIONS) + f"\n\n<graph>\n{R.graph_text(doc)}\n</graph>\n\n"
            + "\n".join(findings))
    last = getattr(ex, "last_call", None)
    items = ([{"type": "function_call_output", "call_id": last.call_id, "output": text}] if last
             else [{"role": "user", "content": text}])
    for _ in range(C.MAX_FIXES + 1):
        call = ex.step(items, [REVISE_NODES], {"type": "function", "name": "revise_nodes"})
        if call is None:
            items = [{"role": "user", "content": "Call revise_nodes."}]
            continue
        ex.last_call = call
        a, err = _args(call)
        new, problems = (None, [err]) if err else apply_texts(doc, a, ctx)
        if new is not None:
            return new
        log.warning("revision not accepted: " + "; ".join(problems)[:300])
        items = [{"type": "function_call_output", "call_id": call.call_id,
                  "output": "Not accepted: " + "; ".join(problems) + ". Call revise_nodes again with all of it."}]
    raise RuntimeError(f"no revise_nodes call passed the rules after {C.MAX_FIXES + 1} tries")


# ----------------------------------------------------------------------------- the editorial's path

def integrate_editorial(cl, log, record, ctx: ProblemContext, doc: dict, out_dir: Path, args,
                        judge=JD.judge_program) -> tuple[dict, dict, Explorer]:
    """An integrator session (statement, editorial, reference solution, graph) adds the editorial's approach as
    a path unless an END route already is it. The path's new nodes carry source "editorial"; it is not judged
    (the reference solution is its program, judged for the record) and the node cap does not apply.
    Returns (doc, {covered, ...}, the session)."""
    state = {"nodes": list(doc["nodes"]), "end_routes": [list(r) for r in doc["end"]["routes"]],
             "end_keys": list(doc["end"].get("keys") or []), "hazards": list(doc["hazards"]),
             "paths": list(doc.get("paths") or [])}
    k = len(state["paths"]) + 1
    ex = Explorer(cl, log, record, args.audit_effort, role="integrator")
    paths = "\n".join(f"{p['id']} (key node {p.get('key_node')}; END route {' + '.join(p['end_route'])}): {p['approach']}"
                      for p in state["paths"]) or "none"
    items = [{"role": "user", "content": ctx.message() + f"\n\n<graph>\n{R.graph_text(doc)}\n</graph>\n\n<paths>\n"
                                         f"{paths}\n</paths>\n\nIf the editorial's approach is already one of the END "
                                         f"routes, call editorial_covered; otherwise call submit_path with it. New "
                                         f"node ids continue at N{len(state['nodes']) + 1}, hazard ids at "
                                         f"H{len(state['hazards']) + 1}."}]
    for _ in range(C.MAX_FIXES + 1):
        call = ex.step(items, [SUBMIT_EDITORIAL, EDITORIAL_COVERED], "required", instructions=PR.INTEGRATE_INSTRUCTIONS)
        if call is None:
            items = [{"role": "user", "content": "Call editorial_covered or submit_path."}]
            continue
        ex.last_call = call
        a, err = _args(call)
        if err:
            items = [{"type": "function_call_output", "call_id": call.call_id, "output": f"Not accepted: {err}."}]
            continue
        if call.name == "editorial_covered":
            info = {"covered": True, "route": a.get("route") or [], "note": a.get("note", "")}
            record({"role": "integrator", "event": "editorial_covered", **info})
            log.info(f"editorial covered by END route {' + '.join(info['route'])}: {info['note'][:200]}")
            return doc, info, ex
        # Nodes are nodes: the editorial's claims get no mark; the path's provenance stays in paths[].source.
        new_nodes = [dict(n, source="exploration", path=f"P{k}") for n in a.get("nodes") or [] if isinstance(n, dict)]
        new_ids = [n.get("id") for n in new_nodes]
        new_hazards = [dict(h) for h in a.get("hazards") or [] if isinstance(h, dict)]
        end_route, key = a.get("end_route"), a.get("key_node")
        merged = merged_graph(state, new_nodes, end_route if isinstance(end_route, list) else [], new_hazards, key)
        problems = R.check_graph(merged, ctx.statement)
        problems += R.check_path(merged, new_ids, end_route, key, state["end_keys"])
        if problems:
            log.info("editorial path not accepted by the rules: " + "; ".join(problems)[:300])
            items = [{"type": "function_call_output", "call_id": call.call_id,
                      "output": "Not accepted: " + "; ".join(problems)
                                + ". Fix these and call submit_path again with the whole path."}]
            continue
        result = judge(ctx.problem, ctx.reference, workdir=out_dir / "judge") if judge else None
        if result and not result["accepted"]:
            log.warning(f"the reference solution gets {result['verdict']} from the judge; the editorial path is "
                        f"added anyway")
        (out_dir / "paths").mkdir(parents=True, exist_ok=True)
        (out_dir / "paths" / f"P{k}.cpp").write_text(ctx.reference, encoding="utf-8")
        path = {"id": f"P{k}", "source": "editorial", "approach": a.get("approach", ""),
                "end_route": list(end_route), "key_node": key, "new_nodes": new_ids,
                "new_hazards": [h.get("id") for h in new_hazards], "program": f"paths/P{k}.cpp", "submission": None,
                "judge": ({x: result.get(x) for x in ("verdict", "tests_run", "n_tests", "max_time_s", "time_limit_s")}
                          if result else None), "notes": a.get("notes", "")}
        new = {**doc, "nodes": merged["nodes"],
               "end": {**doc["end"], "routes": state["end_routes"] + [list(end_route)],
                       "keys": state["end_keys"] + [key]},
               "hazards": merged["hazards"], "paths": state["paths"] + [path]}
        new["solution_outline"] = outline_of(new["paths"])
        new["version"] = R.version_of(new)
        record({"role": "integrator", "event": "editorial_path", "path": path["id"], "new_nodes": new_ids})
        log.info(f"editorial path {path['id']} added: {len(new_ids)} new nodes, END route {' + '.join(end_route)}")
        return new, {"covered": False, "path": path["id"], "new_nodes": new_ids}, ex
    raise RuntimeError(f"no editorial path passed the rules after {C.MAX_FIXES + 1} tries")


def _review_loop(cl, log, record, ctx, doc: dict, ex: Explorer, reviews: list, args) -> tuple[dict, Counter]:
    """Review rounds with wording-only revisions in session ex; sets the doc's status and issues."""
    review_usage = Counter()
    for rnd in range(1, args.max_revisions + 2):
        rev, u = review(cl, log, record, ctx, doc, args.audit_effort)
        review_usage += u
        blocking, advisory = classify(rev)
        reviews.append({"round": len(reviews) + 1, "version": doc["version"], "review": rev, "blocking": blocking,
                        "advisory": advisory, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        log.info(f"review {len(reviews)} of {doc['version']}: {len(blocking)} blocking, {len(advisory)} advisory, "
                 f"verdict {rev.get('verdict')}, editorial found: {rev.get('editorial_found')}")
        for b in blocking:
            log.info(f"   blocking: {b}")
        if not blocking or rnd > args.max_revisions:
            break
        doc = revise_texts(ex, doc, ctx, blocking, advisory, log)
        doc["version"] = R.version_of(doc)
        log.info(f"texts revised: version {doc['version']}")
    last = reviews[-1]
    doc.update(status="flagged" if last["blocking"] else "accepted", open_issues=last["blocking"],
               advisories=last["advisory"])
    return doc, review_usage


def _editorial_step(cl, log, record, ctx, doc: dict, out_dir: Path, reviews: list, args, judge):
    """The editorial's path when wanted: --editorial always, or missing (default) when the last review did not
    find the editorial among the paths. Returns (doc, integrator usage, review usage)."""
    if args.editorial == "never":
        return doc, Counter(), Counter(), None
    found = reviews[-1]["review"].get("editorial_found") if reviews else None
    if args.editorial == "missing" and found is True:
        doc["editorial"] = {"covered": True, "route": None, "note": "found among the paths by the reviewer"}
        return doc, Counter(), Counter(), None
    doc, info, integ = integrate_editorial(cl, log, record, ctx, doc, out_dir, args, judge)
    doc["editorial"] = info
    review_usage = Counter()
    if not info["covered"] and not args.no_review:
        doc, review_usage = _review_loop(cl, log, record, ctx, doc, integ, reviews, args)
    return doc, integ.usage, review_usage, integ


# ----------------------------------------------------------------------------- one problem

def explore_problem(cl, problem: str, args, judge=JD.judge_program) -> dict:
    problem = normalize(problem)
    log = logging.getLogger(f"explore.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = A.Recorder(out_dir / "sessions.jsonl")
    ctx = ProblemContext(problem)
    record({"event": "start exploration", "problem": problem, "model": C.API_MODEL, "effort": args.effort,
            "max_paths": args.max_paths, "inputs": ctx.hashes(), "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    state, ex = explore(cl, log, record, ctx, out_dir, args, judge)
    prov = {"model": C.API_MODEL, "mode": "exploration", "explore_effort": args.effort,
            "audit_effort": args.audit_effort, "max_paths": args.max_paths,
            "explorer_calls": ex.calls, "submissions": state["submissions"], "review_rounds": 0,
            "edited_by_hand": False, "usage": {"explorer": dict(ex.usage)}, "inputs": ctx.hashes(),
            "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc = assemble(problem, ctx, state, "unreviewed", prov)
    reviews, review_usage = [], Counter()
    if not args.no_review and state["paths"]:
        doc, review_usage = _review_loop(cl, log, record, ctx, doc, ex, reviews, args)
    elif not state["paths"]:
        doc["status"] = "empty"
    doc, integ_usage, u, integ = _editorial_step(cl, log, record, ctx, doc, out_dir, reviews, args, judge)
    review_usage += u
    doc["provenance"].update(review_rounds=len(reviews), usage={
        "explorer": dict(ex.usage), "integrator": dict(integ_usage), "reviewer": dict(review_usage),
        "total": A.usage_sum(ex.usage, integ_usage, review_usage)})
    B.finish(out_dir, doc, reviews)
    return doc


def editorial_problem(cl, problem: str, args, judge=JD.judge_program) -> dict:
    """--editorial-only: the editorial step on an existing graph.json, then a review of the added path."""
    problem = normalize(problem)
    log = logging.getLogger(f"explore.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    doc = B.load_json(out_dir / "graph.json")
    if doc is None:
        raise SystemExit(f"{problem}: no {out_dir / 'graph.json'}")
    reviews = B.load_json(out_dir / "review.json", [])
    ctx = ProblemContext(problem)
    record = A.Recorder(out_dir / "sessions.jsonl")
    record({"event": "start editorial step", "problem": problem, "graph_version": doc["version"],
            "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    forced = argparse.Namespace(**{**vars(args), "editorial": "always"})
    doc, integ_usage, review_usage, integ = _editorial_step(cl, log, record, ctx, doc, out_dir, reviews, forced, judge)
    prov = doc["provenance"]
    prov["review_rounds"] = len(reviews)
    prov.setdefault("usage", {})
    prov["usage"]["integrator"] = A.usage_sum(prov["usage"].get("integrator", {}), integ_usage)
    prov["usage"]["reviewer"] = A.usage_sum(prov["usage"].get("reviewer", {}), review_usage)
    prov["usage"]["total"] = A.usage_sum(prov["usage"].get("total", {}), integ_usage, review_usage)
    prov["editorial_step"] = time.strftime("%Y-%m-%d %H:%M:%S")
    B.finish(out_dir, doc, reviews)
    return doc


def revise_problem(cl, problem: str, args, judge=JD.judge_program) -> dict:
    """--revise-from: a wording-only revision of an existing graph.json from findings (validate.py's
    feedback.json, or any {blocking, advisory} JSON) in a fresh session, then a review. The structure
    (nodes, routes, END routes) is not changed: a missing route is added by the editorial step or by a new
    exploration."""
    problem = normalize(problem)
    log = logging.getLogger(f"explore.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    doc = B.load_json(out_dir / "graph.json")
    if doc is None:
        raise SystemExit(f"{problem}: no {out_dir / 'graph.json'}")
    fb = B.load_json(Path(args.revise_from))
    if fb is None:
        raise SystemExit(f"no feedback file {args.revise_from}")
    if isinstance(fb, list):
        fb = {"blocking": fb, "advisory": []}
    if fb.get("graph_version") and fb["graph_version"] != doc["version"]:
        log.warning(f"feedback is for graph version {fb['graph_version']}, the graph is {doc['version']}")
    reviews = B.load_json(out_dir / "review.json", [])
    ctx = ProblemContext(problem)
    record = A.Recorder(out_dir / "sessions.jsonl")
    record({"event": "start revision", "problem": problem, "from": str(args.revise_from),
            "graph_version": doc["version"], "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    session = Explorer(cl, log, record, args.audit_effort, role="reviser")
    old_version = doc["version"]
    doc = revise_texts(session, doc, ctx, fb.get("blocking") or [], fb.get("advisory") or [], log,
                       lead=PR.REVISE_FROM_FEEDBACK_LEAD)
    doc["version"] = R.version_of(doc)
    log.info(f"texts revised from feedback: {old_version} -> {doc['version']}")
    review_usage = Counter()
    if not args.no_review:
        doc, review_usage = _review_loop(cl, log, record, ctx, doc, session, reviews, args)
    prov = doc["provenance"]
    prov["review_rounds"] = len(reviews)
    prov.setdefault("usage", {})
    prov["usage"]["reviser"] = A.usage_sum(prov["usage"].get("reviser", {}), session.usage)
    prov["usage"]["reviewer"] = A.usage_sum(prov["usage"].get("reviewer", {}), review_usage)
    prov["usage"]["total"] = A.usage_sum(prov["usage"].get("total", {}), session.usage, review_usage)
    prov.setdefault("revisions", []).append({"from": str(args.revise_from), "graph_version": old_version,
                                             "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    B.finish(out_dir, doc, reviews)
    return doc


# ----------------------------------------------------------------------------- CLI

def list_status(problems: list[str]) -> None:
    print(f"{'problem':34s} {'status':11s} {'version':17s} nodes paths hazards subs reviews  tokens in/out")
    for p in problems:
        doc = B.load_json(graph_dir(p) / "graph.json")
        if doc is None:
            print(f"{p:34s} -")
            continue
        u = doc["provenance"].get("usage", {}).get("total") or doc["provenance"].get("usage", {}).get("explorer", {})
        ex = doc.get("exploration") or {}
        print(f"{p:34s} {doc['status']:11s} {doc['version']:17s} {len(doc['nodes']):5d} {len(doc.get('paths') or []):5d} "
              f"{len(doc['hazards']):7d} {ex.get('submissions', 0):4d} {doc['provenance'].get('review_rounds', 0):7d}  "
              f"{u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}")


def main(argv=None, client=None, judge=JD.judge_program):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problems", nargs="*", default=None, help="default: every problem in problems.txt")
    ap.add_argument("--force", action="store_true", help="re-explore problems that have graph.json")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--effort", default=C.EXPLORE_EFFORT, help="the explorer's reasoning effort")
    ap.add_argument("--audit-effort", default=C.AUDIT_EFFORT)
    ap.add_argument("--max-paths", type=int, default=C.MAX_PATHS)
    ap.add_argument("--max-revisions", type=int, default=C.MAX_REVISIONS)
    ap.add_argument("--no-review", action="store_true", help="skip the reviewer (editorial and reference unused)")
    ap.add_argument("--editorial", choices=("missing", "always", "never"), default="missing",
                    help="add the editorial's approach as a path: when the reviewer does not find it among the "
                         "paths (missing, default), always, or never")
    ap.add_argument("--revise-from", type=Path,
                    help="wording-only revision of the existing graph.json from validate.py's feedback.json, then a review")
    ap.add_argument("--editorial-only", action="store_true",
                    help="only the editorial step on the existing graph.json (then a review)")
    ap.add_argument("--jobs", type=int, default=C.JOBS)
    ap.add_argument("--graphs-dir", type=Path, default=None,
                    help=f"write the graphs under this directory instead of {C.GRAPHS_DIR} (experiments)")
    args = ap.parse_args(argv)
    if args.graphs_dir is not None:
        C.GRAPHS_DIR = args.graphs_dir.resolve()      # problems.graph_dir reads it at call time
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "openai", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    problems = [normalize(p) for p in (args.problems or read_problem_list())]
    if args.list:
        list_status(problems)
        return 0
    if args.render_only:
        for p in problems:
            out_dir = graph_dir(p)
            doc = B.load_json(out_dir / "graph.json")
            if doc:
                render.write_all(out_dir, doc, B.load_json(out_dir / "review.json", []))
                print(f"{p}: rendered {out_dir}")
        return 0
    if args.editorial_only or args.revise_from:
        todo = [p for p in problems if (graph_dir(p) / "graph.json").exists()]
        work = editorial_problem if args.editorial_only else revise_problem
        for p in sorted(set(problems) - set(todo)):
            logging.info(f"{p}: no graph.json")
    else:
        todo, work = [p for p in problems if args.force or not (graph_dir(p) / "graph.json").exists()], explore_problem
        for p in sorted(set(problems) - set(todo)):
            logging.info(f"{p}: graph.json exists (--force to re-explore)")
    if not todo:
        return 0
    cl = client or A.client()
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(work, cl, p, args, judge): p for p in todo}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                doc = fut.result()
            except Exception as e:
                logging.exception(f"{p}: failed: {e}")
                failed.append(p)
                continue
            logging.info(f"{p}: {doc['status']}, {len(doc['nodes'])} nodes, {len(doc['paths'])} paths, version "
                         f"{doc['version']} -> {graph_dir(p)}")
    list_status(todo)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
