"""A problem's reasoning graph: the lemmas and intermediate conclusions a solver has to establish
(nodes, each with the alternative sets of earlier nodes it is derived from), END (the solution
families) and the hazards on the edge from END to the program. Built by gpt-6-astra from the
statement, the editorial and the reference solution; checked by rules, a reviewer in a fresh
session; revised until accepted
or MAX_REVISIONS is reached. See ../design.md.

    python3 build.py --problems 2025/J-stacking-cups           # build (skips problems that have graph.json)
    python3 build.py --problems P --force                       # rebuild
    python3 build.py --audit-only --problems P                  # after a hand edit of graph.json: rules + one review
    python3 build.py --revise-from FEEDBACK.json --problems P   # revise from validate.py's feedback (fresh builder)
    python3 build.py --render-only --problems P                 # rewrite graph.md / graph.dot / graph.png
    python3 build.py --list
    python3 build.py --max-nodes 30 --problems P                # raise the soft cap when a third family is shown

Writes graph/graphs/<slug>/{graph.json, review.json, graph.md, graph.dot, graph.png,
sessions.jsonl} and every graph written to history/graph_<version>.json. Run it on the login node:
compute nodes have no internet.
"""
import argparse
import json
import logging
import os
import re
import sys
import threading
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

SCHEMA = "reasoning-graph-v2"

# ----------------------------------------------------------------------------- tools

_ROUTES = {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
           "description": "OR of ANDs: alternative sets of earlier node ids; [[]] = from the statement alone"}
_NODE_PROPS = {"id": {"type": "string", "description": "N1, N2, ..."},
               "name": {"type": "string"},
               "kind": {"type": "string", "enum": list(C.KINDS)},
               "statement": {"type": "string"},
               "routes": _ROUTES,
               "accept": {"type": "string"},
               "anchors": {"type": "array", "items": {"type": "string"}},
               "source": {"type": "string", "enum": list(C.SOURCES)}}
_NODE = {"type": "object", "additionalProperties": False, "required": list(_NODE_PROPS), "properties": _NODE_PROPS}
_END = {"type": "object", "additionalProperties": False, "required": ["statement", "routes"],
        "properties": {"statement": {"type": "string"}, "routes": _ROUTES}}
_HAZARD = {"type": "object", "additionalProperties": False, "required": ["id", "statement", "check"],
           "properties": {"id": {"type": "string", "description": "H1, H2, ..."},
                          "statement": {"type": "string"}, "check": {"type": "string"}}}
SUBMIT_GRAPH = A.fn(
    "submit_graph", "The problem's reasoning graph: nodes, END and hazards.",
    solution_outline={"type": "string"},
    nodes={"type": "array", "items": _NODE},
    end=_END,
    hazards={"type": "array", "items": _HAZARD},
    notes={"type": "string", "description": "For the reviewer: where and why you kept something an earlier "
                                            "review or finding objected to. Empty on the first submission."})

NODE_FLAGS = ("specific", "correct", "judgeable", "route_independent", "separable", "atomic")
_REVIEW_NODE = {"type": "object", "additionalProperties": False,
                "required": ["id", *NODE_FLAGS, "note"],
                "properties": {"id": {"type": "string"}, **{f: {"type": "boolean"} for f in NODE_FLAGS},
                               "note": {"type": "string"}}}
_ALTERNATIVE = {"type": "object", "additionalProperties": False,
                "required": ["approach", "correct_and_fast", "representable", "note"],
                "properties": {"approach": {"type": "string"}, "correct_and_fast": {"type": "boolean"},
                               "representable": {"type": "boolean"}, "note": {"type": "string"}}}
SUBMIT_REVIEW = A.fn(
    "submit_review", "Your review of the graph: one entry per node, END, hazards, what is missing, alternatives.",
    nodes={"type": "array", "items": _REVIEW_NODE},
    end_ok={"type": "boolean"}, end_note={"type": "string"},
    hazards_ok={"type": "boolean"}, hazards_note={"type": "string"},
    missing={"type": "array", "items": {"type": "string"}},
    alternatives={"type": "array", "items": _ALTERNATIVE},
    order={"type": "string"},
    verdict={"type": "string", "enum": ["accept", "revise"]})

# Blocking and advisory review flags, in the words the builder is shown.
BLOCKING = {"specific": "not specific to this problem",
            "correct": "a claim or a route is wrong or cannot be judged",
            "judgeable": "a reader of a solver's work cannot decide whether the solver has it",
            "route_independent": "it states one implementation's choice, not what every correct solution "
                                 "through this step gets right"}
ADVISORY = {"separable": "comes with its prerequisite; merge it", "atomic": "bundles claims a solver can have "
                                                                             "separately; split it"}


# ----------------------------------------------------------------------------- checks

def accept_graph(args: dict, ctx: ProblemContext, max_nodes: int | None = None) -> tuple[dict, list[str]]:
    """A submitted graph with derived fields, and what is wrong with it."""
    sub = R.derive(args)
    return sub, R.check_graph(sub, ctx.statement, C.MIN_NODES, max_nodes or C.MAX_NODES)


def check_review(rev: dict, sub: dict) -> list[str]:
    want = R.node_ids(sub)
    got = [r.get("id") for r in rev.get("nodes") or []]
    problems = []
    if sorted(got) != sorted(want):
        problems.append(f"give exactly one entry per node {want}; you gave {got}")
    if not rev.get("alternatives"):
        problems.append("give at least one alternative approach (alternatives), with correct_and_fast, "
                        "representable and note")
    return problems


def classify(rev: dict, sub: dict) -> tuple[list[str], list[str]]:
    """(blocking issues, advisories) of a review, in the words the builder is shown. Decided from the
    flags, not from the reviewer's verdict."""
    blocking, advisory = [], []
    for r in rev.get("nodes") or []:
        bad = [f for f in BLOCKING if not r.get(f, True)]
        soft = [f for f in ADVISORY if not r.get(f, True)]
        words = [BLOCKING[f] for f in bad] + [ADVISORY[f] for f in soft]
        if bad:
            blocking.append(f"{r['id']} ({'; '.join(words)}): {r.get('note', '')}")
        elif soft:
            advisory.append(f"{r['id']} ({'; '.join(words)}): {r.get('note', '')}")
    if not rev.get("end_ok", True):
        blocking.append(f"END: {rev.get('end_note', '')}")
    if not rev.get("hazards_ok", True):
        blocking.append(f"hazards: {rev.get('hazards_note', '')}")
    blocking += [f"missing: {m}" for m in rev.get("missing") or [] if m.strip()]
    for a in rev.get("alternatives") or []:
        if a.get("representable"):
            continue
        line = f"{a.get('approach', '')} -- {a.get('note', '')}"
        if a.get("correct_and_fast"):
            blocking.append(f"missing route (an approach the reviewer shows correct and fast enough that the graph "
                            f"cannot represent): {line}")
        else:
            advisory.append(f"alternative the graph cannot represent (not shown correct and fast): {line}")
    if (rev.get("order") or "").strip():
        advisory.append(f"order: {rev['order'].strip()}")
    return blocking, advisory


def feedback(blocking: list[str], advisory: list[str]) -> str:
    lines = ["Accepted by the format checks. An independent reviewer, who saw the statement, the editorial and "
             "the reference solution, then found:", "", "Blocking:"]
    lines += [f"- {b}" for b in blocking] or ["- nothing"]
    if advisory:
        lines += ["", "Also consider (not blocking):"] + [f"- {a}" for a in advisory]
    lines += ["", "Revise the graph and call submit_graph again with all of it. If you are sure the reviewer is "
                  "wrong about something, keep it and say why in notes."]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- sessions

class Builder:
    """The builder's session. Revisions continue it, so it keeps its own reasoning. accept(arguments)
    gives (submission, problems with it)."""

    def __init__(self, cl, log, record, ctx: ProblemContext, effort: str, accept, role: str = "builder"):
        self.cl, self.log, self.record, self.ctx, self.effort = cl, log, record, ctx, effort
        self.accept, self.role = accept, role
        self.prev, self.call = None, None
        self.usage, self.submissions = Counter(), 0

    def _submit(self, input_items: list) -> dict:
        for _ in range(C.MAX_FIXES + 1):
            kw = dict(model=C.API_MODEL, instructions=PR.BUILD_INSTRUCTIONS, input=input_items,
                      tools=[SUBMIT_GRAPH], tool_choice={"type": "function", "name": "submit_graph"},
                      reasoning={"effort": self.effort})
            if self.prev:
                kw["previous_response_id"] = self.prev
            resp = A.respond(self.cl, self.log, self.record, self.role, **kw)
            self.usage += A.usage_of(resp)
            self.prev = resp.id
            call = A.function_call(resp)
            if call is None:
                input_items = [{"role": "user", "content": "Call submit_graph."}]
                continue
            self.submissions += 1
            self.call = call
            try:
                sub, problems = self.accept(json.loads(call.arguments))
            except json.JSONDecodeError:
                sub, problems = None, ["the arguments are not valid JSON"]
            self.record({"role": self.role, "event": "checked", "submission": self.submissions,
                         "problems": problems})
            if not problems:
                return sub
            self.log.warning(f"{self.role} submission {self.submissions} not accepted: " + "; ".join(problems))
            input_items = [{"type": "function_call_output", "call_id": call.call_id,
                            "output": "Not accepted: " + "; ".join(problems)
                                      + ". Fix these and call submit_graph again."}]
        raise RuntimeError(f"no submit_graph call passed the rules after {C.MAX_FIXES + 1} submissions")

    def first(self, message: str | None = None) -> dict:
        return self._submit([{"role": "user", "content": message or self.ctx.message()}])

    def revise(self, text: str) -> dict:
        return self._submit([{"type": "function_call_output", "call_id": self.call.call_id, "output": text}])


def _forced(cl, log, record, role, instructions, tool, message, effort, checker, what):
    """One fresh session that must end in an accepted call of tool: the answer is checked and sent back
    with the reasons until it passes (3 tries)."""
    input_items, prev, usage = [{"role": "user", "content": message}], None, Counter()
    for _ in range(3):
        kw = dict(model=C.API_MODEL, instructions=instructions, input=input_items, tools=[tool],
                  tool_choice={"type": "function", "name": tool["name"]}, reasoning={"effort": effort})
        if prev:
            kw["previous_response_id"] = prev
        resp = A.respond(cl, log, record, role, **kw)
        usage += A.usage_of(resp)
        prev = resp.id
        call = A.function_call(resp)
        if call is None:
            input_items = [{"role": "user", "content": f"Call {tool['name']}."}]
            continue
        try:
            ans = json.loads(call.arguments)
            problems = checker(ans)
        except json.JSONDecodeError:
            problems = ["the arguments are not valid JSON"]
        if not problems:
            return ans, usage
        input_items = [{"type": "function_call_output", "call_id": call.call_id,
                        "output": "Not accepted: " + "; ".join(problems) + f". Call {tool['name']} again."}]
    raise RuntimeError(f"{what}: no usable answer after 3 tries")


def review(cl, log, record, ctx: ProblemContext, sub: dict, effort: str) -> tuple[dict, Counter]:
    """One review in a fresh session."""
    message = ctx.message() + f"\n\n<graph>\n{R.graph_text(sub)}\n</graph>"
    if (sub.get("notes") or "").strip():
        message += f"\n\n<builder_notes>\n{sub['notes'].strip()}\n</builder_notes>"
    return _forced(cl, log, record, "reviewer", PR.REVIEW_INSTRUCTIONS, SUBMIT_REVIEW, message, effort,
                   lambda ans: check_review(ans, sub), "the reviewer")


# ----------------------------------------------------------------------------- files

def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path, default=None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default


def finish(out_dir: Path, doc: dict, reviews: list[dict]) -> None:
    """Every graph written is also kept as history/graph_<version>.json: gradings record the version they
    used, and a hand edit of graph.json must not lose the graph it started from."""
    write_json_atomic(out_dir / "review.json", reviews)
    write_json_atomic(out_dir / "history" / f"graph_{doc['version']}.json", doc)
    write_json_atomic(out_dir / "graph.json", doc)
    render.write_all(out_dir, doc, reviews)


def _doc(problem, ctx, sub, reviews, builder, review_usage, args, extra=None) -> dict:
    last = reviews[-1]
    open_issues = last["blocking"]
    return {"schema": SCHEMA, "problem": problem, "title": ctx.title,
            "status": "flagged" if open_issues else "accepted",
            "version": R.version_of(sub), "solution_outline": sub["solution_outline"],
            "nodes": sub["nodes"], "end": sub["end"], "hazards": sub["hazards"],
            "builder_notes": sub.get("notes", ""),
            "open_issues": open_issues, "advisories": last["advisory"],
            "provenance": {"model": C.API_MODEL, "gen_effort": args.gen_effort, "audit_effort": args.audit_effort,
                           "max_nodes": args.max_nodes or C.MAX_NODES,
                           "builder_submissions": builder.submissions, "review_rounds": len(reviews),
                           "edited_by_hand": False,
                           "usage": {"builder": dict(builder.usage), "reviewer": dict(review_usage),
                                     "total": A.usage_sum(builder.usage, review_usage)},
                           "inputs": ctx.hashes(), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                           **(extra or {})}}


# ----------------------------------------------------------------------------- one problem

def _loop(cl, log, record, ctx, problem, builder, sub, args, reviews=None):
    """Review rounds with revisions in the builder's session, until accepted or out of rounds."""
    reviews, review_usage = list(reviews or []), Counter()
    for rnd in range(1, args.max_revisions + 2):
        rev, u = review(cl, log, record, ctx, sub, args.audit_effort)
        review_usage += u
        blocking, advisory = classify(rev, sub)
        reviews.append({"round": len(reviews) + 1, "version": R.version_of(sub), "review": rev,
                        "blocking": blocking, "advisory": advisory,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        log.info(f"review {rnd} of {R.version_of(sub)}: {len(blocking)} blocking, {len(advisory)} advisory, "
                 f"reviewer verdict {rev.get('verdict')}")
        for b in blocking:
            log.info(f"   blocking: {b}")
        if not blocking or rnd > args.max_revisions:
            break
        sub = builder.revise(feedback(blocking, advisory))
        log.info(f"revised graph {R.version_of(sub)}: {len(sub['nodes'])} nodes")
    return sub, reviews, review_usage


def build_problem(cl, problem: str, args) -> dict:
    problem = normalize(problem)
    log = logging.getLogger(f"graph.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = A.Recorder(out_dir / "sessions.jsonl")
    ctx = ProblemContext(problem)
    record({"event": "start", "problem": problem, "model": C.API_MODEL, "gen_effort": args.gen_effort,
            "audit_effort": args.audit_effort, "inputs": ctx.hashes(), "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    builder = Builder(cl, log, record, ctx, args.gen_effort, lambda a: accept_graph(a, ctx, args.max_nodes))
    sub = builder.first()
    log.info(f"graph {R.version_of(sub)}: {len(sub['nodes'])} nodes after {builder.submissions} submission(s)")
    sub, reviews, ru = _loop(cl, log, record, ctx, problem, builder, sub, args)
    doc = _doc(problem, ctx, sub, reviews, builder, ru, args)
    finish(out_dir, doc, reviews)
    return doc


def revise_problem(cl, problem: str, args) -> dict:
    """Revise an existing graph from findings (validate.py's feedback.json, or any {blocking, advisory} JSON)
    in a fresh builder session that sees the problem, the graph and the findings."""
    problem = normalize(problem)
    log = logging.getLogger(f"graph.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    doc = load_json(out_dir / "graph.json")
    if doc is None:
        raise SystemExit(f"{problem}: no {out_dir / 'graph.json'}")
    fb = load_json(Path(args.revise_from))
    if fb is None:
        raise SystemExit(f"no feedback file {args.revise_from}")
    if isinstance(fb, list):
        fb = {"blocking": fb, "advisory": []}
    if fb.get("graph_version") and fb["graph_version"] != doc["version"]:
        log.warning(f"feedback is for graph version {fb['graph_version']}, the graph is {doc['version']}")
    ctx = ProblemContext(problem)
    record = A.Recorder(out_dir / "sessions.jsonl")
    record({"event": "start revision", "problem": problem, "from": str(args.revise_from),
            "graph_version": doc["version"], "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    findings = ["Blocking:"] + [f"- {b}" for b in fb.get("blocking") or []] or ["- nothing"]
    if fb.get("advisory"):
        findings += ["", "Also consider (not blocking):"] + [f"- {a}" for a in fb["advisory"]]
    message = (ctx.message() + f"\n\n<graph>\n{R.graph_text(doc, traps=True)}\n</graph>\n\n<findings>\n"
               + "\n".join(findings) + f"\n</findings>\n\n{PR.REVISE_LEAD}")
    builder = Builder(cl, log, record, ctx, args.gen_effort, lambda a: accept_graph(a, ctx, args.max_nodes))
    sub = builder.first(message)
    log.info(f"revised graph {R.version_of(sub)}: {len(sub['nodes'])} nodes after {builder.submissions} "
             f"submission(s)")
    sub, reviews, ru = _loop(cl, log, record, ctx, problem, builder, sub, args,
                             reviews=load_json(out_dir / "review.json", []))
    new = _doc(problem, ctx, sub, reviews, builder, ru, args,
               extra={"revised_from": {"graph_version": doc["version"], "feedback": str(args.revise_from)}})
    # Traps are grading data: keep those of nodes that kept their id and statement.
    old = {n["id"]: n for n in doc.get("nodes") or []}
    for n in new["nodes"]:
        o = old.get(n["id"])
        if o and o.get("statement") == n.get("statement") and o.get("traps"):
            n["traps"] = o["traps"]
    finish(out_dir, new, reviews)
    return new


def audit_problem(cl, problem: str, args) -> dict:
    """Review an existing (possibly hand-edited) graph.json once more; the graph itself is not changed."""
    problem = normalize(problem)
    log = logging.getLogger(f"graph.{slug_of(problem)}")
    out_dir = graph_dir(problem)
    doc = load_json(out_dir / "graph.json")
    if doc is None:
        raise SystemExit(f"{problem}: no {out_dir / 'graph.json'}")
    ctx = ProblemContext(problem)
    doc = {**doc, **R.derive(doc)}
    problems = R.check_graph(doc, ctx.statement, C.MIN_NODES, args.max_nodes or C.MAX_NODES)
    if problems:
        raise SystemExit(f"{problem}: graph.json breaks the rules:\n  " + "\n  ".join(problems))
    record = A.Recorder(out_dir / "sessions.jsonl")
    sub = {"solution_outline": doc["solution_outline"], "nodes": doc["nodes"], "end": doc["end"],
           "hazards": doc["hazards"], "notes": doc.get("builder_notes", "")}
    rev, usage = review(cl, log, record, ctx, sub, args.audit_effort)
    blocking, advisory = classify(rev, sub)
    reviews = load_json(out_dir / "review.json", [])
    reviews.append({"round": len(reviews) + 1, "version": R.version_of(sub), "review": rev,
                    "blocking": blocking, "advisory": advisory, "audit_only": True,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    new_version = R.version_of(sub)
    prov = doc["provenance"]
    prov["edited_by_hand"] = prov.get("edited_by_hand", False) or new_version != doc["version"]
    prov["review_rounds"] = len(reviews)
    prov["usage"]["reviewer"] = A.usage_sum(prov["usage"].get("reviewer", {}), usage)
    prov["usage"]["total"] = A.usage_sum(prov["usage"].get("total", {}), usage)
    doc.update(version=new_version, status="flagged" if blocking else "accepted", open_issues=blocking,
               advisories=advisory)
    finish(out_dir, doc, reviews)
    log.info(f"audit of {new_version}: {len(blocking)} blocking, {len(advisory)} advisory")
    return doc


# ----------------------------------------------------------------------------- CLI

def list_status(problems: list[str]) -> None:
    print(f"{'problem':34s} {'status':9s} {'version':17s} nodes END-routes hazards reviews  tokens in/out")
    for p in problems:
        doc = load_json(graph_dir(p) / "graph.json")
        if doc is None:
            print(f"{p:34s} -")
            continue
        u = doc["provenance"]["usage"]["total"]
        print(f"{p:34s} {doc['status']:9s} {doc['version']:17s} {len(doc['nodes']):5d} "
              f"{len(doc['end']['routes']):10d} {len(doc['hazards']):7d} {doc['provenance']['review_rounds']:7d}  "
              f"{u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}")


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problems", nargs="*", default=None, help="default: every problem in problems.txt")
    ap.add_argument("--force", action="store_true", help="rebuild problems that have graph.json")
    ap.add_argument("--audit-only", action="store_true", help="review the existing graph.json once more")
    ap.add_argument("--revise-from", type=Path, help="revise the existing graph.json from this feedback JSON")
    ap.add_argument("--render-only", action="store_true", help="rewrite graph.md / graph.dot / graph.png; no API")
    ap.add_argument("--list", action="store_true", help="status of every problem; no API call")
    ap.add_argument("--gen-effort", default=C.GEN_EFFORT)
    ap.add_argument("--audit-effort", default=C.AUDIT_EFFORT)
    ap.add_argument("--max-revisions", type=int, default=C.MAX_REVISIONS)
    ap.add_argument("--max-nodes", type=int, default=None, help=f"soft cap on nodes (default {C.MAX_NODES})")
    ap.add_argument("--jobs", type=int, default=C.JOBS, help="problems built at once")
    args = ap.parse_args(argv)
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
            doc = load_json(out_dir / "graph.json")
            if doc:
                render.write_all(out_dir, doc, load_json(out_dir / "review.json", []))
                print(f"{p}: rendered {out_dir}")
        return 0
    if args.audit_only:
        todo, work = problems, audit_problem
    elif args.revise_from:
        todo, work = problems, revise_problem
    else:
        todo = [p for p in problems if args.force or not (graph_dir(p) / "graph.json").exists()]
        for p in sorted(set(problems) - set(todo)):
            logging.info(f"{p}: graph.json exists (--force to rebuild)")
        work = build_problem
    if not todo:
        return 0
    cl = client or A.client()
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(work, cl, p, args): p for p in todo}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                doc = fut.result()
            except Exception as e:                       # one problem must not stop the others
                logging.exception(f"{p}: failed: {e}")
                failed.append(p)
                continue
            logging.info(f"{p}: {doc['status']}, {len(doc['nodes'])} nodes, version {doc['version']} -> "
                         f"{graph_dir(p)}")
    list_status(todo)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
