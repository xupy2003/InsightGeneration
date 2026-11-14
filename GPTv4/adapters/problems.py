"""Problem names, and what the engine reads about a problem.

Names are normalized as ReasoningGraph names them (`2025/J-stacking-cups`, `atcoder/abc301_g`); the slug
(`2025_J-stacking-cups`) names run files and directories. The statement, title, editorial and reference
program come from ReasoningGraph/problems.py loaded by path, so the statement is byte for byte the
message the solver and the graph builder saw. That module imports its own `config`; ours is put back
afterwards (the two directories both have a config.py).
"""
import importlib.util
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
    m = re.fullmatch(r"([a-z]+\d+)/([a-z]+\d+_[a-z0-9]+)", p)
    if m:
        return "atcoder/" + m.group(2)
    return p


def is_atcoder(problem: str) -> bool:
    return normalize(problem).startswith("atcoder/")


def slug_of(problem: str) -> str:
    return normalize(problem).replace("/", "_")


_rg = None


def rg_problems():
    """ReasoningGraph/problems.py, loaded by path once."""
    global _rg
    if _rg is None:
        saved = sys.modules.get("config")
        sys.modules.pop("config", None)
        sys.path.insert(0, str(C.REASONING_GRAPH))
        try:
            spec = importlib.util.spec_from_file_location("rg_problems", C.REASONING_GRAPH / "problems.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(str(C.REASONING_GRAPH))
            if saved is not None:
                sys.modules["config"] = saved
            else:
                sys.modules.pop("config", None)
        _rg = mod
    return _rg


class Problem:
    """statement (the solver's problem message), title, editorial and reference (C++) of one problem."""

    def __init__(self, problem: str, context=None):
        self.problem = normalize(problem)
        self.slug = slug_of(problem)
        ctx = context if context is not None else rg_problems().ProblemContext(self.problem)
        self.statement, self.title = ctx.statement, ctx.title
        self.editorial, self.reference = ctx.editorial, ctx.reference

    @property
    def directory(self) -> Path | None:
        """The ICPC problem directory (statement, samples, solution.tex, solution.cpp); None for AtCoder."""
        return None if is_atcoder(self.problem) else C.ICPC_ARCHIVE / self.problem
