"""graph.md (to read and review a graph) and graph.dot / graph.png (the graph as a figure) from a
graph.json and its review.json. No API call."""
import shutil
import subprocess
import textwrap
from pathlib import Path

from graph import rules as R

NODE_FLAGS = ("specific", "correct", "judgeable", "route_independent", "separable", "atomic")


def _last_review(doc: dict, reviews: list[dict]) -> dict | None:
    """The latest review of this version of the graph, if any."""
    for r in reversed(reviews or []):
        if r.get("version") == doc.get("version"):
            return r
    return None


def _routes(routes) -> str:
    return " \\| ".join("statement" if not r else " + ".join(r) for r in routes or []) or "—"


def to_markdown(doc: dict, reviews: list[dict]) -> str:
    prov = doc.get("provenance") or {}
    last = _last_review(doc, reviews)
    per_node = {r["id"]: r for r in ((last or {}).get("review") or {}).get("nodes") or []}
    nodes = doc.get("nodes") or []
    lines = [f"# Reasoning graph · {doc.get('title', '')} ({doc.get('problem', '')})", "",
             f"status **{doc.get('status')}** · version `{doc.get('version')}` · {len(nodes)} nodes · "
             f"{len((doc.get('end') or {}).get('routes') or [])} END route(s) · {len(doc.get('hazards') or [])} "
             f"hazard(s) · {prov.get('model', '?')} (build {prov.get('gen_effort', '?')}, review "
             f"{prov.get('audit_effort', '?')}) · {prov.get('builder_submissions', '?')} submission(s), "
             f"{prov.get('review_rounds', '?')} review round(s)"
             + (" · **edited by hand**" if prov.get("edited_by_hand") else ""), "",
             f"**Route.** {doc.get('solution_outline', '')}", "",
             "| node | depth | kind | name | routes |", "|---|---:|---|---|---|"]
    for n in nodes:
        lines.append(f"| {n['id']} | {n.get('depth', '')} | {n.get('kind', '')} | {n.get('name', '')} | "
                     f"{_routes(n.get('routes'))} |")
    end = doc.get("end") or {}
    lines.append(f"| END | | | complete solution | {_routes(end.get('routes'))} |")
    for n in nodes:
        lines += ["", f"## {n['id']} · {n.get('name', '')}", "",
                  f"*{n.get('kind')} · depth {n.get('depth', '')} · source: {n.get('source')} · routes: "
                  f"{_routes(n.get('routes'))}*", "",
                  f"**Statement.** {n.get('statement', '')}", "",
                  f"**Anchors.** {' · '.join(n.get('anchors') or [])}", "",
                  f"**Accept.** {n.get('accept', '')}"]
        if n.get("traps"):
            lines += ["", "**Traps (mistaken beliefs seen in graded runs).**", ""] + [f"- {t}" for t in n["traps"]]
        r = per_node.get(n["id"])
        if r:
            false = [f for f in NODE_FLAGS if not r.get(f, True)]
            verdict = "all checks passed" if not false else "failed: " + ", ".join(false)
            lines += ["", f"**Review.** {verdict}" + (f" — {r['note']}" if r.get("note") else "")]
    lines += ["", "## END", "", f"**Statement.** {end.get('statement', '')}", "",
              f"**Routes (solution families).** {_routes(end.get('routes'))}", "",
              f"**Key nodes (holding them is reaching END; the other route members are steps on the way).** "
              f"{_routes(R.end_key_routes(doc))}"]
    lines += ["", "## Hazards (END → program)", ""]
    lines += [f"- **{h['id']}** {h.get('statement', '')} *Check:* {h.get('check', '')}"
              for h in doc.get("hazards") or []] or ["- none"]
    if doc.get("paths") is not None:
        lines += ["", "## Paths (approaches the explorer worked out and the judge accepted)", ""]
        for p in doc["paths"]:
            j = p.get("judge") or {}
            lines += [f"### {p['id']} · {', '.join(p.get('end_route') or [])}", "",
                      f"{p.get('approach', '')}", "",
                      f"New nodes: {', '.join(p.get('new_nodes') or []) or 'none'} · judge: {j.get('verdict')} on "
                      f"{j.get('tests_run')} tests, slowest {j.get('max_time_s')}s · program: `{p.get('program')}` · "
                      f"{p.get('attempts')} submission(s)"]
        if not doc["paths"]:
            lines.append("- none")
        if doc.get("rejected"):
            lines += ["", "## Approaches tried but not accepted by the judge", ""]
            for r in doc["rejected"]:
                lines.append(f"- {r.get('approach', '')} (last verdict {r.get('last_verdict')}, {r.get('attempts')} "
                             f"submission(s))")
        ex = doc.get("exploration") or {}
        if ex:
            lines += ["", "## Exploration", "",
                      f"Finished: {ex.get('finished')} · {ex.get('submissions')} submissions · reason: "
                      f"{ex.get('reason', '')}"]
            if ex.get("considered"):
                lines += ["", "Ideas the explorer considered and dropped:", ""] + [f"- {x}" for x in ex["considered"]]
    if last:
        rev = last["review"]
        lines += ["", "## Review", "",
                  f"END ok: {rev.get('end_ok')}" + (f" — {rev['end_note']}" if rev.get("end_note") else ""),
                  "", f"Hazards ok: {rev.get('hazards_ok')}"
                  + (f" — {rev['hazards_note']}" if rev.get("hazards_note") else "")]
        if rev.get("alternatives"):
            lines += ["", "**Alternatives the reviewer considered.**", ""]
            for a in rev["alternatives"]:
                lines.append(f"- {a.get('approach', '')} (correct and fast: {a.get('correct_and_fast')}; "
                             f"representable: {a.get('representable')}) {a.get('note', '')}")
    if any(doc.get(k) for k in ("open_issues", "advisories", "builder_notes")):
        lines += [""]
        if doc.get("open_issues"):
            lines += ["**Open issues (blocking).**", ""] + [f"- {x}" for x in doc["open_issues"]] + [""]
        if doc.get("advisories"):
            lines += ["**Advisories.**", ""] + [f"- {x}" for x in doc["advisories"]] + [""]
        if doc.get("builder_notes"):
            lines += [f"**Builder's notes.** {doc['builder_notes']}", ""]
    if reviews:
        lines += ["", "## Review history", "",
                  "| round | version | blocking | advisory | verdict |", "|---|---|---|---|---|"]
        for r in reviews:
            mode = " (audit only)" if r.get("audit_only") else ""
            lines.append(f"| {r['round']}{mode} | `{r['version']}` | {len(r['blocking'])} | "
                         f"{len(r['advisory'])} | {r['review'].get('verdict')} |")
    return "\n".join(lines).rstrip() + "\n"


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _wrap(text: str, width: int = 38, max_lines: int = 6) -> str:
    lines = textwrap.wrap(text or "", width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += " …"
    return "\\n".join(_esc(x) for x in lines)


def to_dot(doc: dict, reviews: list[dict]) -> str:
    last = _last_review(doc, reviews)
    blocked = {b.split(" ", 1)[0].rstrip(":") for b in ((last or {}).get("blocking") or [])}
    nodes = doc.get("nodes") or []
    out = ["digraph graph_v2 {",
           '  rankdir=TB; newrank=true; nodesep=0.2; ranksep=0.4; bgcolor="white"; pad=0.1;',
           f'  label="{_esc(doc.get("title", ""))} ({_esc(doc.get("problem", ""))}) · {doc.get("status")} · '
           f'{doc.get("version")}"; labelloc=t; fontname="DejaVu Sans"; fontsize=11;',
           '  node [shape=box, style="rounded,filled", fontname="DejaVu Sans", fontsize=8.5, '
           'fillcolor="#e8eefc", color="#1f2937", penwidth=0.8, margin="0.08,0.04"];',
           '  edge [color="#1f2937", arrowsize=0.55, penwidth=0.9, fontname="DejaVu Sans", fontsize=7];']
    by_depth = {}
    for n in nodes:
        by_depth.setdefault(n.get("depth", 1), []).append(n["id"])
        color = ', color="#c0392b", penwidth=1.6' if n["id"] in blocked else ""
        out.append(f'  {n["id"]} [label="{n["id"]} · {_esc(n.get("name", ""))}\\n{_wrap(n.get("statement", ""))}"'
                   f'{color}];')
    for d in sorted(by_depth):
        out.append(f"  {{rank=same; {'; '.join(by_depth[d])};}}")
    out.append('  END [shape=doubleoctagon, fillcolor="#dcfce7", label="END\\ncomplete solution"];')
    out.append('  CODE [shape=box, fillcolor="#fef3c7", label="CODE\\naccepted program"];')
    for n in nodes:
        routes = n.get("routes") or []
        for i, r in enumerate(routes, 1):
            label = f' [label="r{i}"]' if len(routes) > 1 else ""
            for u in r:
                out.append(f"  {u} -> {n['id']}{label};")
    end_routes = (doc.get("end") or {}).get("routes") or []
    paths = doc.get("paths") or []
    for i, r in enumerate(end_routes, 1):
        name = paths[i - 1]["id"] if i <= len(paths) and paths[i - 1].get("id") else f"family {i}"
        label = f' [label="{_esc(name)}", style=dashed]' if len(end_routes) > 1 else " [style=dashed]"
        for u in R.key_nodes(doc, r):          # only the route's terminal nodes connect to END
            out.append(f"  {u} -> END{label};")
    hazards = ", ".join(h["id"] for h in doc.get("hazards") or [])
    out.append(f'  END -> CODE [label="{_esc(hazards) if hazards else "no hazards"}", penwidth=1.4];')
    out.append("}")
    return "\n".join(out) + "\n"


def write_all(out_dir: Path, doc: dict, reviews: list[dict]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "graph.md").write_text(to_markdown(doc, reviews))
    dot_path = out_dir / "graph.dot"
    dot_path.write_text(to_dot(doc, reviews))
    if shutil.which("dot"):
        subprocess.run(["dot", "-Tpng", "-Gdpi=150", str(dot_path), "-o", str(out_dir / "graph.png")],
                       check=False, capture_output=True, timeout=120)
