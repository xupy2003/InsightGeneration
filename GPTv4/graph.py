"""The reasoning graph of a problem: ReasoningGraph/graph/graphs/<slug>/graph.json (built by its explorer
from the statement alone; the editorial's approach added as a path when it was missing), and what the
engine reads off it. The structural helpers are copies of ReasoningGraph/graph/rules.py's (the repository
convention: copy, do not import across directories). No model calls; `ensure` runs the explorer as a
subprocess when a problem has no graph yet.
"""
import json
import logging
import subprocess
import sys
from pathlib import Path

import config as C
from adapters.problems import slug_of

log = logging.getLogger("gptv4.graph")


def graph_dir(problem: str) -> Path:
    return C.REASONING_GRAPH / "graph" / "graphs" / slug_of(problem)


def graph_path(problem: str) -> Path:
    return graph_dir(problem) / "graph.json"


def load(problem: str) -> dict:
    doc = json.loads(graph_path(problem).read_text(encoding="utf-8"))
    d = depths(doc)
    for n in doc["nodes"]:
        n.setdefault("depth", d[n["id"]])
        n.setdefault("traps", [])
    return doc


def ensure(problem: str, dry: bool = False) -> dict:
    """The graph, built by ReasoningGraph's explorer when there is none (one long API session with the
    judge; 20 min to 2 h). dry: do not build, raise if missing."""
    if not graph_path(problem).exists():
        if dry:
            raise FileNotFoundError(f"{problem}: no graph at {graph_path(problem)}")
        log.info(f"{problem}: no graph yet; running the explorer")
        cmd = [sys.executable, "graph/explore.py", "--problems", problem]
        done = subprocess.run(cmd, cwd=C.REASONING_GRAPH, capture_output=True, text=True)
        if done.returncode or not graph_path(problem).exists():
            raise RuntimeError(f"{problem}: the explorer failed ({done.returncode}): {done.stderr[-1500:]}")
    doc = load(problem)
    if doc.get("status") not in ("accepted", "flagged"):
        log.warning(f"{problem}: graph status is {doc.get('status')}")
    return doc


# --- structure (copies of ReasoningGraph/graph/rules.py)

def by_id(graph: dict) -> dict:
    return {n["id"]: n for n in graph.get("nodes") or []}


def prerequisites(node: dict) -> set:
    return {x for r in node.get("routes") or [] if isinstance(r, list) for x in r}


def ancestors(graph: dict, nid: str) -> set:
    nodes = by_id(graph)
    out, todo = set(), list(prerequisites(nodes.get(nid) or {}))
    while todo:
        x = todo.pop()
        if x in out or x not in nodes:
            continue
        out.add(x)
        todo += list(prerequisites(nodes[x]))
    return out


def depths(graph: dict) -> dict:
    out = {}
    for n in graph.get("nodes") or []:
        best = None
        for r in n.get("routes") or []:
            if not isinstance(r, list) or any(x not in out for x in r):
                continue
            d = 1 + max((out[x] for x in r), default=0)
            best = d if best is None else min(best, d)
        out[n["id"]] = best if best is not None else 1
    return out


def index(graph: dict, nid: str) -> int:
    return next(i for i, n in enumerate(graph["nodes"]) if n["id"] == nid)


def in_order(graph: dict, ids) -> list:
    """ids in the graph's order (ids are topological: routes point to earlier nodes)."""
    pos = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    return sorted(set(ids) & set(pos), key=pos.get)


def key_nodes(graph: dict, route: list) -> list:
    """The route's terminal nodes, for a graph without end.keys."""
    route = [x for x in route if isinstance(x, str)]
    return [n for n in route if not any(n in ancestors(graph, m) for m in route if m != n)]


def end_routes(graph: dict) -> list:
    """[{index (1-based, as the grader numbers them), nodes, key, source}] for every END route; key = the
    explorer's declared key node (end.keys), else the route's terminal node."""
    end = graph.get("end") or {}
    routes, keys = end.get("routes") or [], end.get("keys") or []
    paths = graph.get("paths") or []
    out = []
    for i, route in enumerate(routes):
        key = keys[i] if i < len(keys) and keys[i] else (key_nodes(graph, route) or [None])[-1]
        path = next((p for p in paths if set(p.get("end_route") or []) == set(route)), None)
        out.append({"index": i + 1, "nodes": in_order(graph, route), "key": key,
                    "source": (path or {}).get("source") or ("editorial" if (path or {}).get("program") is None and path else None),
                    "path": (path or {}).get("id"), "program": (path or {}).get("program"),
                    "approach": (path or {}).get("approach")})
    return out


def route_program(graph: dict, problem: str, route: dict) -> str | None:
    """The accepted program of the route's path (paths/P<k>.cpp beside graph.json), or None."""
    rel = route.get("program")
    if not rel:
        return None
    path = graph_dir(problem) / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def hazards(graph: dict) -> list:
    return graph.get("hazards") or []


def hazard(graph: dict, hid: str) -> dict | None:
    return next((h for h in hazards(graph) if h.get("id") == hid), None)


def node_text(node: dict) -> dict:
    """What a writer is shown of a node: no ids beyond its own, no provenance."""
    return {"name": node.get("name"), "kind": node.get("kind"), "statement": node.get("statement"),
            "accept": node.get("accept")}


def text(graph: dict) -> str:
    """The graph as a reader sees it (for logs and the report)."""
    out = [f"Solution outline: {(graph.get('solution_outline') or '').strip()}", ""]
    for n in graph.get("nodes") or []:
        routes = " | ".join("statement" if not r else "+".join(r) for r in n.get("routes") or []) or "(none)"
        out.append(f"{n['id']} · {n.get('name', '')} [{n.get('kind')}; routes: {routes}; depth {n.get('depth')}]")
        out.append(f"  statement: {n.get('statement', '')}")
        out.append(f"  accept: {n.get('accept', '')}")
    for r in end_routes(graph):
        out.append(f"END route {r['index']}: {'+'.join(r['nodes'])} (key {r['key']}"
                   f"{', ' + r['source'] if r.get('source') else ''})")
    for h in hazards(graph):
        out.append(f"{h['id']}: {h.get('statement', '')} (check: {h.get('check', '')})")
    return "\n".join(out).rstrip()
