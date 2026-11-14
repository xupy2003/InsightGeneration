"""The structural rules of a reasoning-graph-v2 graph, its derived fields and its text. No model calls.

A graph: nodes N1..Nk (claims about the problem), each with `routes`, an OR of ANDs of earlier
nodes it is derived from ([[]] = from the statement alone); END with its routes, the solution
families; and hazards H1.. on the edge from END to the program (constraints every correct
program must meet).

The rules (check_graph) are the ones that keep a graph valid and readable by the probes: ids in
order, routes to earlier nodes only (acyclic), no duplicate or subset routes, distinct END routes,
every node on a derivation of END, a node derived from the statement, the text limits of the
fields, no generic node names, no answer tables. Counts of nodes (unless asked), routes,
prerequisites, END routes, hazards and anchors are not capped. The anchor checks only warn
(warnings_of). A graph that breaks a rule goes back to its builder with the reasons.
"""
import json
import re

import config as C
from problems import sha256

# A statement whose claim is that something is fast enough or fits the limits. Such a claim is not a step of
# the solution: it is a property of the algorithm or construction node it qualifies (its accept), or a hazard.
# An error on a key node (check_path), a warning on any other node (warnings_of); a false positive is fixed
# by rewording the claim as what is computed rather than how fast.
COMPLEXITY = re.compile(
    r"\bO\s*\(|\bfits?\b[^.;]{0,40}\blimits?\b|\bfast enough\b|\bsufficiently fast\b|"
    r"\bwithin the (time|memory|input)?\s?limits?\b|\btime limit\b|\bcomplexity\b|\befficient(ly)?\b|"
    r"\bfeasib(le|ility)\b|\bin (linear|quadratic|logarithmic|polynomial|constant|amortized)[ -]time\b|"
    r"\bamortized\b|\bruns? in time\b", re.I)
KEY_KINDS = ("algorithm", "construction")

# Node names that fit every problem. The reviewer judges subtler cases.
GENERIC_NAME = re.compile(
    r"^(the )?(problem )?(understanding|understand(ing)? the (problem|statement|input)|"
    r"read(ing)? (the )?input|input( parsing)?|parsing|modell?ing|algorithm( design)?|"
    r"design(ing)? (an|the) algorithm|implementation|implement(ing)? the "
    r"(solution|algorithm|code)|coding|edge cases?|(handle|handling) edge cases|corner cases?|"
    r"complexity( analysis)?|analy[sz](e|is|ing)( of)? (the )?complexity|testing|debugging|"
    r"verification|output( formatting)?|optimi[sz]ation|solution|key (insight|observation)|"
    r"main (idea|observation)|final answer)$")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _forms(anchor: str) -> set[str]:
    a = _norm(anchor)
    forms = {a}
    if a.endswith("es"):
        forms.add(a[:-2])
    if a.endswith("s"):
        forms.add(a[:-1])
    return {f for f in forms if len(f) >= 3}      # "n" or "h" would match any text


def _mentions(text: str, anchor: str) -> bool:
    t = _norm(text)
    return any(f in t for f in _forms(anchor))


def _words(text) -> int:
    return len((text or "").split())


def node_ids(sub: dict) -> list[str]:
    return [n.get("id") for n in sub.get("nodes") or []]


def _route_problems(owner: str, routes, known: list[str], allow_empty: bool) -> list[str]:
    """What is wrong with a node's (or END's) routes; known lists the earlier nodes' ids."""
    out = []
    if not isinstance(routes, list) or not routes:
        return [f"{owner} needs routes, a non-empty list of lists of earlier node ids"]
    seen = []
    for i, route in enumerate(routes, 1):
        if not isinstance(route, list) or any(not isinstance(x, str) for x in route):
            out.append(f"{owner} route {i} must be a list of node ids")
            continue
        if not route:
            if not allow_empty:
                out.append(f"{owner} route {i} is empty; END routes list the nodes of a complete solution")
            elif len(routes) > 1:
                out.append(f"{owner} is derived from the statement alone (route {i} is empty), so it needs no "
                           f"other route; give [[]] only")
        bad = [x for x in route if x not in known]
        if bad:
            out.append(f"{owner} route {i} uses {bad}, which are not earlier nodes (routes list only nodes with "
                       f"smaller numbers; reorder, or the dependence runs the other way)")
        if len(set(route)) < len(route):
            out.append(f"{owner} route {i} lists a node twice")
        s = set(route)
        for j, other in enumerate(seen, 1):
            if s == other:
                out.append(f"{owner} routes {j} and {i} are the same")
            elif s > other or s < other:
                out.append(f"{owner} routes {j} and {i}: one is a subset of the other, so the larger one adds "
                           f"nothing; keep the smaller, or make them genuinely different derivations")
        seen.append(s)
    return out


def check_graph(sub: dict, statement: str, min_nodes: int | None = None, max_nodes: int | None = None) -> list[str]:
    """What is wrong with a submitted graph; empty if nothing is. min_nodes and max_nodes cap the node count
    only when given (the old editorial-based builder gives them; the explorer does not)."""
    problems = []
    nodes = sub.get("nodes") or []
    if min_nodes is not None and len(nodes) < min_nodes:
        problems.append(f"give at least {min_nodes} nodes, not {len(nodes)}")
    if max_nodes is not None and len(nodes) > max_nodes:
        problems.append(f"give at most {max_nodes} nodes, not {len(nodes)}")
    if not (sub.get("solution_outline") or "").strip():
        problems.append("solution_outline is empty")
    numbers_in_statement = set(re.findall(r"\d+", statement or ""))
    known = []
    for k, n in enumerate(nodes, 1):
        nid = f"N{k}"
        if n.get("id") != nid:
            problems.append(f"node {k} must have id {nid}, not {n.get('id')!r}")
        name = n.get("name") or ""
        if not name.strip():
            problems.append(f"{nid} has no name")
        elif _words(name) > C.WORDS["name"]:
            problems.append(f"{nid} name has {_words(name)} words; at most {C.WORDS['name']}")
        if GENERIC_NAME.match(re.sub(r"[^a-z ]", "", _norm(name)).strip()):
            problems.append(f"{nid} name {name!r} fits any problem; name what this node establishes for this problem")
        if n.get("kind") not in C.KINDS:
            problems.append(f"{nid} kind must be one of {', '.join(C.KINDS)}, not {n.get('kind')!r}")
        if n.get("source") not in C.SOURCES:
            problems.append(f"{nid} source must be one of {', '.join(C.SOURCES)}, not {n.get('source')!r}")
        stmt = n.get("statement") or ""
        if not stmt.strip():
            problems.append(f"{nid} has no statement")
        elif _words(stmt) > C.WORDS["statement"]:
            problems.append(f"{nid} statement has {_words(stmt)} words; at most {C.WORDS['statement']}")
        listed = sorted(set(re.findall(r"\d+", stmt)) - numbers_in_statement, key=int)
        if len(listed) >= C.ANSWER_NUMBERS:
            problems.append(f"{nid} lists {len(listed)} numbers the statement does not contain "
                            f"({', '.join(listed[:10])}{', ...' if len(listed) > 10 else ''}): it reads as "
                            f"precomputed answers; say how such values are obtained instead of listing them")
        accept = n.get("accept") or ""
        if not accept.strip():
            problems.append(f"{nid} has no accept")
        elif _words(accept) > C.WORDS["accept"]:
            problems.append(f"{nid} accept has {_words(accept)} words; at most {C.WORDS['accept']}")
        if not isinstance(n.get("anchors"), list):
            problems.append(f"{nid} anchors must be a list of short names (possibly empty)")
        problems += _route_problems(nid, n.get("routes"), known, allow_empty=True)
        known.append(nid)
    if nodes and not any(r == [] for n in nodes for r in (n.get("routes") or []) if isinstance(r, list)):
        problems.append("no node is derived from the statement alone (routes [[]]); the first steps of the "
                        "solution start from the statement")
    end = sub.get("end") or {}
    if not isinstance(end, dict):
        problems.append("end must be an object with statement and routes")
        end = {}
    if not (end.get("statement") or "").strip():
        problems.append("end has no statement")
    problems += _route_problems("END", end.get("routes"), known, allow_empty=False)
    unreachable = [nid for nid in known if nid not in reachable(sub)]
    if unreachable and not any("route" in p and "not earlier nodes" in p for p in problems):
        problems.append(f"{unreachable} lie on no derivation of END (no END route, and no node on one, uses "
                        f"them); add the route they belong to, or drop them")
    hazards = sub.get("hazards")
    if not isinstance(hazards, list):
        problems.append("hazards must be a list (possibly empty)")
        hazards = []
    for i, h in enumerate(hazards, 1):
        hid = f"H{i}"
        if not isinstance(h, dict):
            problems.append(f"hazard {i} must be an object")
            continue
        if h.get("id") != hid:
            problems.append(f"hazard {i} must have id {hid}, not {h.get('id')!r}")
        for field, limit in (("statement", C.WORDS["hazard"]), ("check", C.WORDS["hazard_check"])):
            text = h.get(field) or ""
            if not text.strip():
                problems.append(f"{hid} has no {field}")
            elif _words(text) > limit:
                problems.append(f"{hid} {field} has {_words(text)} words; at most {limit}")
    return problems


def complexity_claim(text: str) -> str | None:
    """The first phrase of text that reads as an efficiency / feasibility claim, or None."""
    m = COMPLEXITY.search(text or "")
    return m.group(0) if m else None


def warnings_of(sub: dict, statement: str) -> list[str]:
    """Advisory findings, logged but never blocking: a node without anchors, anchors absent from the statement,
    a statement that mentions none of its anchors, a statement that reads as an efficiency claim."""
    out = []
    for n in sub.get("nodes") or []:
        nid = n.get("id")
        hit = complexity_claim(n.get("statement"))
        if hit:
            out.append(f"{nid}: its statement reads as an efficiency claim ({hit!r}); efficiency belongs in the "
                       f"accept of the node it qualifies, not in a node of its own")
        anchors = [a for a in (n.get("anchors") or []) if isinstance(a, str)]
        if not anchors:
            out.append(f"{nid} has no anchors")
            continue
        if not any(_mentions(statement, a) for a in anchors):
            out.append(f"{nid}: none of its anchors {anchors} occurs in the statement")
        if not any(_mentions(n.get("statement") or "", a) for a in anchors):
            out.append(f"{nid}: its statement mentions none of its anchors {anchors}")
    return out


def prerequisites(node: dict) -> set[str]:
    """Every node that appears in one of the node's routes."""
    return {x for r in node.get("routes") or [] if isinstance(r, list) for x in r}


def ancestors(sub: dict, nid: str) -> set[str]:
    """Every node the given node depends on, through any of its routes, transitively."""
    by_id = {n.get("id"): n for n in sub.get("nodes") or []}
    out, todo = set(), list(prerequisites(by_id.get(nid) or {}))
    while todo:
        x = todo.pop()
        if x in out or x not in by_id:
            continue
        out.add(x)
        todo += list(prerequisites(by_id[x]))
    return out


def key_nodes(sub: dict, route: list) -> list[str]:
    """The route's terminal nodes: members no other member depends on. Holding them is reaching END on
    this route; the other members are the steps on the way, read for diagnosis only. A route written as
    its final construction alone and one written out in full have the same key nodes."""
    route = [x for x in route if isinstance(x, str)]
    return [n for n in route if not any(n in ancestors(sub, m) for m in route if m != n)]


def end_key_routes(sub: dict) -> list[list[str]]:
    """One list of key nodes per END route: the route's declared key node (end.keys, written by the explorer
    or the integrator; a path is a progression to it), else its terminal nodes (older graphs)."""
    end = sub.get("end") or {}
    routes, keys = end.get("routes") or [], end.get("keys") or []
    return [[keys[i]] if i < len(keys) and keys[i] else key_nodes(sub, r) for i, r in enumerate(routes)]


def reachable(sub: dict) -> set[str]:
    """The nodes on some derivation of END: END's routes' nodes and, through routes, what they use."""
    by_id = {n.get("id"): n for n in sub.get("nodes") or []}
    todo = [x for r in (sub.get("end") or {}).get("routes") or [] if isinstance(r, list) for x in r]
    seen = set()
    while todo:
        nid = todo.pop()
        if nid in seen or nid not in by_id:
            continue
        seen.add(nid)
        todo += list(prerequisites(by_id[nid]))
    return seen


def depths(sub: dict) -> dict:
    """{node: depth}: 1 for a node derived from the statement, else the smallest over its routes of one more
    than the deepest node of the route (routes point to earlier nodes, so one pass in order suffices)."""
    out = {}
    for n in sub.get("nodes") or []:
        best = None
        for r in n.get("routes") or []:
            if not isinstance(r, list) or any(x not in out for x in r):
                continue
            d = 1 + max((out[x] for x in r), default=0)
            best = d if best is None else min(best, d)
        out[n.get("id")] = best if best is not None else 1
    return out


def derive(sub: dict) -> dict:
    """The graph with each node's depth, traps defaulting to [], and hazards under code."""
    d = depths(sub)
    nodes = [{**n, "traps": n.get("traps") or [], "depth": d.get(n.get("id"), 1)} for n in sub.get("nodes") or []]
    return {**sub, "nodes": nodes, "end": sub.get("end") or {"statement": "", "routes": []},
            "hazards": sub.get("hazards") or []}


def body_of(doc: dict) -> dict:
    """What the version hashes: everything the grader and the reviewer read; not traps, depth or provenance."""
    nodes = [{k: v for k, v in n.items() if k in ("id", "name", "kind", "statement", "routes", "accept",
                                                   "anchors", "source")} for n in doc.get("nodes") or []]
    return {"solution_outline": doc.get("solution_outline", ""), "nodes": nodes, "end": doc.get("end"),
            "hazards": doc.get("hazards") or []}


def version_of(doc: dict) -> str:
    return sha256(json.dumps(body_of(doc), sort_keys=True, ensure_ascii=False))[:16]


def route_text(routes) -> str:
    return " | ".join("statement" if not r else "+".join(r) for r in routes or []) or "(none)"


def graph_text(sub: dict, traps: bool = False) -> str:
    """The graph as the reviewer and a revising builder read it."""
    out = [f"Solution outline: {(sub.get('solution_outline') or '').strip()}", ""]
    for n in sub.get("nodes") or []:
        out.append(f"{n['id']} · {n.get('name', '')} [{n.get('kind')}; source: {n.get('source')}; "
                   f"routes: {route_text(n.get('routes'))}]")
        out.append(f"  statement: {n.get('statement', '')}")
        out.append(f"  anchors: {'; '.join(n.get('anchors') or [])}")
        out.append(f"  accept: {n.get('accept', '')}")
        if traps and n.get("traps"):
            out.append(f"  traps: {' | '.join(n['traps'])}")
    end = sub.get("end") or {}
    out += ["", f"END [routes: {route_text(end.get('routes'))}]", f"  statement: {end.get('statement', '')}", ""]
    hazards = sub.get("hazards") or []
    out.append("Hazards on the edge END -> program:" if hazards else "Hazards on the edge END -> program: none")
    for h in hazards:
        out.append(f"  {h['id']}: {h.get('statement', '')} (check: {h.get('check', '')})")
    return "\n".join(out).rstrip()


def check_path(merged: dict, new_ids: list[str], end_route: list, key_node: str | None = None,
               existing_keys=()) -> list[str]:
    """What is wrong with a submitted path, beyond check_graph on the merged graph: its END route must
    name nodes; its key node (the claim that, once held, means the solution is in hand) must be one of
    them and every other node of the route must be its ancestor through routes (a path is a progression
    to its key node); every new node must lie on the derivation of the key node; and the path must add
    something (a new node, or an END route the graph does not have) with a key node no other path has."""
    problems = []
    ids = node_ids(merged)
    if not isinstance(end_route, list) or not end_route:
        return ["end_route must list the nodes of this path's complete solution"]
    bad = [x for x in end_route if x not in ids]
    if bad:
        problems.append(f"end_route names {bad}, which are not nodes")
        return problems
    if key_node is not None:
        if key_node not in ids:
            return problems + [f"key_node {key_node!r} is not a node"]
        if key_node not in end_route:
            problems.append(f"key_node {key_node} must be one of end_route's nodes")
        key = next(n for n in merged["nodes"] if n.get("id") == key_node)
        if key.get("kind") not in KEY_KINDS:
            problems.append(f"key_node {key_node} has kind {key.get('kind')!r}: the key node is the path's output "
                            f"rule, a node of kind algorithm or construction that states what the program computes "
                            f"or constructs for every input; a property, formula or proof step cannot be the key "
                            f"node, so make the node that produces the output the key, adding it if the path "
                            f"lacks one")
        hit = complexity_claim(key.get("statement"))
        if hit:
            problems.append(f"key_node {key_node}'s statement reads as a complexity or feasibility claim ({hit!r}): "
                            f"the key node states what the program computes or constructs, not that it is fast "
                            f"enough; move the efficiency into its accept, or make the construction node the key")
        anc = ancestors(merged, key_node)
        loose = [x for x in end_route if x != key_node and x not in anc]
        if loose:
            problems.append(f"{loose} are in end_route but the key node {key_node} does not depend on them, directly "
                            f"or through routes: a path is a progression to its key node, so add them to the routes "
                            f"of the nodes that need them, or leave them out of end_route")
        if key_node in existing_keys:
            problems.append(f"{key_node} is already the key node of another path: a new path ends in a claim the "
                            f"graph does not have, or it is not a new path")
        closure = anc | {key_node}
    else:
        closure = reachable({"nodes": merged["nodes"], "end": {"routes": [end_route]}})
    unused = [nid for nid in new_ids if nid not in closure]
    if unused:
        problems.append(f"new nodes {unused} lie on no derivation of this path's end_route; a new node must be a "
                        f"step of this path (used by end_route, directly or through routes), or it is not part of it")
    if not new_ids:
        others = [set(r) for r in (merged.get("end") or {}).get("routes") or []]
        if set(end_route) in others:
            problems.append("this path adds no new node and its end_route is already a route of END: it is not a "
                            "genuinely different approach")
    return problems


def probe_nodes(doc: dict) -> list[dict]:
    """What a window or program probe is shown of every node."""
    return [{"id": n["id"], "name": n.get("name"), "kind": n.get("kind"), "statement": n.get("statement"),
             "accept": n.get("accept")} for n in doc.get("nodes") or []]
