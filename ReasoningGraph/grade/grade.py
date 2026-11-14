"""Grade runs against a reasoning graph: for each run, the solver's state on every node in its last
substantive round (and, with --first-round, its first), how its programs stand to the nodes and the
hazards, and what follows: END reached or not, unsupported nodes, the frontier, the stuck node, the
roots, the run's class. See ../design.md §2.

    python3 grade.py --graph graph/graphs/2025_J-stacking-cups/graph.json \\
        --runs '/path/agentv2/runs_hard/*/baseline/2025_J-stacking-cups_run*_transcript.jsonl' \\
        --out grade/runs/2025_J-stacking-cups/baseline [--first-round] [--workers 8] [--dry-run]

Reads *_transcript.jsonl, with the *_submissions.jsonl and *_summary.json beside it. A run with a hint
(insight or editorial arm) has the hint read first: the nodes it gives away are `given`: recorded and used as
prerequisites for frontier / unsupported, but not counted toward END (the run must establish a key node
itself; 2026-11-02). Node states come from the windows alone (2026-11-03): the programs give `implemented`
(how the final program stands to each node) and the hazards. The probes are blind by default (no judge
feedback, no verdict; --sighted shows them). Writes runs.jsonl, grade.json and report.md under --out; answers are cached in --out/cache
(or --cache), so a rerun asks only for what was not answered yet. Run it on the login node.
"""
import argparse
import glob
import hashlib
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

VER2 = Path(__file__).resolve().parents[1]
if str(VER2) not in sys.path:
    sys.path.insert(0, str(VER2))
import config as C  # noqa: E402
from problems import normalize  # noqa: E402
from grade import rounds as Rd  # noqa: E402
from grade import windows as W  # noqa: E402
from grade import probe as P  # noqa: E402
from grade import programs as Pg  # noqa: E402
from grade import closure as Cl  # noqa: E402

log = logging.getLogger("grade")
CLAIMS_PER_NODE = 4


def run_info(trace) -> dict:
    """Labels from the run layout <collection>/<model>/<condition>/<slug>_runN_transcript.jsonl, and the
    outcome, model and hint from the summary beside the transcript."""
    trace = Path(trace).resolve()
    summary_path = trace.with_name(trace.name.replace("_transcript.jsonl", "_summary.json"))
    summary = (json.loads(summary_path.read_text(encoding="utf-8"))
               if summary_path != trace and summary_path.exists() else {})
    condition, model_dir, collection = ([p.name for p in trace.parents][:3] + ["-", "-", "-"])[:3]
    number = re.search(r"_run(\d+)_transcript", trace.name)
    run = int(number.group(1)) if number else None
    model_name = str(summary.get("model") or "")
    model = ("qwen" if "qwen" in model_name.lower() else "nemotron" if "nemotron" in model_name.lower()
             else model_dir)
    solved = summary.get("solved")
    solved = solved if isinstance(solved, bool) else (str(solved) == "True" if solved is not None else None)
    return {"label": f"{collection}/{model_dir}/{condition}/run{run}", "group": f"{collection}/{model_dir}/{condition}",
            "collection": collection, "model": model, "condition": condition, "run": run, "trace": str(trace),
            "problem": normalize(str(summary.get("problem") or "")) if summary.get("problem") else None,
            "solved": solved, "insight": str(summary.get("insight")) == "True",
            "submissions": summary.get("num_submissions"), "stop_reason": summary.get("stop_reason")}


def plan_run(trace, first: bool, min_chars: int = C.MIN_ROUND_CHARS, k: int = C.PROGRAMS_PER_RUN,
             blind: bool = False, tail: bool = True) -> dict:
    """What the grader reads of one run: the rounds, their windows, the hint's windows and the programs.
    blind: the windows carry no tool results (judge feedback). tail: read the short rounds after the last
    substantive one too (each as its own windows)."""
    rounds = Rd.read_rounds(trace)
    sel = Rd.select(rounds, first, min_chars)
    read = [rnd for rnd in (sel["first"], sel["last"]) if rnd is not None] + (sel["tail"] if tail else [])
    wins = {rnd: W.round_windows(trace, rnd, blind=blind) for rnd in read}
    hint = Rd.insight_text(trace)
    subs = Pg.submissions(trace)
    return {"rounds": rounds, "selection": sel, "windows": wins, "hint": hint,
            "hint_windows": W.text_windows(hint) if hint else [], "subs": subs,
            "programs": Pg.select(subs, set(wins), k)}


def window_checkpoint(window, answer) -> dict:
    return {"id": window["id"], "kind": "window", "rounds": window["rounds"], "focus": answer["focus"],
            "rows": [dict(row, where=window["id"]) for row in answer["nodes"]],
            "off_graph": [dict(x, where=window["id"]) for x in answer.get("off_graph") or []]}


def program_checkpoint(program, answer) -> dict:
    where = f"program #{program['id']} ({program['role']}, {program.get('verdict')})"
    rows = [{"node_id": r["node_id"], "status": r["status"], "state": Cl.PROGRAM_STATE[r["status"]],
             "quote": r["quote"] or None, "solver_claim": r["reason"], "unit_id": None, "where": where}
            for r in answer["nodes"]]
    return {"id": f"P{program['id']}", "kind": "program", "rounds": [program.get("round")], "focus": None,
            "submission": program["id"], "role": program["role"], "verdict": program.get("verdict"),
            "hazards": answer["hazards"], "rows": rows}


def checkpoints_of(plan, answers: dict, order: list[int]) -> list[dict]:
    """The run's checkpoints in time order: the windows of the rounds read (in round order), then its
    programs in submission order (the program of a round read before the final one)."""
    out = []
    for rnd in order:
        for w in plan["windows"].get(rnd, []):
            if w["id"] in answers:
                out.append(window_checkpoint(w, answers[w["id"]]))
    for prog in plan["programs"]:
        key = f"program #{prog['id']}"
        if key in answers:
            out.append(program_checkpoint(prog, answers[key]))
    return out


def given_of(plan, answers: dict) -> tuple[list[str], list[dict]]:
    """Nodes the hint states (established in the hint's windows), and the hint's rows."""
    given, rows = set(), []
    for w in plan["hint_windows"]:
        ans = answers.get(w["id"])
        if ans:
            for row in ans["nodes"]:
                rows.append(dict(row, where=w["id"]))
                if row["state"] == "established":
                    given.add(row["node_id"])
    return sorted(given), rows


def rounds_order(plan) -> list[int]:
    """The rounds read, in time order: first, the fallback round when it was used, last, then its tail."""
    sel, order = plan["selection"], []
    for x in [sel["first"], sel["fallback"] if plan.get("fallback_used") else None, sel["last"]] + list(sel.get("tail") or []):
        if x is not None and x not in order and x in plan["windows"]:
            order.append(x)
    return order


def run_end(plan, answers: dict, order: list[int]) -> dict | None:
    """The end of the run as read: the last C.ADJ_FINAL_CHARS characters of the windows read of the last
    substantive round and its tail, in order (the solver's final write-up and code), with the ids of the
    windows they come from. Falls back to the last window read when none of those was."""
    last = plan["selection"]["last"]
    ending = [w for rnd in order if last is not None and rnd >= last
              for w in plan["windows"].get(rnd, []) if w["id"] in answers]
    if not ending:
        ending = [w for rnd in order for w in plan["windows"].get(rnd, []) if w["id"] in answers][-1:]
    if not ending:
        return None
    need, covered = C.ADJ_FINAL_CHARS, []
    for w in reversed(ending):
        covered.insert(0, w["id"])
        need -= sum(len(u["text"]) + 1 for u in w["units"])
        if need <= 0:
            break
    text = "\n".join(u["text"] for w in ending for u in w["units"])
    return {"where": covered[0] if len(covered) == 1 else f"{covered[0]}..{covered[-1]}",
            "text": text[-C.ADJ_FINAL_CHARS:]}


def trail_of(plan, answers: dict, order: list[int], nid: str) -> tuple[list[dict], list[dict], dict | None]:
    """One node's rows over the windows read, in time order, each with the solver's text around its quote
    (C.ADJ_BEFORE characters before, C.ADJ_AFTER after); every window's id and focus sentence; and the end
    of the run as read (run_end: its last C.ADJ_FINAL_CHARS characters, the solver's final write-up and code)."""
    trail, windows, final = [], [], run_end(plan, answers, order)
    for rnd in order:
        for w in plan["windows"].get(rnd, []):
            ans = answers.get(w["id"])
            if not ans:
                continue
            windows.append({"id": w["id"], "focus": ans.get("focus")})
            row = next((r for r in ans["nodes"] if r["node_id"] == nid), None)
            if not row or row["state"] == "absent":
                continue
            text = next((u["text"] for u in w["units"] if u["id"] == row.get("unit_id")), "")
            quote = row.get("quote") or ""
            i = text.find(quote) if quote else -1
            context = text[max(0, i - C.ADJ_BEFORE): i + len(quote) + C.ADJ_AFTER] if i >= 0 else quote
            trail.append({"where": w["id"], "state": row["state"], "solver_claim": row.get("solver_claim"),
                          "quote": quote, "context": context})
    return trail, windows, final


def adjudications_of(answers: dict) -> dict:
    return {key.split(" ", 1)[1]: ans for key, ans in answers.items() if key.startswith("adjudicate ")}


def record_of(graph, run, plan, answers, rounds_read: list[int]) -> dict:
    cps = checkpoints_of(plan, answers, rounds_read)
    given, hint_rows = given_of(plan, answers)
    hint_off = [dict(x, where=w["id"]) for w in plan["hint_windows"]
                for x in (answers.get(w["id"]) or {}).get("off_graph") or []]
    off_graph = [x for cp in cps if cp["kind"] == "window" for x in cp.get("off_graph") or []]
    final = next((cp for cp in reversed(cps) if cp["kind"] == "program" and cp["role"] == "final"), None)
    tripped = [h["hazard_id"] for h in (final or {}).get("hazards") or [] if h["status"] == "tripped"]
    summary = Cl.summarize(graph, cps, given, run["solved"], tripped, off_graph, adjudications_of(answers))
    windows = [w for rnd in rounds_read for w in plan["windows"].get(rnd, [])]
    return {**run, "graph_version": graph.get("version"),
            "rounds_total": len(plan["rounds"]), "rounds_read": rounds_read,
            "selection": plan["selection"],
            "windows_read": [w["id"] for w in windows if w["id"] in answers],
            "windows_unread": [w["id"] for w in windows if w["id"] not in answers],
            "windows_salvaged": [w["id"] for w in windows if (answers.get(w["id"]) or {}).get("off_graph_dropped")],
            "hint_chars": len(plan["hint"] or ""), "hint_windows": [w["id"] for w in plan["hint_windows"]],
            "hint_rows": hint_rows, "hint_off_graph": hint_off,
            "profile": Pg.profile(plan["subs"]),
            "programs": [{"id": p["id"], "role": p["role"], "round": p.get("round"), "verdict": p.get("verdict"),
                          "hazards": (answers.get(f"program #{p['id']}") or {}).get("hazards")}
                         for p in plan["programs"]],
            "checkpoints": [{"id": cp["id"], "kind": cp["kind"], "rounds": cp["rounds"], "focus": cp.get("focus")}
                            for cp in cps if cp["kind"] == "window"],       # the trajectories' columns
            **summary}


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(doc: dict, records: list[dict], graph: dict) -> str:
    usage = doc["usage"]
    lines = [f"# Grading: {graph.get('title')} ({graph.get('problem')}, graph {graph.get('version')})", "",
             f"{len(records)} runs; {doc['windows_read']} windows and {doc['programs_read']} programs read, "
             f"{doc['hint_windows']} hint windows; {doc['model']} / {doc['effort']}: "
             f"{usage.get('input_tokens', 0):,} input and {usage.get('output_tokens', 0):,} output tokens in "
             f"{doc['requests']} requests, {doc['cache_hits']} answers from the cache."
             + (" **Blind**: the probes saw neither the judge's feedback nor any verdict." if doc.get("blind") else ""),
             "",
             "Each run's checkpoints are the windows of the rounds read (first, fallback, last) and its programs. "
             "A trajectory has one character per checkpoint: `+` established, `x` wrong, `~` working, `.` absent. "
             "Held = established in the run's own text (its windows); the programs give `implemented` (how the final "
             "program stands to each node) and the hazards, never a node's state; nodes given by a hint are listed but "
             "do not count toward END. END is reached on a route when its key node is held and no node of the route "
             "is left wrong; derived = the whole route held. The frontier is what the solver could do next; the stuck "
             "node is the frontier node with the most wrong or working evidence, else the root (the shallowest node "
             "left wrong); a run that engaged no node but stated wrong claims no node covers is off_graph. A node the "
             "windows leave wrong gets a second reading over its whole trail (adjudication): its final operative "
             "version decides, and wrong passages the solver's own text defeats are slips (`x ⇒ +` in the "
             "trajectories).", ""]
    lines += [f"- {w}" for w in doc["warnings"]] + ([""] if doc["warnings"] else [])
    lines += ["## Classes", "", "| class | runs |", "|---|---:|"]
    for cls, n in doc["summary"]["classes"].items():
        lines.append(f"| {cls} | {n} |")
    lines += ["", "## Runs", "",
              "| run | solved | class | rounds read | windows | programs | given | held | derived | unsupported | "
              "frontier | stuck | root | hazards tripped | code gap | off-graph |",
              "|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|---:|"]
    for r in records:
        solved = {True: "yes", False: "no", None: "?"}[r["solved"]]
        stuck = f"{r['stuck']} ({r['stuck_source']})" if r.get("stuck") else "-"
        lines.append(f"| {r['label']} | {solved} | {r['class']} | {','.join(map(str, r['rounds_read']))}/{r['rounds_total']} | "
                     f"{len(r['windows_read'])} | {', '.join(f'#{p['id']} {p['role']}' for p in r['programs']) or '-'} | "
                     f"{', '.join(r['given']) or '-'} | {', '.join(r['established']) or '-'} | "
                     f"{'yes' if r.get('derived_end') else 'no'} | "
                     f"{', '.join(r['unsupported']) or '-'} | {', '.join(r['frontier']) or '-'} | {stuck} | "
                     f"{r['root'] or '-'} | {', '.join(r['hazards_tripped']) or '-'} | "
                     f"{', '.join(r.get('code_gap') or []) or '-'} | {len(r.get('off_graph') or [])} |")
    lines += ["", "## Nodes", "",
              "| node | depth | name | held in AC | held in failed | wrong | working | stuck | root | unsupported |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for nid, s in doc["summary"]["nodes"].items():
        lines.append(f"| {nid} | {s['depth']} | {_cell(s['name'])} | {s['held_ac']}/{doc['summary']['ac']} | "
                     f"{s['held_fail']}/{doc['summary']['fail']} | {s['wrong']} | {s['working']} | {s['stuck']} | "
                     f"{s['root']} | {s['unsupported']} |")
    lines += ["", "## Trajectories", "", "| run | " + " | ".join(n["id"] for n in graph["nodes"]) + " |",
              "|---|" + "---|" * len(graph["nodes"])]
    for r in records:
        cells = []
        for n in graph["nodes"]:
            e = r["results"][n["id"]]
            cell = f"`{e['trajectory'] or '.'}`"
            if "adjudication" in e:
                cell += f" ⇒ `{Cl.SYMBOL[e['final']]}`"
            cells.append(cell)
        lines.append(f"| {r['label']} | " + " | ".join(cells) + " |")
    adj = [(r["label"], nid, r["results"][nid]) for r in records for nid in r.get("adjudicated") or {}]
    if adj:
        lines += ["", "## Adjudicated nodes", "",
                  "The windows left these nodes wrong; the second reading of each whole trail decided:", ""]
        for label, nid, e in adj:
            a = e["adjudication"]
            lines.append(f"- {label} {nid}: `{e['trajectory']}` window {e.get('window_final')} → **{a['final']}** "
                         f"(basis {a.get('basis')}): {_cell(a.get('reason'))}")
            for s in a.get("slips") or []:
                lines.append(f"  - slip {s.get('where')}: {_cell(s.get('why'))}")
    off = [(r["label"], x) for r in records for x in r.get("off_graph") or []]
    if off:
        lines += ["", "## Claims no node covers (off_graph)", ""]
        for label, x in sorted(off, key=lambda t: (not t[1].get("wrong"), t[0])):
            lines += [f"- {label} {x.get('where')} ({'wrong' if x.get('wrong') else 'step'}): {_cell(x.get('claim'))}",
                      f"  > {_cell(x.get('quote'))}"]
    lines += ["", "## Mistaken beliefs per node", ""]
    for nid, claims in doc["summary"]["claims"].items():
        node = next(n for n in graph["nodes"] if n["id"] == nid)
        lines += [f"### {nid} · {node['name']}", "", f"Claim: {node['statement']}", ""]
        for c in claims:
            lines += [f"- {c['run']} {c['checkpoint']}: {_cell(c['claim'])}", f"  > {_cell(c['quote'])}"]
        lines.append("")
    return "\n".join(lines)


def summarize(records: list[dict], graph: dict) -> dict:
    ac = [r for r in records if r["solved"] is True]
    fail = [r for r in records if r["solved"] is False]
    nodes = {}
    for n in graph["nodes"]:
        nid = n["id"]
        nodes[nid] = {"name": n["name"], "depth": n.get("depth"),
                      "held_ac": sum(nid in r["established"] for r in ac),
                      "held_fail": sum(nid in r["established"] for r in fail),
                      "wrong": sum(r["results"][nid]["wrong"] > 0 for r in records),
                      "working": sum(r["results"][nid]["working"] > 0 for r in records),
                      "stuck": sum(r["stuck"] == nid for r in records),
                      "root": sum(r["root"] == nid for r in records),
                      "unsupported": sum(nid in r["unsupported"] for r in records),
                      "implemented_contradicts": sum((r.get("implemented") or {}).get(nid, {}).get("status")
                                                    == "contradicts" for r in records)}
    claims = defaultdict(list)
    for r in records:
        for nid, e in r["results"].items():
            seen = set()
            for c in e["claims"]:
                if c["claim"] in seen:
                    continue
                seen.add(c["claim"])
                claims[nid].append({"run": r["label"], "checkpoint": c["checkpoint"], "claim": c["claim"],
                                    "quote": c["quote"]})
    return {"ac": len(ac), "fail": len(fail), "unknown": len(records) - len(ac) - len(fail),
            "derived_ac": sum(bool(r.get("derived_end")) for r in ac),
            "off_graph_claims": sum(len(r.get("off_graph") or []) for r in records),
            "adjudicated": dict(Counter(final for r in records for final in (r.get("adjudicated") or {}).values())),
            "classes": dict(Counter(r["class"] for r in records).most_common()), "nodes": nodes,
            "claims": {nid: xs[:CLAIMS_PER_NODE * 3] for nid, xs in claims.items() if xs}}


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description="Grade runs against a reasoning graph.")
    ap.add_argument("--graph", type=Path, required=True, help="graph.json")
    ap.add_argument("--runs", nargs="+", required=True, help="*_transcript.jsonl paths or quoted globs")
    ap.add_argument("--out", type=Path, help="output directory (not needed with --dry-run)")
    ap.add_argument("--first-round", action="store_true", help="also read the first round")
    ap.add_argument("--no-fallback", action="store_true",
                    help="do not read the round before the last when the last says nothing about any node")
    ap.add_argument("--min-round-chars", type=int, default=C.MIN_ROUND_CHARS)
    ap.add_argument("--programs", type=int, default=C.PROGRAMS_PER_RUN, help="programs read per run, at most")
    ap.add_argument("--model", default=C.API_MODEL)
    ap.add_argument("--effort", default=C.GRADE_EFFORT)
    ap.add_argument("--workers", type=int, default=C.WORKERS)
    ap.add_argument("--cache", type=Path, help="answer cache shared between outputs (default OUT/cache)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be read; no model calls, no files")
    ap.add_argument("--blind", action="store_true", default=C.GRADE_BLIND,
                    help="withhold the judge's feedback and verdicts from the probes: windows carry no tool results, "
                         "the program probe is not told the verdict (the default since 2026-11-03)")
    ap.add_argument("--sighted", action="store_true", help="show the probes the judge's feedback and the verdicts")
    ap.add_argument("--no-tail", action="store_true",
                    help="read only the last substantive round, not the short rounds after it (read by default "
                         "since 2026-11-03: a fix made in a short final round belongs to the final state)")
    ap.add_argument("--no-adjudicate", action="store_true", default=not C.ADJUDICATE,
                    help="skip the second reading of the nodes the windows left wrong (their final operative version "
                         "over the whole trail; the default since 2026-11-03)")
    args = ap.parse_args(argv)
    if args.sighted:
        args.blind = False
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "openai", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if args.workers < 1:
        ap.error("--workers must be positive")
    if not args.dry_run and args.out is None:
        ap.error("--out is required unless --dry-run")
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    traces = sorted({str(Path(p).resolve()) for pattern in args.runs for p in (glob.glob(pattern) or [pattern])})
    missing = [t for t in traces if not Path(t).is_file()]
    if missing:
        ap.error("no such transcript: " + ", ".join(missing))

    runs, warnings = [], []
    for trace in traces:
        info = run_info(trace)
        if info["solved"] is None:
            warnings.append(f"{info['label']}: no summary beside the transcript; outcome unknown")
        if info["problem"] and normalize(graph.get("problem", "")) != info["problem"]:
            warnings.append(f"{info['label']}: its problem is {info['problem']}, the graph's is {graph.get('problem')}")
        plan = plan_run(trace, args.first_round, args.min_round_chars, args.programs, args.blind, not args.no_tail)
        if plan["hint"] is None:
            warnings.append(f"{info['label']}: the summary says the run had a hint, but it was not found in the prompt")
            plan["hint"] = ""
        runs.append({"info": info, "plan": plan})

    if args.dry_run:
        print(f"{'run':48s} {'solved':>6s} {'rounds':>7s} {'read':>12s} {'windows':>8s} {'hint':>5s} {'programs':>9s}")
        calls = 0
        for r in runs:
            sel, plan = r["plan"]["selection"], r["plan"]
            read = ",".join(str(x) for x in [sel["first"], sel["last"]] + list(sel.get("tail") or []) if x is not None)
            n_win = sum(len(v) for v in plan["windows"].values())
            calls += n_win + len(plan["hint_windows"]) + len(plan["programs"])
            print(f"{r['info']['label']:48s} {str(r['info']['solved']):>6s} {len(plan['rounds']):7d} {read:>12s} "
                  f"{n_win:8d} {len(plan['hint_windows']):5d} {len(plan['programs']):9d}")
        print(f"{calls} probe calls (windows + hint windows + programs), plus fallback rounds when a last round "
              f"says nothing. No call was made.")
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)
        return 0

    prober = P.Prober(args.out, model=args.model, effort=args.effort, client=client, cache_dir=args.cache,
                      blind=args.blind)
    answers = defaultdict(dict)

    def fail(exc) -> bool:
        if exc.fatal:
            print(f"Error: {exc}", file=sys.stderr)
            return True
        warnings.append(str(exc))
        log.warning("%s", exc)
        return False

    def probe_all(tasks) -> bool:
        """tasks: (run index, key, callable). Returns False when a fatal error stopped the grading."""
        if not tasks:
            return True
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fnc): (i, key) for i, key, fnc in tasks}
            for done, future in enumerate(as_completed(futures), 1):
                i, key = futures[future]
                try:
                    answers[i][key] = future.result()
                except P.ProbeError as exc:
                    if fail(exc):
                        for pending in futures:
                            pending.cancel()
                        return False
                if done % 20 == 0 or done == len(futures):
                    log.info("%d/%d probes done", done, len(futures))
        return True

    tasks = []
    for i, r in enumerate(runs):
        plan, label = r["plan"], r["info"]["label"]
        for w in plan["hint_windows"]:
            tasks.append((i, w["id"], lambda w=w, label=label: prober.probe_insight(graph, w, label)))
        for rnd, wins in plan["windows"].items():
            for w in wins:
                tasks.append((i, w["id"], lambda w=w, label=label: prober.probe_window(graph, w, label)))
        for prog in plan["programs"]:
            tasks.append((i, f"program #{prog['id']}", lambda prog=prog, label=label: prober.probe_program(graph, prog, label)))
    log.info("Probing %d items of %d runs", len(tasks), len(runs))
    if not probe_all(tasks):
        return 1

    # Fallback: a last round whose windows say nothing about any node is replaced by the substantive round before it.
    fallback_tasks = []
    for i, r in enumerate(runs):
        plan, sel = r["plan"], r["plan"]["selection"]
        last_wins = [w for rnd in [sel["last"]] + list(sel.get("tail") or []) for w in plan["windows"].get(rnd, [])]
        said = any(row["state"] != "absent" for w in last_wins if w["id"] in answers[i]
                   for row in answers[i][w["id"]]["nodes"])
        if last_wins and not said and sel["fallback"] is not None and not args.no_fallback:
            plan["windows"][sel["fallback"]] = W.round_windows(r["info"]["trace"], sel["fallback"], blind=args.blind)
            plan["fallback_used"] = True
            for w in plan["windows"][sel["fallback"]]:
                fallback_tasks.append((i, w["id"], lambda w=w, label=r["info"]["label"]:
                                       prober.probe_window(graph, w, label)))
    if fallback_tasks:
        log.info("Reading the fallback round of %d runs: %d windows", len({t[0] for t in fallback_tasks}),
                 len(fallback_tasks))
        if not probe_all(fallback_tasks):
            return 1

    # Adjudication: a node the windows leave wrong gets a second reading over its whole trail.
    adj_tasks = []
    if not args.no_adjudicate:
        nodes_by_id = {n["id"]: n for n in graph["nodes"]}
        for i, r in enumerate(runs):
            plan, order, label = r["plan"], rounds_order(r["plan"]), r["info"]["label"]
            states = Cl.node_states(graph, checkpoints_of(plan, answers[i], order))
            for nid, e in states.items():
                if e["final"] != "wrong":
                    continue
                trail, wins, final = trail_of(plan, answers[i], order, nid)
                adj_tasks.append((i, f"adjudicate {nid}", lambda nid=nid, trail=trail, wins=wins, final=final, label=label:
                                  prober.probe_node(graph, nodes_by_id[nid], trail, wins, label, final)))
        if adj_tasks:
            log.info("Adjudicating %d nodes the windows left wrong", len(adj_tasks))
            if not probe_all(adj_tasks):
                return 1

    records = []
    for i, r in enumerate(runs):
        plan = r["plan"]
        order = rounds_order(plan)
        rec = record_of(graph, r["info"], plan, answers[i], order)
        rec["blind"] = args.blind
        if rec["windows_unread"]:
            warnings.append(f"{r['info']['label']}: {len(rec['windows_unread'])} windows without an accepted answer")
        if rec["windows_salvaged"]:
            warnings.append(f"{r['info']['label']}: off_graph claims whose quotes failed the checks dropped from "
                            + ", ".join(rec["windows_salvaged"]))
        records.append(rec)
    summary = summarize(records, graph)
    doc = {"schema": "grade-v3", "problem": graph.get("problem"), "title": graph.get("title"),
           "graph_version": graph.get("version"), "graph": str(args.graph.resolve()),
           "graph_sha256": hashlib.sha256(args.graph.read_bytes()).hexdigest(),
           "first_round": args.first_round, "min_round_chars": args.min_round_chars, "blind": args.blind,
           "tail": not args.no_tail, "adjudicate": not args.no_adjudicate, "adjudicated": len(adj_tasks),
           "unit_chars": C.UNIT_CHARS, "window_chars": C.WINDOW_CHARS, "model": args.model, "effort": args.effort,
           "windows_read": sum(len(r["windows_read"]) for r in records),
           "hint_windows": sum(len(r["hint_windows"]) for r in records),
           "programs_read": sum(len(r["programs"]) for r in records),
           "requests": prober.requests, "cache_hits": prober.cache_hits, "usage": dict(prober.usage),
           "warnings": warnings, "summary": summary}
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "runs.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    _write(args.out / "grade.json", json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    _write(args.out / "report.md", render(doc, records, graph))
    for cls, n in summary["classes"].items():
        print(f"{cls}: {n}")
    print(f"Report: {(args.out / 'report.md').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
