"""Node states over a run's checkpoints, and what the graph makes of them: whether END was reached,
which established nodes have no established prerequisites (unsupported), the frontier (nodes whose
prerequisites are all held), the stuck node, the roots of what is wrong, and the run's class
(design.md §2.3). Pure Python, no model calls.

A checkpoint is one probed window or program, {id, kind, rounds, rows}; rows are the probe's rows,
{node_id, state, quote, solver_claim, where}. Checkpoints come in time order.

Since 2026-11-03 the node states come from the windows alone, i.e. from what the solver wrote. A program
checkpoint feeds `implemented` (how the program stands to each node) and the hazards, never a node's
state. held = the nodes the run established in its text. The hint's `given` nodes are recorded and serve
as prerequisites (support = held | given) for the frontier and for unsupported, but do not count toward
END. END on a route = its key node held and no node of the route left wrong: a skipped step is fine, a
wrong one is not. derived = the whole route held (reported, not required).
"""
from collections import defaultdict

from graph import rules as R

STATES = ("established", "wrong", "working", "absent")
SYMBOL = {"established": "+", "wrong": "x", "working": "~", "absent": "."}
PROGRAM_STATE = {"holds": "established", "contradicts": "wrong", "not_needed": "absent"}
PROGRAM_STATUS = {v: k for k, v in PROGRAM_STATE.items()}
RANK = {"wrong": 3, "established": 2, "working": 1, "absent": 0}


def is_program(cp: dict) -> bool:
    return cp.get("kind") == "program"


def node_states(graph: dict, checkpoints: list[dict]) -> dict:
    """{node: {trajectory, final, established, wrong, working, claims, evidence}} from the window
    checkpoints (program checkpoints are skipped). At one checkpoint wrong beats established beats working;
    the final state is the last one that is not absent. claims are the wrong rows (the solver's mistaken
    beliefs with quotes), evidence the established and working rows."""
    order = [n["id"] for n in graph["nodes"]]
    results = {nid: {"trajectory": "", "final": "absent", "established": 0, "wrong": 0, "working": 0,
                     "claims": [], "evidence": []} for nid in order}
    for cp in checkpoints:
        if is_program(cp):
            continue
        rows = defaultdict(list)
        for row in cp["rows"]:
            if row["state"] != "absent" and row["node_id"] in results:
                rows[row["node_id"]].append(row)
        for nid in order:
            state = max((r["state"] for r in rows[nid]), key=RANK.get, default="absent")
            entry = results[nid]
            entry["trajectory"] += SYMBOL[state]
            if state == "absent":
                continue
            entry["final"] = state
            entry[state] += 1
            for r in rows[nid]:
                item = {"checkpoint": cp["id"], "kind": cp.get("kind"), "rounds": cp.get("rounds"),
                        "where": r.get("where"), "state": r["state"], "claim": r.get("solver_claim"),
                        "quote": r.get("quote")}
                (entry["claims"] if r["state"] == "wrong" else entry["evidence"]).append(item)
    return results


def apply_adjudications(results: dict, adjudications: dict | None) -> dict:
    """The second reading of the nodes the windows left wrong (grade.py's adjudication stage): the node's
    final comes from it, the window fold's final is kept as window_final, and the claims it lists as slips
    are marked. adjudications: {node: {final, basis, slips: [{where, why}], reason}}."""
    for nid, ans in (adjudications or {}).items():
        if nid not in results or not isinstance(ans, dict) or ans.get("final") not in STATES:
            continue
        e = results[nid]
        e["window_final"] = e["final"]
        e["final"] = ans["final"]
        slips = {s["where"]: s.get("why") for s in ans.get("slips") or [] if isinstance(s, dict)}
        for c in e["claims"]:
            if c.get("where") in slips:
                c["slip"] = slips[c["where"]]
        e["adjudication"] = {"final": ans["final"], "basis": ans.get("basis"), "slips": ans.get("slips") or [],
                             "reason": ans.get("reason")}
    return results


def implemented_of(graph: dict, checkpoints: list[dict]) -> dict:
    """{node: {status, quote, reason, program}} from the last program checkpoint (the final program when it
    was read): holds / contradicts / not_needed. {} when no program was read."""
    progs = [cp for cp in checkpoints if is_program(cp)]
    if not progs:
        return {}
    last = next((cp for cp in reversed(progs) if cp.get("role") == "final"), progs[-1])
    out = {}
    for row in last.get("rows") or []:
        status = row.get("status") or PROGRAM_STATUS.get(row.get("state"), "not_needed")
        out[row["node_id"]] = {"status": status, "quote": row.get("quote"), "reason": row.get("solver_claim"),
                               "program": last["id"]}
    for n in graph["nodes"]:
        out.setdefault(n["id"], {"status": "not_needed", "quote": None, "reason": None, "program": last["id"]})
    return out


def satisfied(route, held) -> bool:
    return all(x in held for x in route)


def supported(node: dict, held) -> bool:
    """Some route of the node lies in held ([] = from the statement: always supported)."""
    return any(satisfied(r, held) for r in node.get("routes") or [])


def end_status(graph: dict, held, wrong=()) -> list[dict]:
    """One entry per END route: its key node(s), whether it is reached (key held, nothing on the route left
    wrong), whether it is derived (the whole route held), and the route's nodes left wrong."""
    wrong = set(wrong)
    out = []
    routes = (graph.get("end") or {}).get("routes") or []
    for i, (keys, route) in enumerate(zip(R.end_key_routes(graph), routes), 1):
        bad = [x for x in route if x in wrong]
        out.append({"route": i, "keys": keys, "reached": satisfied(keys, held) and not bad,
                    "derived": satisfied(route, held), "wrong": bad})
    return out


def end_routes_satisfied(graph: dict, held, wrong=()) -> list[int]:
    """The END routes reached: key nodes held and no node of the route left wrong."""
    return [e["route"] for e in end_status(graph, held, wrong) if e["reached"]]


def unsupported(graph: dict, held, given=(), support=None) -> list[str]:
    """Held nodes (not given) with no route in support (default: held): established without their
    prerequisites. For a hinted run support = held | given, so a node built on given prerequisites is
    not unsupported."""
    support = held if support is None else support
    return [n["id"] for n in graph["nodes"]
            if n["id"] in held and n["id"] not in given and not supported(n, support)]


def frontier(graph: dict, held, support=None) -> list[str]:
    """Nodes not held whose some route is in support (default: held): what the solver could do next. A
    node the hint states but the run has not established itself is on the frontier."""
    support = held if support is None else support
    return [n["id"] for n in graph["nodes"] if n["id"] not in held and supported(n, support)]


def stuck_node(graph: dict, results: dict, held, support=None) -> tuple[str | None, str | None]:
    """(node, source). The frontier node with the most evidence of trouble (wrong counts double, then
    working), source "frontier"; when no frontier node was touched, the root of what is wrong (the solver
    worked beyond the frontier), source "root"; (None, None) when the run never engaged the graph."""
    front = frontier(graph, held, support)
    scored = [(2 * results[nid]["wrong"] + results[nid]["working"], nid) for nid in front]
    scored = [(s, nid) for s, nid in scored if s > 0]
    depth = {n["id"]: n.get("depth", 1) for n in graph["nodes"]}
    if scored:
        return max(scored, key=lambda x: (x[0], -depth[x[1]], -graph_index(graph, x[1])))[1], "frontier"
    root = root_node(graph, results)
    return (root, "root") if root else (None, None)


def graph_index(graph: dict, nid: str) -> int:
    return next(i for i, n in enumerate(graph["nodes"]) if n["id"] == nid)


def roots(graph: dict, results: dict) -> list[str]:
    """Nodes left wrong none of whose prerequisites (over all routes) is left wrong."""
    wrong = {nid for nid, e in results.items() if e["final"] == "wrong"}
    out = []
    for n in graph["nodes"]:
        if n["id"] in wrong:
            prereq = {x for r in n.get("routes") or [] for x in r}
            if not prereq & wrong:
                out.append(n["id"])
    return out


def root_node(graph: dict, results: dict) -> str | None:
    """The shallowest root; among equals, the one shown wrong most often."""
    rs = roots(graph, results)
    if not rs:
        return None
    depth = {n["id"]: n.get("depth", 1) for n in graph["nodes"]}
    return min(rs, key=lambda nid: (depth[nid], -results[nid]["wrong"], graph_index(graph, nid)))


def code_gap(implemented: dict, ends: list[dict]) -> list[str]:
    """Nodes of a reached END route that the final program contradicts: where a right idea went wrong in
    code (diagnosis of END+fail; the class does not depend on it)."""
    on_routes = {x for e in ends if e["reached"] for x in (e.get("nodes") or [])}
    return [nid for nid in on_routes if (implemented.get(nid) or {}).get("status") == "contradicts"]


def classify(solved, reached: bool, tripped: list[str], stuck: str | None, off_graph: bool = False) -> str:
    if reached:
        if solved:
            return "END+AC"
        return f"END+fail/hazard:{','.join(tripped)}" if tripped else "END+fail/other"
    if solved:
        return "noEND+AC"
    if stuck:
        return f"noEND+fail/stuck:{stuck}"
    return "noEND+fail/off_graph" if off_graph else "noEND+fail/stalled"


def summarize(graph: dict, checkpoints: list[dict], given, solved, tripped: list[str], off_graph=None,
              adjudications=None) -> dict:
    """Everything the grader records about one run from its checkpoints. Node states and END come from the
    windows alone; the programs give `implemented` and (through tripped) the hazards; given nodes are
    prerequisites (support) for the frontier and unsupported. off_graph: the windows' off-graph claims.
    adjudications: the second reading of the nodes the windows left wrong (apply_adjudications)."""
    results = apply_adjudications(node_states(graph, checkpoints), adjudications)
    held = {nid for nid, e in results.items() if e["final"] == "established"}
    wrong = {nid for nid, e in results.items() if e["final"] == "wrong"}
    support = held | set(given)
    routes = (graph.get("end") or {}).get("routes") or []
    ends = [dict(e, nodes=list(routes[e["route"] - 1])) for e in end_status(graph, held, wrong)]
    reached = [e["route"] for e in ends if e["reached"]]
    derived = [e["route"] for e in ends if e["derived"]]
    stuck, source = stuck_node(graph, results, held, support)
    implemented = implemented_of(graph, checkpoints)
    off_graph = list(off_graph or [])
    off_wrong = any(x.get("wrong") for x in off_graph)
    return {"results": results, "given": sorted(given, key=lambda x: graph_index(graph, x)),
            "established": sorted(held, key=lambda x: graph_index(graph, x)),
            "reached_end": bool(reached), "end_routes_satisfied": reached,
            "derived_end": bool(derived), "end_routes_derived": derived, "end_routes": ends,
            "unsupported": unsupported(graph, held, given, support), "frontier": frontier(graph, held, support),
            "stuck": stuck, "stuck_source": source, "roots": roots(graph, results),
            "root": root_node(graph, results),
            "implemented": implemented, "code_gap": code_gap(implemented, ends),
            "hazards_tripped": tripped, "off_graph": off_graph,
            "adjudicated": {nid: e["adjudication"]["final"] for nid, e in results.items() if "adjudication" in e},
            "class": classify(solved, bool(reached), tripped, stuck, off_wrong)}
