"""A toy graph and synthetic grader records for the offline tests."""
import copy

GRAPH = {
    "schema": "reasoning-graph-v2", "problem": "2099/X-toy", "title": "Toy", "status": "accepted", "version": "toy1",
    "solution_outline": "Model the thing, derive the bound, construct the answer.",
    "nodes": [
        {"id": "N1", "name": "Model the objects", "kind": "modeling", "statement": "Each object has a weight w and a bound b.",
         "routes": [[]], "accept": "Any equivalent formulation.", "anchors": ["object"], "source": "exploration"},
        {"id": "N2", "name": "The bound", "kind": "key_property", "statement": "The answer never exceeds the sum of weights.",
         "routes": [["N1"]], "accept": "Any proof.", "anchors": ["weights"], "source": "exploration"},
        {"id": "N3", "name": "Greedy construction", "kind": "construction", "statement": "Take objects by decreasing weight while the bound allows.",
         "routes": [["N2"]], "accept": "The greedy order.", "anchors": ["weight"], "source": "exploration"},
        {"id": "N4", "name": "DP construction", "kind": "algorithm", "statement": "A knapsack DP over the bound gives the answer.",
         "routes": [["N1"]], "accept": "Any DP over the bound.", "anchors": ["bound"], "source": "editorial"},
    ],
    "end": {"statement": "...", "routes": [["N1", "N2", "N3"], ["N1", "N4"]], "keys": ["N3", "N4"]},
    "hazards": [{"id": "H1", "statement": "Weights sum beyond 32 bits.", "check": "64-bit sums."}],
    "paths": [{"id": "P1", "approach": "greedy", "end_route": ["N1", "N2", "N3"], "key_node": "N3", "program": None},
              {"id": "P2", "approach": "dp", "end_route": ["N1", "N4"], "key_node": "N4", "program": None, "source": "editorial"}],
}


def record(label, model, solved, states: dict, stuck=None, root=None, reached_end=False, given=(), insight=False,
           hazards=(), code_gap=(), cls=None, trace=None, run=1, claims=None, implemented=None, submissions=3):
    """A grader record with the node finals given (missing nodes absent)."""
    results = {}
    for n in GRAPH["nodes"]:
        nid = n["id"]
        st = states.get(nid, "absent")
        entry = {"trajectory": {"established": "+", "wrong": "x", "working": "~", "absent": "."}[st], "final": st,
                 "established": int(st == "established"), "wrong": int(st == "wrong"), "working": int(st == "working"),
                 "claims": [], "evidence": []}
        if st == "wrong":
            entry["claims"] = [{"checkpoint": "R1W01", "where": "R1W01", "state": "wrong",
                                "claim": (claims or {}).get(nid, f"mistaken {nid} by {model}"),
                                "quote": f"quote of {nid} in {label}"}]
        elif st in ("established", "working"):
            entry["evidence"] = [{"state": st, "quote": f"{model} wording on {nid}"}]
        results[nid] = entry
    held = [nid for nid, st in states.items() if st == "established"]
    if cls is None:
        cls = "END+AC" if solved and reached_end else "noEND+AC" if solved else (
            f"noEND+fail/stuck:{stuck}" if stuck else ("END+fail/hazard:" + ",".join(hazards) if reached_end and hazards
                                                       else "END+fail/other" if reached_end else "noEND+fail/stalled"))
    return {"label": label, "group": "/".join(label.split("/")[:-1]), "model": model, "run": run, "trace": trace,
            "solved": solved, "insight": insight, "submissions": submissions, "results": results,
            "given": list(given), "established": held, "reached_end": reached_end,
            "end_routes_satisfied": [1] if reached_end else [], "frontier": [], "stuck": stuck,
            "stuck_source": "frontier" if stuck else None, "root": root or stuck,
            "implemented": implemented or {}, "code_gap": list(code_gap), "hazards_tripped": list(hazards),
            "off_graph": [], "class": cls,
            "programs": [{"id": 1, "role": "final", "verdict": "WA",
                          "hazards": [{"hazard_id": h, "status": "tripped", "quote": "int s = 0;"} for h in hazards]}]}


def baseline_records(model="qwen", n=5):
    """Five failed no-hint runs: N1 held, stuck at N2 (wrong)."""
    return [record(f"pool/{model}/baseline/run{i}", model, False, {"N1": "established", "N2": "wrong"}, stuck="N2",
                   run=i, trace=None) for i in range(1, n + 1)]


def graph():
    return copy.deepcopy(GRAPH)
