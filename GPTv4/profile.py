"""A model's profile on a problem: what its own graded runs show it holds by itself, gets wrong, and
where it stops (plan.md §2 step 2). Pure Python over the grader's records.

Held nodes (the set H_M the insight starts from): established in the run's own text in at least HELD_MIN
of the no-hint runs and left wrong in at most WRONG_MAX of them. Every other node of the chosen route is
written. Per node the profile also keeps the model's mistaken claims (distinct, with verbatim quotes) for
the writer, and its own wording where it worked on the node. The run summary counts the classes, stuck
and root nodes, tripped hazards and contradicted nodes; the behavior profile comes from behavior.py.
"""
import json
import re
from collections import Counter
from pathlib import Path

import behavior as B
import config as C
import graph as G


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def distinct_claims(records: list, nid: str, limit: int = C.TRAPS_PER_NODE, hinted_first: bool = False) -> list:
    """The model's mistaken claims on a node, distinct by normalized text, most frequent across runs first;
    each with the quote of its first occurrence."""
    seen, order = {}, []
    for r in records:
        found = set()
        for c in ((r.get("results") or {}).get(nid) or {}).get("claims") or []:
            if c.get("slip"):
                continue        # the solver's own text defeated it
            key = _normal(c.get("claim"))
            if not key or key in found:
                continue
            found.add(key)
            if key not in seen:
                seen[key] = {"claim": c.get("claim"), "quote": (c.get("quote") or "")[:400], "run": r.get("label"),
                             "where": c.get("where"), "runs": 0}
                order.append(key)
            seen[key]["runs"] += 1
    rows = sorted((seen[k] for k in order), key=lambda x: -x["runs"])
    return rows[:limit]


def wording(records: list, nid: str, limit: int = C.EVIDENCE_PER_NODE) -> list:
    """The model's own words when it held or worked on the node (established first)."""
    out = []
    for state in ("established", "working"):
        for r in records:
            for e in ((r.get("results") or {}).get(nid) or {}).get("evidence") or []:
                if e.get("state") == state and e.get("quote"):
                    out.append({"state": state, "quote": e["quote"][:300]})
                    if len(out) >= limit:
                        return out
    return out


def node_rows(graph: dict, records: list) -> dict:
    n = len(records)
    out = {}
    for node in graph["nodes"]:
        nid = node["id"]
        finals = [((r.get("results") or {}).get(nid) or {}).get("final", "absent") for r in records]
        est, wrong, working = finals.count("established"), finals.count("wrong"), finals.count("working")
        held_rate = est / n if n else 0.0
        wrong_rate = wrong / n if n else 0.0
        out[nid] = {"name": node.get("name"), "kind": node.get("kind"), "depth": node.get("depth"),
                    "runs": n, "established": est, "wrong": wrong, "working": working,
                    "absent": finals.count("absent"),
                    "wrong_any_window": sum(((r.get("results") or {}).get(nid) or {}).get("wrong", 0) > 0 for r in records),
                    "stuck": sum(r.get("stuck") == nid for r in records),
                    "root": sum(r.get("root") == nid for r in records),
                    "given": sum(nid in (r.get("given") or []) for r in records),
                    "contradicts": sum(((r.get("implemented") or {}).get(nid) or {}).get("status") == "contradicts"
                                       for r in records),
                    "held_rate": round(held_rate, 3), "wrong_rate": round(wrong_rate, 3),
                    "held": bool(n) and held_rate >= C.HELD_MIN and wrong_rate <= C.WRONG_MAX,
                    "claims": distinct_claims(records, nid), "wording": wording(records, nid)}
    return out


def run_rows(records: list) -> list:
    out = []
    for r in records:
        wrong = [nid for nid, e in (r.get("results") or {}).items() if e.get("final") == "wrong"]
        out.append({"label": r.get("label"), "run": r.get("run"), "solved": r.get("solved"), "class": r.get("class"),
                    "insight": bool(r.get("insight")), "reached_end": bool(r.get("reached_end")),
                    "stuck": r.get("stuck"), "stuck_source": r.get("stuck_source"), "root": r.get("root"),
                    "established": r.get("established") or [], "wrong": wrong, "given": r.get("given") or [],
                    "hazards_tripped": r.get("hazards_tripped") or [], "code_gap": r.get("code_gap") or [],
                    "submissions": r.get("submissions"), "stop_reason": r.get("stop_reason"),
                    "off_graph_wrong": [x.get("claim") for x in r.get("off_graph") or [] if x.get("wrong")]})
    return out


def summary(records: list) -> dict:
    fails = [r for r in records if r.get("solved") is False]
    return {"runs": len(records), "solved": sum(r.get("solved") is True for r in records), "failed": len(fails),
            "classes": dict(Counter(r.get("class") for r in records).most_common()),
            "stuck": dict(Counter(r.get("stuck") for r in fails if r.get("stuck")).most_common()),
            "root": dict(Counter(r.get("root") for r in fails if r.get("root")).most_common()),
            "hazards_tripped": dict(Counter(h for r in fails for h in r.get("hazards_tripped") or []).most_common()),
            "code_gap": dict(Counter(x for r in fails for x in r.get("code_gap") or []).most_common()),
            "end_fail": sum(bool(r.get("reached_end")) for r in fails),
            "end_fail_other": sum(str(r.get("class")) == "END+fail/other" for r in fails),
            "stalled": sum(str(r.get("class")).endswith("stalled") or (r.get("submissions") == 0) for r in fails),
            "off_graph": sum(str(r.get("class")).endswith("off_graph") for r in fails),
            "ac_routes": dict(Counter(i for r in records if r.get("solved") is True
                                      for i in r.get("end_routes_satisfied") or []))}


def build(graph: dict, records: list, model: str, traces: list | None = None) -> dict:
    """The profile of one model from its graded runs (no-hint runs for round 0)."""
    nodes = node_rows(graph, records)
    beh = B.analyze(traces) if traces else None
    return {"model": model, "problem": graph.get("problem"), "graph_version": graph.get("version"),
            "runs": len(records), "sources": sorted({r.get("group") for r in records if r.get("group")}),
            "held": [nid for nid, row in nodes.items() if row["held"]],
            "nodes": nodes, "summary": summary(records), "run_rows": run_rows(records),
            "behavior": None if beh is None else {"failed": beh["failed"], "reference": beh["reference"],
                                                   "instructions": beh["instructions"], "runs": len(beh["rows"])}}


def held_set(profile: dict) -> set:
    return set(profile.get("held") or [])


def save(profile: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def text(profile: dict, graph: dict) -> str:
    """The profile as a short table for the log."""
    s = profile["summary"]
    lines = [f"{profile['model']} on {profile['problem']}: {profile['runs']} graded runs, {s['solved']} solved; "
             f"held by itself: {', '.join(profile['held']) or 'none'}",
             f"classes: {s['classes']}", f"stuck: {s['stuck']}  root: {s['root']}",
             "| node | depth | held | wrong | working | absent | stuck | root | claims |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for nid, row in profile["nodes"].items():
        lines.append(f"| {nid} {row['name']} | {row['depth']} | {row['established']}{'*' if row['held'] else ''} | "
                     f"{row['wrong']} | {row['working']} | {row['absent']} | {row['stuck']} | {row['root']} | {len(row['claims'])} |")
    return "\n".join(lines)
