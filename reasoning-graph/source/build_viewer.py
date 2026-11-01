#!/usr/bin/env python3
"""Build the interactive viewer for the pilot: the four reasoning graphs and the 40 graded traces.

Reads graph/graphs/<slug>/{graph.json, graph.dot}, grade/runs/<slug>/{pilot,pilot_blind}/runs.jsonl,
validate/reports/<slug>[_blind]/report.json and the round-0 prompt of each trace (statement, hint text),
renders each graph.dot to SVG with graphviz (same layout as graph.png) and writes

    viewer/index.html      standalone page (open locally or hand out)
    viewer/artifact.html   the same page as a fragment for claude.ai Artifacts (no html/head/body)

Run from Ver2/:  python3 viewer/build_viewer.py
"""
import html as html_mod
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from graph import rules as R  # noqa: E402
from grade import rounds as RD  # noqa: E402

# Tab order: the order the pilots were run.
SLUGS = ["2025_J-stacking-cups", "2024_I-steppe-on-it", "2024_J-the-silk-road-with-robots", "2025_B-blackboard-game"]
# Gradings shown on the page. The blind re-grade (grade/runs/<slug>/pilot_blind) was dropped from the page on
# 2026-11-01 at the user's request; add {"pilot_blind": "blind"} back here to get the toggle and per-run diff again.
COHORTS = {"pilot": "standard"}
MODELS = {"qwen": "Qwen3.6-35B-A3B", "nemotron": "Nemotron-Cascade-2-30B-A3B"}

RUN_FIELDS = ("label", "collection", "model", "condition", "run", "trace", "solved", "insight", "submissions",
              "stop_reason", "rounds_total", "rounds_read", "selection", "windows_read", "hint_chars", "profile",
              "programs", "checkpoints", "results", "given", "established", "reached_end", "end_routes_satisfied",
              "unsupported", "frontier", "stuck", "roots", "root", "hazards_tripped", "class", "blind")


def condition_label(cond: str) -> str:
    if cond == "baseline":
        return "no hint"
    if cond == "editorial":
        return "editorial"
    m = re.match(r"loop_r(\d+)(_ownrate)?$", cond)
    if m:
        return f"GPTv3 hint, round {m.group(1)}" + (" (own-rate pick)" if m.group(2) else "")
    return cond


NODE_LINE = re.compile(r'^(  (N\d+) \[)label="((?:[^"\\]|\\.)*)"', re.M)


def compact_dot(dot: str, graph: dict) -> str:
    """graph.dot with every node label reduced to the node id and its short name (the statement moves to the
    page's hover tooltip). Ranks, edges, route labels, END/CODE and the reviewer's red outlines stay as in
    graph.png; the spacing is tightened a little for the smaller boxes."""
    names = {n["id"]: n.get("name", "") for n in graph["nodes"]}

    def sub(m: re.Match) -> str:
        nid = m.group(2)
        lines = textwrap.wrap(names.get(nid, ""), 20) or [""]
        label = ('<<FONT POINT-SIZE="9.5"><B>' + nid + '</B></FONT><BR/><FONT POINT-SIZE="7.5">'
                 + "<BR/>".join(html_mod.escape(x, quote=False) for x in lines) + "</FONT>>")
        return m.group(1) + "label=" + label

    out = NODE_LINE.sub(sub, dot)
    return out.replace("nodesep=0.2; ranksep=0.4;", "nodesep=0.16; ranksep=0.5;", 1)


def render_svg(dot_text: str) -> str:
    svg = subprocess.run(["dot", "-Tsvg"], input=dot_text, check=True, capture_output=True, text=True).stdout
    svg = svg[svg.index("<svg"):]
    # Drop the fixed pixel size (CSS scales the viewBox), the white background and the title label:
    # the page carries the title itself and paints its own theme background.
    svg = re.sub(r'<svg width="[^"]*" height="[^"]*"', "<svg", svg, count=1)
    svg = re.sub(r'<polygon fill="white" stroke="transparent" points="[^"]*"/>\n?', "", svg, count=1)
    svg = re.sub(r'(<title>graph_v2</title>\n)<text [^>]*>[^<]*</text>\n?', r"\1", svg, count=1)
    svg = re.sub(r"<!--.*?-->\n?", "", svg, flags=re.S)
    return svg.strip()


def statement_text(runs: list[dict]) -> str:
    """The problem statement as the solver saw it, from a run without a hint (else cut before the hint)."""
    for r in sorted(runs, key=lambda x: x["insight"]):
        rec = RD.round0(r["trace"])
        prompt = rec.get("prompt") or ""
        if not prompt:
            continue
        if r["insight"]:
            for marker in ("## Key insights", *RD.INSIGHT_MARKERS):
                i = prompt.find(marker)
                if i >= 0:
                    prompt = prompt[:i]
                    break
        return prompt.strip()
    return ""


def load_runs(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            slim = {k: r.get(k) for k in RUN_FIELDS}
            slim["model_name"] = MODELS.get(r["model"], r["model"])
            slim["condition_label"] = condition_label(r["condition"])
            hint = RD.insight_text(r["trace"]) if r.get("insight") else ""
            slim["hint"] = hint or ""
            n_cp = len(r.get("checkpoints") or [])
            for nid, res in (r.get("results") or {}).items():
                if len(res.get("trajectory", "")) != n_cp:
                    print(f"warning: {path} {r['label']} {nid}: trajectory {len(res['trajectory'])} != "
                          f"{n_cp} checkpoints", file=sys.stderr)
            out.append(slim)
    return out


def load_report(path: Path) -> dict:
    if not path.exists():
        return {}
    rep = json.loads(path.read_text(encoding="utf-8"))
    nodes = {}
    for nid, st in (rep.get("nodes") or {}).items():
        nodes[nid] = {k: st.get(k) for k in ("held_ac", "held_fail", "given", "wrong_runs", "working_runs",
                                              "stuck_runs", "root_runs", "distinct_claims")}
        nodes[nid]["claims"] = (st.get("claims") or [])[:6]
    return {"metrics": rep.get("metrics") or {}, "nodes": nodes}


def build_problem(slug: str) -> dict:
    gdir = ROOT / "graph" / "graphs" / slug
    graph = json.loads((gdir / "graph.json").read_text(encoding="utf-8"))
    dot_text = (gdir / "graph.dot").read_text(encoding="utf-8")
    cohorts = {}
    for cohort in COHORTS:
        p = ROOT / "grade" / "runs" / slug / cohort / "runs.jsonl"
        if p.exists():
            cohorts[cohort] = {"runs": load_runs(p),
                               "report": load_report(ROOT / "validate" / "reports" /
                                                     (slug if cohort == "pilot" else f"{slug}_blind") /
                                                     "report.json")}
    runs_std = cohorts.get("pilot", {}).get("runs") or next(iter(cohorts.values()))["runs"]
    nodes = []
    for i, n in enumerate(graph["nodes"]):
        nodes.append({"id": n["id"], "index": i, "name": n.get("name", ""), "kind": n.get("kind", ""),
                      "statement": n.get("statement", ""), "accept": n.get("accept", ""),
                      "routes": n.get("routes") or [], "depth": n.get("depth", 1), "source": n.get("source"),
                      "path": n.get("path"), "traps": n.get("traps") or []})
    paths = []
    for i, p in enumerate(graph.get("paths") or []):
        j = p.get("judge") or {}
        paths.append({"id": p["id"], "approach": p.get("approach", ""), "end_route": p.get("end_route") or [],
                      "key_node": p.get("key_node"), "new_nodes": p.get("new_nodes") or [],
                      "source": p.get("source") or "exploration", "judge": j.get("verdict"),
                      "tests": j.get("tests_run"), "max_time_s": j.get("max_time_s")})
    return {
        "slug": slug, "problem": graph["problem"], "title": graph["title"], "status": graph["status"],
        "version": graph["version"], "outline": graph.get("solution_outline", ""),
        "nodes": nodes, "end": graph.get("end") or {}, "key_routes": R.end_key_routes(graph),
        "hazards": graph.get("hazards") or [], "paths": paths, "editorial": graph.get("editorial"),
        "provenance": {k: (graph.get("provenance") or {}).get(k) for k in ("model", "explorer_calls",
                                                                               "submissions", "review_rounds")},
        "svg": render_svg(compact_dot(dot_text, graph)),
        "svg_full": render_svg(dot_text),
        "statement": statement_text(runs_std),
        "cohorts": cohorts,
    }


def main() -> None:
    data = {"built": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%MZ"], capture_output=True, text=True).stdout.strip(),
            "cohort_names": COHORTS, "problems": [build_problem(s) for s in SLUGS]}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--")
    template = (HERE / "template.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/" in template
    fragment = template.replace("/*__DATA__*/", payload)
    (HERE / "artifact.html").write_text(fragment, encoding="utf-8")
    standalone = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                  "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
                  "</head>\n<body>\n" + fragment + "\n</body>\n</html>\n")
    (HERE / "index.html").write_text(standalone, encoding="utf-8")
    n_runs = sum(len(c["runs"]) for p in data["problems"] for c in p["cohorts"].values())
    print(f"{len(data['problems'])} problems, {n_runs} graded runs (all cohorts), "
          f"{len(fragment) / 1e6:.2f} MB fragment -> {HERE / 'index.html'}")


if __name__ == "__main__":
    main()
