"""ReasoningGraph's grader, run as a subprocess on a set of runs, and its records read back.

grade.py reads each run's last substantive round (and the short rounds after it) in 24k windows, asks a
probe for every node's state in every window, reads the hint first (its `given` nodes), and closes the
states offline: `results[N]` (trajectory, final state, the mistaken claims with quotes), `established`
(held in the run's own text), `reached_end`, `frontier`, `stuck`, `root`, `implemented`, `code_gap`,
`hazards_tripped`, `off_graph`, `class`. See ReasoningGraph/design.md §2. The pilot gradings of the
no-hint runs (grade/runs/<slug>/pilot/runs.jsonl) are read directly when they exist.
"""
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import config as C
from adapters.problems import slug_of
from graph import graph_path

log = logging.getLogger("gptv4.grading")


MOVED = (("/codebase/agentv3/", "/codebase/Solver/agentv3/"), ("/codebase/agentv2/", "/codebase/Solver/agentv2/"),
         ("/codebase/agent/", "/codebase/Solver/agent/"), ("/codebase/GPTv3/", "/codebase/InsightGen/GPTv3/"))


def fix_trace(path: str) -> str:
    """A transcript path recorded before the 2026-11-03 move of the solver directories under Solver/."""
    if not path or Path(path).exists():
        return path
    for old, new in MOVED:
        if old in path and Path(path.replace(old, new)).exists():
            return path.replace(old, new)
    return path


def load_records(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    out = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in out:
        if r.get("trace"):
            r["trace"] = fix_trace(r["trace"])
    return out


def pilot_records(problem: str) -> list:
    """ReasoningGraph's own grading of the problem's no-hint runs, when it was done."""
    return load_records(C.REASONING_GRAPH / "grade" / "runs" / slug_of(problem) / "pilot" / "runs.jsonl")


def of_model(records: list, model: str, hinted: bool | None = None) -> list:
    """The records of one model; hinted=False: only runs without a hint, True: only with one."""
    out = [r for r in records if r.get("model") == model]
    if hinted is not None:
        out = [r for r in out if bool(r.get("insight")) == hinted]
    return out


def grade(problem: str, traces: list, out_dir: Path, cache_dir: Path | None = None, workers: int = C.GRADE_WORKERS,
          log_path: Path | None = None, dry: bool = False) -> list:
    """Grade the runs (transcript paths) against the problem's graph into out_dir; returns the records.
    Already-graded runs are answered from the cache (shared through cache_dir)."""
    out_dir = Path(out_dir)
    traces = [str(Path(t).resolve()) for t in traces]
    if not traces:
        return []
    cmd = [sys.executable, "grade/grade.py", "--graph", str(graph_path(problem)), "--runs", *traces,
           "--workers", str(workers)]
    if dry:
        cmd.append("--dry-run")
    else:
        cmd += ["--out", str(out_dir.resolve())]
        if cache_dir:
            cmd += ["--cache", str(Path(cache_dir).resolve())]
    log.info(f"grading {len(traces)} runs of {problem} -> {out_dir}")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as sink:
            sink.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd[:6])} ... ({len(traces)} runs)\n")
            sink.flush()
            done = subprocess.run(cmd, cwd=C.REASONING_GRAPH, stdout=sink, stderr=subprocess.STDOUT, text=True)
        tail = f"see {log_path}"
    else:
        done = subprocess.run(cmd, cwd=C.REASONING_GRAPH, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = (done.stdout or "")[-1500:]
    if done.returncode:
        raise RuntimeError(f"grade.py failed ({done.returncode}): {tail}")
    return [] if dry else load_records(out_dir / "runs.jsonl")


def node_final(record: dict, nid: str) -> str:
    return ((record.get("results") or {}).get(nid) or {}).get("final", "absent")


def route_progress(record: dict, route_nodes: list) -> dict:
    """How far one run got on a route: the nodes held, the nodes left wrong, and the depth reached =
    the number of route nodes (in route order) held before the first one left wrong."""
    held = set(record.get("established") or [])
    wrong = {nid for nid in route_nodes if node_final(record, nid) == "wrong"}
    reached = 0
    for nid in route_nodes:
        if nid in wrong:
            break
        if nid in held:
            reached += 1
    return {"held": [n for n in route_nodes if n in held], "wrong": [n for n in route_nodes if n in wrong],
            "reached": reached, "end": bool(record.get("reached_end"))}
