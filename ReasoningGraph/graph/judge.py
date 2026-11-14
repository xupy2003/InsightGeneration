"""Judge a program on a problem's tests, for the explorer: an approach becomes a path of the graph only
when its program is accepted. Uses the solver harness's problem loader and judge (Solver/agent_prompt.py,
Solver/judge.py), so the tests, the time limit and the judging mode are the ones the agent runs use. ICPC WF: the samples
first, then the secret tests; AtCoder: every test. Stops at the first failing test, like a real judge."""
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

VER2 = Path(__file__).resolve().parents[1]
if str(VER2) not in sys.path:      # so `python3 graph/judge.py ...` works from anywhere
    sys.path.insert(0, str(VER2))
import config as C  # noqa: E402
from problems import is_atcoder, normalize, solver_modules

_lock = threading.Lock()
_J = None


def _modules():
    global _J
    with _lock:
        if _J is None:
            solver_modules()
            import judge as J       # Solver/judge.py: solver_modules() put Solver/ on the path
            _J = J
    return None, _J


def load(problem: str):
    """problem_msg, meta (with the judge's problem object and the time limit) and reference, as the solver's
    harness builds them. ICPC WF only."""
    p = normalize(problem)
    if is_atcoder(p):
        raise SystemExit(f"{p}: AtCoder problems are not supported in this repository")
    AP, _ = solver_modules()
    pdir = C.ICPC_ARCHIVE / p
    if not pdir.is_dir():
        raise SystemExit(f"{p}: no problem directory {pdir}")
    msg, meta = AP.build_problem_message(pdir)
    return SimpleNamespace(problem_msg=msg, meta=meta, reference=pdir / "solution.cpp")


def _snippet(path, limit):
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None
    return text if len(text) <= limit else text[:limit] + f"\n... ({len(text)} characters in all)"


def judge_program(problem: str, code: str, workdir=None) -> dict:
    """{verdict, accepted, tests_run, n_tests, failing_test, failing_input, failing_answer, max_time_s,
    time_limit_s, compile_error} for one C++ program."""
    _, J = _modules()
    loaded = load(problem)
    prob, tl = loaded.meta["problem"], loaded.meta["time_limit"]
    workdir = Path(workdir or tempfile.mkdtemp(prefix="rg2_judge_"))
    workdir.mkdir(parents=True, exist_ok=True)
    src = workdir / "sol.cpp"
    src.write_text(code, encoding="utf-8")
    stages = ["secret"] if is_atcoder(problem) else ["sample", "secret"]
    out = {"verdict": None, "accepted": False, "tests_run": 0, "n_tests": 0, "failing_test": None,
           "failing_input": None, "failing_answer": None, "max_time_s": 0.0, "time_limit_s": tl,
           "compile_error": None}
    for which in stages:
        r = J.evaluate(prob, src, verbose=False, time_limit=tl, which=which)
        if r["verdict"] == "VE" and (r.get("compile_error") or "") == "no tests found":
            continue                                   # a problem without sample files
        out["tests_run"] += r["tests_run"]
        out["n_tests"] += r["n_tests"]
        out["max_time_s"] = max(out["max_time_s"], r["max_time_s"])
        out["verdict"] = r["verdict"]
        out["compile_error"] = (r.get("compile_error") or "")[:2000] or None
        if r["verdict"] != "AC":
            out["failing_test"] = r.get("failing_test")
            for tin, ans in prob.tests(which):
                if r.get("failing_test") and tin.stem == r["failing_test"]:
                    out["failing_input"] = _snippet(tin, C.JUDGE_SNIPPET_CHARS)
                    out["failing_answer"] = _snippet(ans, 500) if ans and Path(ans).is_file() else None
                    break
            return out
    out["accepted"] = out["verdict"] == "AC"
    return out


def judge_text(r: dict) -> str:
    """The verdict as the explorer reads it."""
    if r["verdict"] == "AC":
        return (f"Verdict: AC on all {r['tests_run']} tests (slowest {r['max_time_s']:.2f}s of the "
                f"{r['time_limit_s']:g}s limit).")
    lines = [f"Verdict: {r['verdict']} after {r['tests_run']} of {r['n_tests']} tests"
             + (f", on test {r['failing_test']}" if r.get("failing_test") else "") + "."]
    if r.get("compile_error"):
        lines.append("Compiler output:\n" + r["compile_error"])
    if r.get("failing_input") is not None:
        lines.append("Input of the failing test:\n" + r["failing_input"].rstrip())
    if r.get("failing_answer") is not None:
        lines.append("A correct answer for it (any valid answer is accepted):\n" + r["failing_answer"].rstrip())
    return "\n".join(lines)


if __name__ == "__main__":      # python3 judge.py PROBLEM FILE.cpp
    print(judge_text(judge_program(sys.argv[1], Path(sys.argv[2]).read_text())))
