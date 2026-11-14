"""Run one program on a problem's samples, as the agent's run_samples tool does, and print the
result as JSON. The insight engine uses it to check a failed run's program: the samples are printed
in the statement, so this tells the engine nothing the solver could not have found out itself.

    WF_ARCHIVE=../data/all_candidates/ICPC_WF python3 check_samples.py \\
        --problem 2016/H-polygonal-puzzle --code program.cpp
"""
import argparse
import json
import tempfile
from pathlib import Path

from judge import ValidatorError, patch_includes, run_samples
from problem import load_problem


def check(ref, code, strict_mem=False):
    """run_samples on the program, compiled the way run.py compiles a submission."""
    problem = load_problem(ref)
    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
        f.write(patch_includes(code))
        path = f.name
    try:
        return run_samples(problem, path, strict_mem=strict_mem)
    except ValidatorError as e:
        return {"problem": problem.name, "compile_error": None, "samples": [], "judge_error": str(e)}
    finally:
        Path(path).unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem", required=True)
    ap.add_argument("--code", required=True, help="the program's source file")
    args = ap.parse_args(argv)
    print(json.dumps(check(args.problem, Path(args.code).read_text(encoding="utf-8", errors="replace"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
