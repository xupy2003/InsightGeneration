"""Compile, run and validate one C++ submission against one problem.

Taken unchanged from the ICPC archive evaluator, with everything the World
Finals path never reaches removed: the Kattis package loader, contest
discovery, and the selftest CLI. `problem` is whatever the caller passes --
here a WFProblem from problem.py, which supplies the same attributes.

Three judging modes, taken from the problem:
  * comparison  -- the Kattis default validator. NOT a diff: case-insensitive
                   and whitespace-run-insensitive unless validator_flags says
                   otherwise, with float tolerance when flagged.
  * custom      -- build and run the problem's own output validator, using the
                   standard argv/exit-code protocol (42 accept, 43 reject).
  * interactive -- the validator IS the interactor: it and the submission are
                   wired to each other over a pair of pipes.

All-or-nothing, stopping at the first failing test, the way a real ICPC judge
does.
"""
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


CXX = os.environ.get("CXX", "g++")

CXXFLAGS = os.environ.get("CXXFLAGS", "-O2 -std=gnu++20 -w").split()

CC = os.environ.get("CC", "gcc")

CFLAGS = os.environ.get("CFLAGS", "-O2 -std=gnu17 -w").split()

WALL_GRACE = 5.0

DEFAULT_MEMORY_MB = 2048

OUTPUT_LIMIT_MB = int(os.environ.get("ICPC_OUTPUT_LIMIT_MB", 512))

AC, WA, TLE, RTE, CE, VE = "AC", "WA", "TLE", "RTE", "CE", "VE"

class CompileError(RuntimeError):
    pass

class ValidatorError(RuntimeError):
    pass

def parse_validator_flags(flags):
    """validator_flags -> comparison options for the default validator."""
    f = flags.split() if isinstance(flags, str) else list(flags or [])
    out = {"case_sensitive": "case_sensitive" in f,
           "space_change_sensitive": "space_change_sensitive" in f,
           "rel": None, "abs": None}
    for i, tok in enumerate(f):
        if tok in ("float_tolerance", "float_relative_tolerance",
                   "float_absolute_tolerance") and i + 1 < len(f):
            try:
                v = float(f[i + 1])
            except ValueError:
                continue
            if tok != "float_absolute_tolerance":
                out["rel"] = v
            if tok != "float_relative_tolerance":
                out["abs"] = v
    return out

def _as_float(tok):
    try:
        return float(tok)
    except ValueError:
        return None

def default_validator_accepts(team_output: str, answer: str, flags=None) -> bool:
    """The Kattis default validator.

    Its defaults are the easy thing to get wrong: a plain `diff` rejects a
    correct `yes` against an answer of `Yes`, and rejects every correct answer
    on a problem whose validator_flags set a float tolerance.
    """
    o = parse_validator_flags(flags)
    a, b = team_output, answer
    if not o["case_sensitive"]:
        a, b = a.lower(), b.lower()
    if o["space_change_sensitive"]:
        ta = [ln.split(" ") for ln in a.rstrip("\n").split("\n")]
        tb = [ln.split(" ") for ln in b.rstrip("\n").split("\n")]
        if ta != tb and o["rel"] is None and o["abs"] is None:
            return False
        ta = [t for ln in ta for t in ln if t]
        tb = [t for ln in tb for t in ln if t]
    else:
        ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if o["rel"] is None and o["abs"] is None:
            return False
        fx, fy = _as_float(x), _as_float(y)
        if fx is None or fy is None:
            return False
        d = abs(fx - fy)
        if o["abs"] is not None and d <= o["abs"]:
            continue
        if o["rel"] is not None and abs(fy) > 0 and d / abs(fy) <= o["rel"]:
            continue
        return False
    return True

def compile_source(src, out_path, extra_include=None):
    """Compile one C/C++ source to out_path. Returns the argv to run it."""
    src = Path(src)
    if src.suffix == ".py":
        return [sys.executable, str(src)]
    if src.suffix == ".c":
        # Valid C is not always valid C++ (implicit void* conversions, `new` as
        # an identifier, ...), so a .c reference solution built with g++ reports
        # a compile error the real judge never saw.
        cmd = [CC, *CFLAGS]
    else:
        cmd = [CXX, *CXXFLAGS]
    if extra_include:
        cmd += ["-I", str(extra_include)]
    cmd += ["-o", str(out_path), str(src)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise CompileError(proc.stderr[-4000:])
    return [str(out_path)]

def build_validator(problem, workdir: Path):
    """Return argv for the problem's output validator.

    The package format allows a `build` script plus a `run` entry point as an
    escape hatch; a couple of problems here use it, so honour it before
    falling back to compiling the sources directly.
    """
    vdir = problem.validator_dir
    if vdir is None:
        return None
    build, run = vdir / "build", vdir / "run"
    if build.is_file():
        staged = workdir / "validator_src"
        shutil.copytree(vdir, staged)
        os.chmod(staged / "build", 0o755)
        proc = subprocess.run(["./build"], cwd=staged, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise ValidatorError(f"validator build failed: {proc.stderr[-1000:]}")
        runner = staged / "run"
        if runner.is_file():
            os.chmod(runner, 0o755)
            return [str(runner)]
        raise ValidatorError(f"{vdir} has build but no run")
    if run.is_file() and not any(vdir.glob("*.cpp")) and not any(vdir.glob("*.cc")):
        staged = workdir / "validator_src"
        shutil.copytree(vdir, staged)
        os.chmod(staged / "run", 0o755)
        return [str(staged / "run")]

    srcs = sorted([p for p in vdir.iterdir()
                   if p.suffix in (".cpp", ".cc", ".c") and p.is_file()])
    if srcs:
        cmd = [CXX, *CXXFLAGS, "-I", str(vdir), "-o", str(workdir / "validator"),
               *[str(s) for s in srcs]]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            # Several packages ship more than one independent validator source
            # in one directory; compiling them together gives duplicate mains.
            # Fall back to the one that looks like the entry point.
            main = next((s for s in srcs if "valid" in s.stem.lower()), srcs[0])
            cmd = [CXX, *CXXFLAGS, "-I", str(vdir), "-o", str(workdir / "validator"), str(main)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                raise ValidatorError(f"validator compile failed: {proc.stderr[-1500:]}")
        return [str(workdir / "validator")]

    pys = sorted(vdir.glob("*.py"))
    if pys:
        main = next((p for p in pys if "valid" in p.stem.lower()), pys[0])
        return [sys.executable, str(main)]
    raise ValidatorError(f"no buildable validator in {vdir}")

def _limits(mem_mb, cpu_seconds, strict_mem=False, output_mb=OUTPUT_LIMIT_MB):
    """CPU time and output size are always capped; memory is not, unless asked.

    RLIMIT_AS caps virtual address space, not resident memory, and modern
    libstdc++ reserves far more VA than it touches -- enforcing it manufactures
    failures for solutions the real judge accepts, which corrupts an evaluation
    worse than missing the occasional genuine MLE.

    RLIMIT_FSIZE is not about fairness but about survival: an unattended run
    over hundreds of problems will eventually meet a model solution that prints
    in an infinite loop, and without a cap it fills the disk before the CPU
    limit trips.
    """
    def apply():
        if strict_mem and mem_mb:
            b = int(mem_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        hard = int(cpu_seconds) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (hard, hard))
        if output_mb:
            b = int(output_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (b, b))
    return apply

def _exit_verdict(returncode):
    if returncode is None or returncode == 0:
        return None
    if returncode == -signal.SIGXFSZ:
        return f"{RTE} (output limit exceeded)"
    if returncode < 0:
        try:
            return f"{RTE} (killed by {signal.Signals(-returncode).name})"
        except ValueError:
            return f"{RTE} (signal {-returncode})"
    return f"{RTE} (exit {returncode})"

def _wait_measured(proc, wall_deadline):
    """Wait for `proc`, returning (exit_status, cpu_seconds) or raising on timeout.

    Uses os.wait4 rather than Popen.wait so we get the child's own rusage: the
    limit these contests publish is a CPU-time limit, and for an interactive
    problem wall-clock would also bill the submission for the interactor's
    time, failing correct solutions.
    """
    while True:
        pid, status, ru = os.wait4(proc.pid, os.WNOHANG)
        if pid != 0:
            proc.returncode = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
            return proc.returncode, ru.ru_utime + ru.ru_stime
        if time.time() > wall_deadline:
            raise subprocess.TimeoutExpired(proc.args, 0)
        time.sleep(0.005)

def _kill_measured(proc):
    """Kill and reap, returning whatever CPU it had used."""
    try:
        proc.kill()
    except OSError:
        pass
    try:
        _, status, ru = os.wait4(proc.pid, 0)
        proc.returncode = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
        return ru.ru_utime + ru.ru_stime
    except (ChildProcessError, OSError):
        proc.returncode = -9
        return 0.0

def _validator_argv(base, tin, ans, feedback_dir, flags):
    argv = [*base, str(tin), str(ans), str(feedback_dir)]
    if flags:
        argv += flags.split() if isinstance(flags, str) else list(flags)
    return argv

def _read_feedback(feedback_dir: Path, limit=400):
    for name in ("judgemessage.txt", "judgeerror.txt", "teammessage.txt"):
        f = feedback_dir / name
        if f.is_file():
            t = f.read_text(errors="replace").strip()
            if t:
                return t[:limit]
    return ""

def run_batch_test(argv, tin, ans, problem, tl, workdir, validator_argv,
                   strict_mem=False):
    """One non-interactive test -> (ok, verdict, seconds)."""
    outfile = workdir / "team_out.txt"
    try:
        with open(tin) as fi, open(outfile, "w") as fo:
            proc = subprocess.Popen(argv, stdin=fi, stdout=fo, stderr=subprocess.DEVNULL,
                                    cwd=workdir,
                                    preexec_fn=_limits(problem.memory_mb, tl, strict_mem))
    except Exception as e:  # noqa: BLE001
        return False, f"{RTE} ({e.__class__.__name__})", 0.0
    try:
        rc, cpu = _wait_measured(proc, time.time() + tl + WALL_GRACE)
    except subprocess.TimeoutExpired:
        return False, TLE, _kill_measured(proc)

    if cpu > tl:
        return False, TLE, cpu
    v = _exit_verdict(rc)
    if v:
        # A CPU-limit kill is a TLE, not a crash; conflating them would report
        # a too-slow solution as a buggy one.
        if rc == -signal.SIGXCPU:
            return False, TLE, cpu
        return False, v, cpu
    elapsed = cpu

    if validator_argv is not None:
        fb = workdir / "feedback"
        shutil.rmtree(fb, ignore_errors=True)
        fb.mkdir(parents=True, exist_ok=True)
        ans_path = ans if ans is not None else workdir / "empty.ans"
        if ans is None:
            ans_path.write_text("")
        with open(outfile) as team_out:
            vp = subprocess.run(_validator_argv(validator_argv, tin, ans_path, fb,
                                                problem.validator_flags),
                                stdin=team_out, capture_output=True, text=True,
                                timeout=120, cwd=workdir)
        if vp.returncode == 42:
            return True, AC, elapsed
        if vp.returncode == 43:
            msg = _read_feedback(fb)
            return False, (f"{WA} ({msg})" if msg else WA), elapsed
        raise ValidatorError(
            f"validator exited {vp.returncode} (expected 42/43): "
            f"{(vp.stderr or _read_feedback(fb))[-400:]}")

    if ans is None:
        raise ValidatorError(f"{problem.name}: test {tin.name} has no .ans and no validator")
    ok = default_validator_accepts(outfile.read_text(errors="replace"),
                                   ans.read_text(errors="replace"),
                                   problem.validator_flags)
    return ok, (AC if ok else WA), elapsed

def run_interactive_test(argv, tin, ans, problem, tl, workdir, validator_argv,
                         strict_mem=False):
    """Interactive test: the validator is the interactor, wired to the
    submission by a pair of pipes (submission stdout -> validator stdin,
    validator stdout -> submission stdin)."""
    if validator_argv is None:
        raise ValidatorError(f"{problem.name} is interactive but ships no validator")
    fb = workdir / "feedback"
    shutil.rmtree(fb, ignore_errors=True)
    fb.mkdir(parents=True, exist_ok=True)
    ans_path = ans if ans is not None else workdir / "empty.ans"
    if ans is None:
        ans_path.write_text("")

    sub_r, val_w = os.pipe()   # validator -> submission
    val_r, sub_w = os.pipe()   # submission -> validator
    val = sub = None
    err_path = workdir / "interactor_err.txt"
    err_f = open(err_path, "w")
    try:
        val = subprocess.Popen(
            _validator_argv(validator_argv, tin, ans_path, fb, problem.validator_flags),
            stdin=val_r, stdout=val_w, stderr=err_f, cwd=workdir)
        sub = subprocess.Popen(
            argv, stdin=sub_r, stdout=sub_w, stderr=subprocess.DEVNULL, cwd=workdir,
            preexec_fn=_limits(problem.memory_mb, tl, strict_mem))
    finally:
        err_f.close()
        for fd in (sub_r, val_w, val_r, sub_w):
            try:
                os.close(fd)
            except OSError:
                pass

    try:
        vrc = val.wait(timeout=tl + WALL_GRACE)
    except subprocess.TimeoutExpired:
        val.kill()
        val.wait()
        return False, TLE, _kill_measured(sub)

    try:
        src, cpu = _wait_measured(sub, time.time() + WALL_GRACE)
    except subprocess.TimeoutExpired:
        cpu = _kill_measured(sub)
        src = sub.returncode
    elapsed = cpu
    # The limit is on the submission's own CPU, not on the pair's wall clock.
    if cpu > tl:
        return False, TLE, cpu

    if vrc == 42:
        return True, AC, elapsed
    if vrc == -signal.SIGPIPE:
        # The interactor wrote to a closed pipe: the submission exited or
        # crashed mid-protocol. That is a rejected run, not a broken judge.
        v = _exit_verdict(src)
        return False, (f"{v} (during interaction)" if v
                       else f"{WA} (stopped responding)"), elapsed
    if vrc == 43:
        msg = _read_feedback(fb)
        # A submission that crashed mid-interaction shows up as a validator
        # reject; report the crash, which is what actually happened.
        if src not in (0, None) and src != -signal.SIGPIPE:
            v = _exit_verdict(src)
            if elapsed >= tl:
                return False, TLE, elapsed
            return False, f"{v} (during interaction)", elapsed
        return False, (f"{WA} ({msg})" if msg else WA), elapsed
    err = err_path.read_text(errors="replace") if err_path.exists() else ""
    raise ValidatorError(f"interactor exited {vrc} (expected 42/43): "
                         f"{(err or _read_feedback(fb))[-400:]}")

def evaluate(problem, solution_src, verbose=True, strict_mem=False,
             stop_on_first_failure=True, max_tests=None, which="secret",
             time_limit=None):
    """Grade one submission. ICPC is all-or-nothing: accepted only if every
    test passes, and like a real judge we stop at the first failure."""
    if isinstance(problem, (str, Path)):
        raise TypeError("evaluate() takes a loaded problem, not a path")
    tl = time_limit or problem.time_limit
    if not tl:
        raise ValueError(f"{problem.name}: no time limit")
    tests = problem.tests(which)
    if max_tests:
        tests = tests[:max_tests]
    result = {"contest": problem.contest, "problem": problem.name,
              "title": problem.title, "mode": problem.mode,
              "time_limit_s": tl, "n_tests": len(tests), "tests_run": 0,
              "verdict": None, "accepted": False, "failing_test": None,
              "max_time_s": 0.0, "compile_error": None}
    if not tests:
        result["verdict"] = VE
        result["compile_error"] = "no tests found"
        return result

    workdir = Path(tempfile.mkdtemp(prefix=f"icpc_{problem.contest}_{problem.name}_"))
    try:
        try:
            argv = compile_source(Path(solution_src), workdir / "sol")
        except CompileError as e:
            result["verdict"] = CE
            result["compile_error"] = str(e)
            return result
        validator_argv = build_validator(problem, workdir) if (problem.custom or problem.interactive) else None
        runner = run_interactive_test if problem.interactive else run_batch_test

        for tin, ans in tests:
            ok, verdict, secs = runner(argv, tin, ans, problem, tl, workdir,
                                       validator_argv, strict_mem=strict_mem)
            result["tests_run"] += 1
            result["max_time_s"] = max(result["max_time_s"], round(secs, 3))
            if verbose:
                print(f"    {tin.stem:<40} {verdict:<28} {secs:6.2f}s", flush=True)
            if not ok:
                result["verdict"] = verdict
                result["failing_test"] = tin.stem
                if stop_on_first_failure:
                    return result
        if result["verdict"] is None:
            result["verdict"] = AC
            result["accepted"] = True
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
