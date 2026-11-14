"""Validate a graph from graded runs (design.md §3): soundness (accepted runs reach END), discrimination
(failed runs do not, or trip a hazard), localization (where failed runs get stuck), grader agreement
between two gradings, per-node statistics, and the merge / split / missing-route suggestions that go
back to the builder. Offline, no model calls.

    python3 validate.py --graph graph/graphs/<slug>/graph.json \\
        --runs grade/runs/<slug>/baseline/runs.jsonl [grade/runs/<slug>/editorial/runs.jsonl ...] \\
        --out validate/reports/<slug> [--compare OTHER/runs.jsonl] [--apply-traps]

Writes report.md, report.json and feedback.json (what build.py --revise-from reads) under --out.
--apply-traps writes the mistaken beliefs seen at each node into the graph's `traps` (graph.json; the
version does not change, traps are grading data).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VER2 = Path(__file__).resolve().parents[1]
if str(VER2) not in sys.path:
    sys.path.insert(0, str(VER2))
import config as C  # noqa: E402
from grade import closure as Cl  # noqa: E402
from graph import rules as R  # noqa: E402

MERGE_MIN_RUNS = 3        # runs holding a node's prerequisites before "always held with them" means anything
MERGE_RATE = 0.9
SPLIT_MIN_STUCK = 2       # runs stuck at a node before its distinct mistaken beliefs suggest a split
OFF_GRAPH_LIMIT = 20      # off-graph claims kept in feedback.json (most frequent first)
UNUSED_MIN_AC = 3         # accepted runs before "never held in an accepted run" means anything
TRAPS_PER_NODE = 5


def load_runs(paths) -> list[dict]:
    out = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                rec["_source"] = str(p)
                out.append(rec)
    return out


def _share(num, den):
    return round(num / den, 3) if den else None


def metrics(records: list[dict]) -> dict:
    """The validation metrics. soundness is measured on the accepted runs WITHOUT a hint only: a run that
    solved the problem by itself must have the solution's idea in its text, so a miss is the graph's or the
    grader's. Accepted runs with a hint are reported apart (hinted_ac_end and recipe_rate): a hinted run
    that passes without establishing a key node itself was carried by the hint."""
    ac = [r for r in records if r["solved"] is True]
    fail = [r for r in records if r["solved"] is False]
    ac_nohint = [r for r in ac if not r.get("insight")]
    ac_hint = [r for r in ac if r.get("insight")]
    sound = [r for r in ac_nohint if r["reached_end"]]
    hinted_end = [r for r in ac_hint if r["reached_end"]]
    discriminated = [r for r in fail if not r["reached_end"] or r["hazards_tripped"]]
    residual = [r for r in fail if r["reached_end"] and not r["hazards_tripped"]]
    stalled = [r for r in fail if r["class"].endswith("stalled")]
    off_graph = [r for r in fail if r["class"].endswith("off_graph")]
    localization = {}
    for key in sorted({(r["model"], r["condition"]) for r in fail}):
        group = [r for r in fail if (r["model"], r["condition"]) == key]
        stuck = Counter(r["stuck"] for r in group if r["stuck"])
        top = stuck.most_common(1)[0] if stuck else (None, 0)
        localization["/".join(key)] = {"failed": len(group), "stuck": dict(stuck.most_common()),
                                       "top": top[0], "top_share": _share(top[1], len(group)),
                                       "distinct": len(stuck), "stalled": sum(not r["stuck"] for r in group)}
    return {"runs": len(records), "ac": len(ac), "fail": len(fail),
            "ac_nohint": len(ac_nohint), "ac_hint": len(ac_hint),
            "soundness": _share(len(sound), len(ac_nohint)), "soundness_n": f"{len(sound)}/{len(ac_nohint)}",
            "hinted_ac_end": _share(len(hinted_end), len(ac_hint)),
            "hinted_ac_end_n": f"{len(hinted_end)}/{len(ac_hint)}",
            "recipe_rate": _share(len(ac_hint) - len(hinted_end), len(ac_hint)),
            "derived_nohint_ac": _share(sum(bool(r.get("derived_end")) for r in ac_nohint), len(ac_nohint)),
            "derived_hint_ac": _share(sum(bool(r.get("derived_end")) for r in ac_hint), len(ac_hint)),
            "discrimination": _share(len(discriminated), len(fail)),
            "discrimination_n": f"{len(discriminated)}/{len(fail)}",
            "residual_end_fail_other": _share(len(residual), len(fail)), "stalled": _share(len(stalled), len(fail)),
            "off_graph": _share(len(off_graph), len(fail)),
            "unsound_runs": [r["label"] for r in ac_nohint if not r["reached_end"]],
            "recipe_runs": [r["label"] for r in ac_hint if not r["reached_end"]],
            "residual_runs": [r["label"] for r in residual],
            "classes": dict(Counter(r["class"] for r in records).most_common()), "localization": localization}

def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def node_stats(records: list[dict], graph: dict) -> dict:
    ac = [r for r in records if r["solved"] is True]
    fail = [r for r in records if r["solved"] is False]
    no_hint = [r for r in records if not r["given"]]
    out = {}
    for n in graph["nodes"]:
        nid = n["id"]
        prereq_held = [r for r in records if n.get("routes") and Cl.supported(n, set(r["established"]) - {nid})
                       and any(r_ for r_ in n["routes"])]
        held_with = [r for r in prereq_held if nid in r["established"]]
        claims = {}
        for r in records:
            for c in r["results"][nid]["claims"]:
                key = _normal(c["claim"])
                if key and key not in claims:
                    claims[key] = {"claim": c["claim"], "run": r["label"], "quote": c["quote"]}
        out[nid] = {"name": n["name"], "depth": n.get("depth"),
                    "held_ac": sum(nid in r["established"] for r in ac),
                    "held_fail": sum(nid in r["established"] for r in fail),
                    "given": sum(nid in r["given"] for r in records),
                    "wrong_runs": sum(r["results"][nid]["wrong"] > 0 for r in records),
                    "working_runs": sum(r["results"][nid]["working"] > 0 for r in records),
                    "stuck_runs": sum(r["stuck"] == nid for r in records),
                    "root_runs": sum(r["root"] == nid for r in records),
                    "unsupported_no_hint": sum(nid in r["unsupported"] for r in no_hint),
                    "prereq_held_runs": len(prereq_held), "held_with_prereq": len(held_with),
                    "held_given_prereq": _share(len(held_with), len(prereq_held)),
                    "implemented_contradicts": sum((r.get("implemented") or {}).get(nid, {}).get("status")
                                                  == "contradicts" for r in records),
                    "distinct_claims": len(claims), "claims": list(claims.values())}
    return out


def off_graph_claims(records: list[dict], limit: int = OFF_GRAPH_LIMIT) -> list[dict]:
    """The windows' off-graph claims over all runs, grouped by normalized text, most frequent first (wrong
    ones before steps): candidates for new nodes (steps the graph lacks) or traps (mistaken beliefs no node
    covers)."""
    groups = {}
    for r in records:
        for x in r.get("off_graph") or []:
            key = _normal(x.get("claim"))
            if not key:
                continue
            g = groups.setdefault(key, {"claim": x.get("claim"), "wrong": bool(x.get("wrong")), "runs": set(),
                                        "example": {"run": r["label"], "where": x.get("where"),
                                                    "quote": x.get("quote")}})
            g["runs"].add(r["label"])
    out = [dict(g, runs=len(g["runs"])) for g in groups.values()]
    out.sort(key=lambda g: (-g["runs"], not g["wrong"], g["claim"]))
    return out[:limit]


def suggestions(records: list[dict], graph: dict, stats: dict) -> tuple[list[str], list[str], dict, list[dict]]:
    """(blocking, advisory, traps, off_graph) for the builder: accepted no-hint runs no END route covers
    (missing routes: blocking), accepted hinted runs the hint carried (advisory), nodes to merge (always held
    with their prerequisites, never a stuck point), nodes to split (a stuck point with several distinct
    mistaken beliefs), routes nobody walks, off-graph claims seen in several runs; the beliefs as traps and
    the off-graph claims as candidates."""
    blocking, advisory, traps = [], [], {}
    by_id = {n["id"]: n for n in graph["nodes"]}
    ac = [r for r in records if r["solved"] is True]
    for r in ac:
        if r["reached_end"]:
            continue
        held = set(r["established"])
        detail = "; ".join(f"key nodes {' + '.join(route)} miss {', '.join(x for x in route if x not in held)}"
                           for route in R.end_key_routes(graph))
        bad = [e for e in r.get("end_routes") or [] if e.get("wrong")]
        if bad:
            detail += "; " + "; ".join(f"route {e['route']} has {', '.join(e['wrong'])} wrong" for e in bad)
        prog = ", ".join(f"#{p['id']} {p['role']}" for p in r.get("programs") or []) or "none"
        if r.get("insight"):
            advisory.append(f"hint-carried run {r['label']}: accepted with a hint, but its text holds "
                            f"{', '.join(r['established']) or 'no node'} (given: {', '.join(r['given']) or 'none'}) "
                            f"and satisfies no END route ({detail}): the hint supplied the solution without the "
                            f"understanding")
        else:
            blocking.append(f"accepted run {r['label']} holds {', '.join(r['established']) or 'no node'} but "
                            f"satisfies no END route ({detail}); programs read: {prog}. Either a route is missing, "
                            f"or a node it bypasses is stated too narrowly, or the grader missed it: read the run "
                            f"before changing the graph")
    for nid, s in stats.items():
        n = by_id[nid]
        if (s["prereq_held_runs"] >= MERGE_MIN_RUNS and s["held_given_prereq"] is not None
                and s["held_given_prereq"] >= MERGE_RATE and s["stuck_runs"] == 0 and s["wrong_runs"] == 0):
            advisory.append(f"merge {nid} ({n['name']}) into its prerequisites: held in {s['held_with_prereq']} of "
                            f"{s['prereq_held_runs']} runs that hold a route of it, never a stuck point, never wrong")
        if s["unsupported_no_hint"] >= MERGE_MIN_RUNS:
            advisory.append(f"{nid} ({n['name']}) is held without any route of it in {s['unsupported_no_hint']} "
                            f"runs without a hint: solvers do not take its prerequisites as a separate step; merge "
                            f"it with them, or its routes are wrong")
        if s["stuck_runs"] >= SPLIT_MIN_STUCK and s["distinct_claims"] >= 2:
            beliefs = " | ".join(c["claim"] for c in s["claims"][:TRAPS_PER_NODE])
            advisory.append(f"split {nid} ({n['name']})? stuck point of {s['stuck_runs']} runs with "
                            f"{s['distinct_claims']} distinct mistaken beliefs: {beliefs}")
        if len(ac) >= UNUSED_MIN_AC and s["held_ac"] == 0 and s["given"] == 0:
            advisory.append(f"{nid} ({n['name']}) is held in none of {len(ac)} accepted runs: a route nobody walks "
                            f"(keep it if the editorial's, else consider dropping it)")
        if s["claims"]:
            traps[nid] = [c["claim"] for c in s["claims"][:TRAPS_PER_NODE]]
    off = off_graph_claims(records)
    for c in off:
        if c["runs"] >= 2:
            advisory.append(f"off-graph {'mistaken belief' if c['wrong'] else 'step'} in {c['runs']} runs "
                            f"(a node or a trap the graph lacks?): {c['claim']}")
    return blocking, advisory, traps, off

def agreement(a: list[dict], b: list[dict], graph: dict) -> dict | None:
    """How two gradings of the same runs agree: per node-state, per stuck node, per reached_end."""
    by_label = {r["label"]: r for r in b}
    pairs = [(r, by_label[r["label"]]) for r in a if r["label"] in by_label]
    if not pairs:
        return None
    states = [(r["results"][n["id"]]["final"], s["results"][n["id"]]["final"])
              for r, s in pairs for n in graph["nodes"]]
    same = sum(x == y for x, y in states)
    non_absent = [(x, y) for x, y in states if x != "absent" or y != "absent"]
    return {"runs": len(pairs), "node_states": _share(same, len(states)),
            "node_states_non_absent": _share(sum(x == y for x, y in non_absent), len(non_absent)),
            "stuck": _share(sum(r["stuck"] == s["stuck"] for r, s in pairs), len(pairs)),
            "reached_end": _share(sum(r["reached_end"] == s["reached_end"] for r, s in pairs), len(pairs)),
            "class": _share(sum(r["class"] == s["class"] for r, s in pairs), len(pairs))}


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(doc: dict, graph: dict) -> str:
    m = doc["metrics"]
    lines = [f"# Validation: {graph.get('title')} ({graph.get('problem')}, graph {graph.get('version')})", "",
             f"{m['runs']} runs: {m['ac']} accepted ({m['ac_nohint']} without a hint, {m['ac_hint']} with one), "
             f"{m['fail']} failed. Node states come from the runs' text; END = a key node held and nothing on its "
             f"route wrong.", "",
             "| metric | value | meaning |", "|---|---|---|",
             f"| soundness | {m['soundness']} ({m['soundness_n']}) | accepted runs WITHOUT a hint that reach END "
             f"(target ≥ 0.9; a miss is the graph's or the grader's) |",
             f"| hinted AC reaching END | {m['hinted_ac_end']} ({m['hinted_ac_end_n']}) | accepted runs with a hint "
             f"whose own text establishes a key node; recipe rate {m['recipe_rate']} = carried by the hint |",
             f"| derived | {m['derived_nohint_ac']} / {m['derived_hint_ac']} | accepted runs (no hint / hint) whose "
             f"text holds a whole END route |",
             f"| discrimination | {m['discrimination']} ({m['discrimination_n']}) | failed runs that do not reach END, "
             f"or trip a hazard (target ≥ 0.8) |",
             f"| END+fail/other | {m['residual_end_fail_other']} | failed runs with the idea but no named hazard: "
             f"the implementation residual |",
             f"| stalled / off_graph | {m['stalled']} / {m['off_graph']} | failed runs that engaged no node / that "
             f"only stated claims no node covers |", "",
             "## Classes", "", "| class | runs |", "|---|---:|"]
    lines += [f"| {cls} | {n} |" for cls, n in m["classes"].items()]
    lines += ["", "## Localization (failed runs)", "",
              "| model/condition | failed | stuck nodes | top | top share | distinct | stalled |",
              "|---|---:|---|---|---:|---:|---:|"]
    for key, loc in m["localization"].items():
        stuck = ", ".join(f"{k} ×{v}" for k, v in loc["stuck"].items()) or "-"
        lines.append(f"| {key} | {loc['failed']} | {stuck} | {loc['top'] or '-'} | {loc['top_share']} | "
                     f"{loc['distinct']} | {loc['stalled']} |")
    if doc.get("agreement"):
        a = doc["agreement"]
        lines += ["", "## Grader agreement (--compare)", "",
                  f"{a['runs']} runs graded twice: node states agree {a['node_states']} (non-absent "
                  f"{a['node_states_non_absent']}), stuck node {a['stuck']}, reached END {a['reached_end']}, "
                  f"class {a['class']}."]
    lines += ["", "## Nodes", "",
              "| node | depth | name | held AC | held fail | given | wrong | working | stuck | root | unsupported "
              "(no hint) | held given prereq | distinct beliefs | code contradicts |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    for nid, s in doc["nodes"].items():
        lines.append(f"| {nid} | {s['depth']} | {_cell(s['name'])} | {s['held_ac']}/{m['ac']} | "
                     f"{s['held_fail']}/{m['fail']} | {s['given']} | {s['wrong_runs']} | {s['working_runs']} | "
                     f"{s['stuck_runs']} | {s['root_runs']} | {s['unsupported_no_hint']} | "
                     f"{s['held_with_prereq']}/{s['prereq_held_runs']} | {s['distinct_claims']} | "
                     f"{s.get('implemented_contradicts', 0)} |")
    lines += ["", "## Findings for the builder", "", "**Blocking.**", ""]
    lines += [f"- {b}" for b in doc["feedback"]["blocking"]] or ["- none"]
    lines += ["", "**Advisory.**", ""]
    lines += [f"- {a}" for a in doc["feedback"]["advisory"]] or ["- none"]
    lines += ["", "## Mistaken beliefs (traps)", ""]
    for nid, claims in doc["feedback"]["traps"].items():
        lines += [f"- **{nid}**: " + " | ".join(_cell(c) for c in claims)]
    off = doc["feedback"].get("off_graph") or []
    if off:
        lines += ["", "## Claims no node covers (off_graph, most frequent first)", ""]
        for c in off:
            lines += [f"- ({'wrong' if c['wrong'] else 'step'}, {c['runs']} run{'s' if c['runs'] != 1 else ''}) "
                      f"{_cell(c['claim'])}", f"  > {c['example']['run']} {c['example'].get('where')}: "
                      f"{_cell(c['example'].get('quote'))}"]
    if m["unsound_runs"] or m.get("recipe_runs") or m["residual_runs"]:
        lines += ["", "## Runs to read by hand", ""]
        lines += [f"- accepted without a hint but no END route: {r}" for r in m["unsound_runs"]]
        lines += [f"- accepted with a hint, no END route (hint-carried): {r}" for r in m.get("recipe_runs") or []]
        lines += [f"- END reached, failed, no hazard: {r}" for r in m["residual_runs"]]
    return "\n".join(lines) + "\n"


def apply_traps(graph_path: Path, traps: dict) -> None:
    doc = json.loads(graph_path.read_text(encoding="utf-8"))
    for n in doc["nodes"]:
        if n["id"] in traps:
            n["traps"] = traps[n["id"]]
    tmp = graph_path.with_name(f".{graph_path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, graph_path)
    try:
        from graph import render as GR
        reviews_path = graph_path.with_name("review.json")
        reviews = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else []
        GR.write_all(graph_path.parent, doc, reviews)
    except Exception as exc:  # the traps are written; the figure is a convenience
        print(f"Warning: could not re-render the graph: {exc}", file=sys.stderr)


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate a reasoning graph from graded runs.")
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--runs", nargs="+", required=True, help="runs.jsonl files of grade.py")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--compare", nargs="*", default=[], help="runs.jsonl of a second grading of the same runs")
    ap.add_argument("--apply-traps", action="store_true", help="write the mistaken beliefs into the graph's traps")
    args = ap.parse_args(argv)
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    records = load_runs(args.runs)
    if not records:
        ap.error("no runs")
    other = [r["label"] for r in records if r.get("graph_version") != graph.get("version")]
    warnings = ([f"{len(other)} runs were graded with another graph version: {', '.join(other[:5])}"
                 + (" ..." if len(other) > 5 else "")] if other else [])
    stats = node_stats(records, graph)
    blocking, advisory, traps, off = suggestions(records, graph, stats)
    doc = {"schema": "validate-v3", "problem": graph.get("problem"), "graph_version": graph.get("version"),
           "runs": [str(p) for p in args.runs], "warnings": warnings, "metrics": metrics(records), "nodes": stats,
           "agreement": agreement(records, load_runs(args.compare), graph) if args.compare else None,
           "feedback": {"problem": graph.get("problem"), "graph_version": graph.get("version"),
                        "blocking": blocking, "advisory": advisory, "traps": traps, "off_graph": off}}
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "report.json", json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    _write(args.out / "feedback.json", json.dumps(doc["feedback"], ensure_ascii=False, indent=2) + "\n")
    _write(args.out / "report.md", render(doc, graph))
    if args.apply_traps:
        apply_traps(args.graph, traps)
    m = doc["metrics"]
    print(f"soundness {m['soundness']} ({m['soundness_n']}, no hint), hinted AC reaching END {m['hinted_ac_end']} "
          f"({m['hinted_ac_end_n']}), discrimination {m['discrimination']} ({m['discrimination_n']}), "
          f"END+fail/other {m['residual_end_fail_other']}; {len(blocking)} blocking, {len(advisory)} advisory "
          f"findings, {len(off)} off-graph claims")
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    print(f"Report: {(args.out / 'report.md').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
