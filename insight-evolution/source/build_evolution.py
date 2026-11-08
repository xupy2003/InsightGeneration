#!/usr/bin/env python3
"""Build the "Insight Evolution" page: one reasoning graph per condition, showing how the frontier of a
single (problem, model) pair moves as the engine's insight grows one node at a time.

Reads, for the pair in CONFIG:
    ReasoningGraph/graph/graphs/<slug>/{graph.json, graph.dot}   the graph and its layout
    ReasoningGraph/grade/runs/<slug>/pilot/runs.jsonl            the no-hint runs, graded
    GPTv4/runs/<slug>/<model>/editorial_arm/grade/runs.jsonl     the editorial arm, graded
    GPTv4/runs/<slug>/<model>/{r<k>,f<k>}/{insight.txt, items.json, grade/runs.jsonl}

and writes viewer/index.html (standalone). Run from GPTv4/:  python3 viewer/build_evolution.py
"""
import html as H
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402
from adapters.problems import Problem  # noqa: E402

PROBLEM = "2024/K-tower-of-noiha"
SLUG = "2024_K-tower-of-noiha"
MODEL = "nemotron"
MODEL_NAME = "Nemotron-Cascade-2-30B-A3B"
# (directory, label, sub-label). The compaction rounds c1..c6 are summarised in prose, not drawn.
STAGES = [("__baseline__", "No insight", "the model alone, 5 runs",
           "The statement only. No run establishes more than two route nodes, two runs contradict N1 and two "
           "contradict N2, and all five stop inside the first three."),
          ("__editorial__", "Human editorial", "the official solution text, 5 runs",
           "The official editorial, 2232 solver tokens &mdash; five times the engine's final insight. The grader "
           "recognises N2, N4 and N6 in it together with N14, N15 and N16: the editorial argues a <b>different route "
           "into END</b>. The runs take the early nodes (N1, N2 and N4 in four or five runs each) but contradict N6 "
           "and N7 in three runs each, and all five stop inside the first four nodes. Supplying the content is not "
           "the same as the model taking it up."),
          ("r1", "Round 1", None, None), ("r2", "Round 2", None, None), ("r3", "Round 3", None, None),
          ("r4", "Round 4", None, None), ("r5", "Round 5", None, None), ("r6", "Round 6", None, None),
          ("r7", "Round 7", None, None), ("r8", "Round 8", None, None), ("r9", "Round 9", None, None),
          ("f1", "Final insight", "after compaction, 5 fresh seeds",
           "Round 9's text (730 tokens) was then compacted over six rounds &mdash; the hazard item dropped and "
           "five of the seven nodes rewritten back to level 1 &mdash; down to 448 tokens, and re-measured on five "
           "seeds the engine had never used.")]

GDIR = C.REASONING_GRAPH / "graph" / "graphs" / SLUG
RUNDIR = C.RUNS / SLUG / MODEL
NODE_LINE = re.compile(r'^(  (N\d+) \[)label="((?:[^"\\]|\\.)*)"', re.M)


def compact_dot(dot: str, graph: dict) -> str:
    """Every node label reduced to its id and short name; the statement moves to the page's tooltip."""
    names = {n["id"]: n.get("name", "") for n in graph["nodes"]}

    def sub(m: re.Match) -> str:
        nid = m.group(2)
        lines = textwrap.wrap(names.get(nid, ""), 20) or [""]
        return (m.group(1) + 'label=<<FONT POINT-SIZE="9.5"><B>' + nid + '</B></FONT><BR/>'
                '<FONT POINT-SIZE="7.5">' + "<BR/>".join(H.escape(x, quote=False) for x in lines) + "</FONT>>")

    return NODE_LINE.sub(sub, dot).replace("nodesep=0.2; ranksep=0.4;", "nodesep=0.16; ranksep=0.5;", 1)


def render_svg(dot_text: str) -> str:
    svg = subprocess.run(["dot", "-Tsvg"], input=dot_text, check=True, capture_output=True, text=True).stdout
    svg = svg[svg.index("<svg"):]
    svg = re.sub(r'<svg width="[^"]*" height="[^"]*"', "<svg", svg, count=1)
    svg = re.sub(r'<polygon fill="white" stroke="transparent" points="[^"]*"/>\n?', "", svg, count=1)
    svg = re.sub(r'(<title>graph_v2</title>\n)<text [^>]*>[^<]*</text>\n?', r"\1", svg, count=1)
    svg = re.sub(r"<!--.*?-->\n?", "", svg, flags=re.S)
    return svg.strip()


def records(path: Path, model: str | None = None) -> list:
    if not path.exists():
        return []
    out = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in out if model is None or r.get("model") == model]


def node_final(rec: dict, nid: str) -> str:
    return ((rec.get("results") or {}).get(nid) or {}).get("final", "absent")


def stage_data(key: str, label: str, sub: str | None, note: str | None, route: list, nodes: list) -> dict | None:
    if key == "__baseline__":
        recs = records(C.REASONING_GRAPH / "grade" / "runs" / SLUG / "pilot" / "runs.jsonl", MODEL)
        recs = [r for r in recs if not r.get("insight")]
        hint, tokens, change = None, None, None
    elif key == "__editorial__":
        recs = records(RUNDIR / "editorial_arm" / "grade" / "runs.jsonl")
        hint, tokens, change = Problem(PROBLEM).editorial, EDITORIAL_TOKENS, None
    else:
        recs = records(RUNDIR / key / "grade" / "runs.jsonl")
        p = RUNDIR / key / "insight.txt"
        hint = p.read_text(encoding="utf-8").strip() if p.exists() else None
        tokens = ROUND_TOKENS.get(key)
        change = ROUND_CHANGE.get(key)
    if not recs:
        return None
    recs.sort(key=lambda r: r.get("run", 0))
    n = len(recs)
    counts, given_n = {}, {}
    for nd in nodes:
        nid = nd["id"]
        c = {"established": 0, "wrong": 0, "working": 0, "absent": 0}
        for r in recs:
            c[node_final(r, nid)] = c.get(node_final(r, nid), 0) + 1
        counts[nid] = c
        given_n[nid] = sum(1 for r in recs if nid in (r.get("given") or []))
    maj = (n + 1) // 2
    states = {}
    for nid, c in counts.items():
        if c["wrong"] >= maj:
            s = "wrong"
        elif c["established"] >= maj:
            s = "established"
        elif c["working"] >= maj:
            s = "working"
        else:
            s = "absent"
        states[nid] = s
    per_run, stuck = [], {}
    for r in recs:
        held = [x for x in route if x in (r.get("established") or [])]
        wrong = [x for x in route if node_final(r, x) == "wrong"]
        st = r.get("stuck")
        if not r.get("reached_end"):
            stuck[st or "?"] = stuck.get(st or "?", 0) + 1
        per_run.append({"run": r.get("run"), "solved": bool(r.get("solved")), "cls": r.get("class"),
                        "stuck": st, "end": bool(r.get("reached_end")), "held": held, "wrong": wrong,
                        "given": [x for x in route if x in (r.get("given") or [])]})
    return {"key": key, "label": label, "sub": sub, "note": note, "runs": n,
            "solved": sum(x["solved"] for x in per_run), "ends": sum(x["end"] for x in per_run),
            "tokens": tokens, "change": change, "hint": hint,
            "counts": counts, "states": states, "given": given_n, "stuck": stuck, "per_run": per_run,
            "held_mean": round(sum(len(x["held"]) for x in per_run) / n, 2)}


def main() -> None:
    graph = json.loads((GDIR / "graph.json").read_text(encoding="utf-8"))
    dot = (GDIR / "graph.dot").read_text(encoding="utf-8")
    state = json.loads((RUNDIR / "state.json").read_text(encoding="utf-8"))
    route = state["route"]["nodes"]

    global ROUND_TOKENS, ROUND_CHANGE, EDITORIAL_TOKENS
    ROUND_TOKENS = {r["condition"]: r.get("insight_tokens") for r in state["rounds"]}
    items_prev = {}
    ROUND_CHANGE = {}
    for r in state["rounds"]:
        cond = r["condition"]
        p = RUNDIR / cond / "items.json"
        items = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        cur = {k: v.get("level") for k, v in items.items() if v.get("node")}
        added = [k for k in cur if k not in items_prev]
        up = [k for k in cur if k in items_prev and cur[k] > items_prev[k]]
        nodeof = {k: items[k]["node"] for k in cur}
        if added:
            ROUND_CHANGE[cond] = {"kind": "add", "node": nodeof[added[0]], "level": cur[added[0]]}
        elif up:
            ROUND_CHANGE[cond] = {"kind": "escalate", "node": nodeof[up[0]],
                                  "level": cur[up[0]], "from": items_prev[up[0]]}
        else:
            ROUND_CHANGE[cond] = None
        items_prev = cur
    try:
        import tokens as T
        EDITORIAL_TOKENS = T.count(MODEL, Problem(PROBLEM).editorial)
        T.stop()
    except Exception as e:                                        # the tokenizer env may be unavailable
        print(f"editorial token count unavailable ({e})", file=sys.stderr)
        EDITORIAL_TOKENS = None

    nodes = [{"id": n["id"], "name": n.get("name", ""), "kind": n.get("kind", ""),
              "statement": n.get("statement", ""), "accept": n.get("accept", ""),
              "depth": n.get("depth", 1), "routes": n.get("routes") or []} for n in graph["nodes"]]
    stages = [s for s in (stage_data(k, lab, sub, note, route, nodes) for k, lab, sub, note in STAGES) if s]

    data = {"problem": graph["problem"], "title": graph["title"], "model": MODEL_NAME,
            "route": route, "key_node": state["route"]["key"], "approach": state["route"]["approach"],
            "end_routes": (graph.get("end") or {}).get("routes") or [],
            "nodes": nodes, "stages": stages,
            "svg": render_svg(compact_dot(dot, graph)),
            "built": subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True, text=True).stdout.strip()}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\!--")
    template = (HERE / "template.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/" in template
    fragment = template.replace("/*__DATA__*/", payload)
    standalone = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                  "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
                  "</head>\n<body>\n" + fragment + "\n</body>\n</html>\n")
    (HERE / "index.html").write_text(standalone, encoding="utf-8")
    print(f"{len(stages)} stages, {len(nodes)} nodes -> {HERE / 'index.html'} "
          f"({(HERE / 'index.html').stat().st_size / 1e3:.0f} kB)")
    for s in stages:
        print(f"  {s['label']:16s} runs={s['runs']} solved={s['solved']} end={s['ends']} "
              f"held={s['held_mean']} tok={s['tokens']} stuck={s['stuck']}")


if __name__ == "__main__":
    main()
