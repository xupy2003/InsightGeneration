"""Problem identifiers, and what the builder and the grader read about a problem.

Problems are named as the agent runs name them, normalized:
    2025/J-stacking-cups     ICPC WF (also accepted: wf2025/J-stacking-cups, all_candidates/ICPC_WF/2025/J-...)
    atcoder/abc301_g         AtCoder (also accepted: abc301/abc301_g, all_candidates/Atcoder/abc301_g)
The slug names files and directories: 2025_J-stacking-cups, atcoder_abc301_g.

The statement is the agent's problem message byte for byte (the solver harness's build_problem_message,
Solver/agent_prompt.py), so a node's anchors are words the agent saw. Only ICPC WF problems are loaded here;
AtCoder names are still recognized, but their loader (CategoryEval) is not part of this repository.
"""
import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

import config as C


def normalize(problem: str) -> str:
    p = problem.strip().strip("/")
    for prefix in ("all_candidates/ICPC_WF/", "ICPC_WF/"):
        if p.startswith(prefix):
            return p[len(prefix):]
    for prefix in ("all_candidates/Atcoder/", "Atcoder/", "atcoder/"):
        if p.startswith(prefix):
            return "atcoder/" + p[len(prefix):]
    m = re.fullmatch(r"wf(\d{4})/(.+)", p)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.fullmatch(r"([a-z]+\d+)/([a-z]+\d+_[a-z0-9]+)", p)       # abc301/abc301_g, as the agent runs name it
    if m:
        return "atcoder/" + m.group(2)
    return p


def is_atcoder(problem: str) -> bool:
    return normalize(problem).startswith("atcoder/")


def slug_of(problem: str) -> str:
    """`2025/J-stacking-cups` -> `2025_J-stacking-cups`, as the agent run files are named."""
    return normalize(problem).replace("/", "_")


def graph_dir(problem: str) -> Path:
    return C.GRAPHS_DIR / slug_of(problem)


def read_problem_list(path=C.PROBLEMS) -> list[str]:
    lines = (line.split("#", 1)[0] for line in Path(path).read_text().splitlines())
    return [normalize(x) for line in lines for x in line.split()]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_by_path(name: str, path: Path, extra_paths=()):
    """A module loaded from its file; extra_paths go on sys.path first for the module's own imports."""
    for p in extra_paths:
        if str(p) not in sys.path:
            sys.path.insert(1, str(p))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def solver_modules():
    """agent_prompt and prompt of the solver harness (Solver/), with WF_ARCHIVE set before Solver/problem.py
    reads it on import. Solver/ goes on sys.path behind this directory: its judge.py is the judge
    graph/judge.py runs, and none of its module names is one of ours."""
    os.environ.setdefault("WF_ARCHIVE", str(C.ICPC_ARCHIVE))
    if str(C.SOLVER) not in sys.path:
        sys.path.insert(1, str(C.SOLVER))
    import agent_prompt as AP
    import prompt as P
    return AP, P


class ProblemContext:
    """statement (the agent's problem message), title, editorial and reference (C++) of one problem."""

    def __init__(self, problem: str):
        self.problem = normalize(problem)
        if is_atcoder(self.problem):
            self._load_atcoder()
        else:
            self._load_icpc()

    def _load_icpc(self):
        AP, P = solver_modules()
        pdir = C.ICPC_ARCHIVE / self.problem
        if not pdir.is_dir():
            raise SystemExit(f"{self.problem}: no problem directory {pdir}")
        self.statement, meta = AP.build_problem_message(pdir)
        self.title = meta["title"]
        self.editorial = P.load_insight(pdir)
        if not self.editorial:
            raise SystemExit(f"{self.problem}: no solution.tex under {pdir}")
        self.reference = (pdir / "solution.cpp").read_text()

    def _load_atcoder(self):
        raise SystemExit(f"{self.problem}: AtCoder problems need CategoryEval's loader, which is not part of "
                         f"this repository")

    def message(self) -> str:
        return (f"<problem>\n{self.statement.strip()}\n</problem>\n\n"
                f"<editorial>\n{self.editorial.strip()}\n</editorial>\n\n"
                f"<reference_solution>\n```cpp\n{self.reference.rstrip()}\n```\n"
                f"</reference_solution>")

    def hashes(self) -> dict:
        return {"statement": sha256(self.statement), "editorial": sha256(self.editorial),
                "reference": sha256(self.reference)}
