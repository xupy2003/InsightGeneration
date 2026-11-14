"""The solver: Solver/agentv3 runs on Slurm (ailab, one GPU each), launched as GPTv3/launch_eval.sh did,
waited for, and read back.

A run is `contest.sh` with the environment it expects: PROBLEM, RUN (the seed), ARM (names the job and
the arm), TOOLSET v3, RUNS_DIR, MODEL_PATH, CONDA_ENV, MAX_TOKENS_PER_ROUND, WF_ARCHIVE and, with an
insight, INSIGHT_PICK + INSIGHT_ROOT (contest.sh reads INSIGHT_ROOT/<slug>/<pick>/insight.txt). Without an
insight the run is the baseline arm. Each run writes <slug>_run<N>_{transcript,submissions,reasoning,
samples}.jsonl and _summary.json into RUNS_DIR; a seed with a summary is skipped. The output tokens of a
run are the sum of its rounds' completion_tokens (the transcript): the reasoning tokens the engine wants
to lower.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import config as C
from adapters.problems import slug_of

log = logging.getLogger("gptv4.solver")
FILES = ("transcript.jsonl", "submissions.jsonl", "summary.json", "reasoning.jsonl", "samples.jsonl")


def run_paths(runs_dir: Path, slug: str, seed: int) -> dict:
    return {kind.split(".")[0]: Path(runs_dir) / f"{slug}_run{seed}_{kind}" for kind in FILES}


def done_seeds(runs_dir: Path, slug: str, seeds) -> list:
    return [s for s in seeds if run_paths(runs_dir, slug, s)["summary"].exists()]


def job_name(model: str, slug: str, condition: str, seed: int) -> str:
    return f"g4_{model}_{slug.split('-')[0]}_{condition}_s{seed}"


def sbatch_command(name: str, mem: str, env: dict, dry: bool = False) -> list:
    """The sbatch command of one run; the settings go to the job through --export."""
    exports = "ALL," + ",".join(f"{k}={v}" for k, v in env.items())
    return (["sbatch"] + (["--test-only"] if dry else [])
            + [f"--job-name={name}", f"--mem={mem}", f"--time={C.JOB_TIME}", f"--partition={C.PARTITION}",
               f"--export={exports}", "contest.sh"])


def queued_job(name: str) -> str | None:
    """The id of a job of this name already in the queue, or None."""
    out = subprocess.run(["squeue", "-h", "-u", os.environ.get("USER", ""), "-n", name, "-o", "%i"],
                         capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def submit(cmd: list, name: str, dry: bool = False):
    """sbatch with retries: when the controller is overloaded sbatch prints "Slurm job queue full, sleeping and
    retrying" and still gives up with exit 1 (2023/F Qwen r6, 2026-11-05, which killed the loop); the
    submission is repeated after a pause, up to C.SBATCH_RETRIES times, after checking that the job did not
    get queued after all. Raises after the last failure."""
    for attempt in range(1, C.SBATCH_RETRIES + 1):
        done = subprocess.run(cmd, cwd=C.SOLVER, capture_output=True, text=True)
        if not done.returncode or dry:
            return done
        log.warning(f"{name}: sbatch failed ({done.returncode}), attempt {attempt}/{C.SBATCH_RETRIES}: "
                    f"{done.stderr.strip()[-300:]}")
        time.sleep(C.SBATCH_RETRY_S)
        queued = queued_job(name)
        if queued:
            log.info(f"{name}: queued as {queued} after all")
            return subprocess.CompletedProcess(cmd, 0, stdout=f"Submitted batch job {queued}\n", stderr="")
    raise RuntimeError(f"sbatch failed ({done.returncode}) for {name} after {C.SBATCH_RETRIES} attempts: {done.stderr[-800:]}")


def launch(problem: str, model: str, runs_dir: Path, condition: str, insight_path: Path | None = None,
           seeds=range(1, C.RUNS_PER_ROUND + 1), dry: bool = False) -> list:
    """Submit one job per seed that has no summary yet; returns the job ids ([] when all were done or dry).
    condition names the arm (job names, ARM); the insight is copied to where contest.sh looks for it."""
    spec = C.SOLVERS[model]
    slug = slug_of(problem)
    runs_dir = Path(runs_dir).resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    env = {"REPO": str(C.SOLVER), "PROBLEM": problem, "ARM": condition if insight_path else "baseline",
           "TOOLSET": C.TOOLSET, "RUNS_DIR": str(runs_dir), "MODEL_PATH": str(spec["path"]),
           "CONDA_ENV": spec["conda_env"], "MAX_TOKENS_PER_ROUND": str(C.MAX_TOKENS_PER_ROUND),
           "WF_ARCHIVE": str(C.ICPC_ARCHIVE)}
    if insight_path:
        root = runs_dir / "insight_root"
        target = root / slug / condition / "insight.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(insight_path, target)
        env.update({"INSIGHT_PICK": condition, "INSIGHT_ROOT": str(root)})
    (C.SOLVER / "logs").mkdir(exist_ok=True)
    jobs = []
    for seed in seeds:
        if run_paths(runs_dir, slug, seed)["summary"].exists():
            continue
        name = job_name(model, slug, condition, seed)
        queued = None if dry else queued_job(name)
        if queued:
            log.info(f"{name}: already queued as {queued}")
            jobs.append(queued)
            continue
        cmd = sbatch_command(name, spec["mem"], {**env, "RUN": str(seed)}, dry)
        done = submit(cmd, name, dry)
        m = re.search(r"Submitted batch job (\d+)", done.stdout or "")
        log.info(f"{name}: {'would submit' if dry else 'submitted ' + (m.group(1) if m else '?')}")
        if m:
            jobs.append(m.group(1))
    return jobs


def wait(jobs: list, poll_s: float = C.POLL_S, what: str = "") -> list:
    """Block until none of the jobs is queued or running; returns the jobs that did not COMPLETE."""
    if not jobs:
        return []
    log.info(f"waiting for {what or 'jobs'} ({' '.join(jobs)})")
    while subprocess.run(["squeue", "-h", "-j", ",".join(jobs)], capture_output=True, text=True).stdout.strip():
        time.sleep(poll_s)
    rows = subprocess.run(["sacct", "-n", "-X", "-P", "-j", ",".join(jobs), "-o", "JobID,State"],
                          capture_output=True, text=True).stdout.splitlines()
    failed = [row for row in rows if row and not row.endswith("|COMPLETED")]
    if failed:
        log.warning(f"jobs not completed: {'; '.join(failed)}")
    return failed


def read_run(runs_dir: Path, slug: str, seed: int) -> dict | None:
    """One finished run: outcome, submissions, output tokens (the sum of the rounds' completion tokens),
    rounds, elapsed, and the transcript path; None when it has no summary yet."""
    paths = run_paths(runs_dir, slug, seed)
    if not paths["summary"].exists():
        return None
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    out_tokens, rounds, first_submit_tokens = 0, 0, None
    if paths["transcript"].exists():
        with paths["transcript"].open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("round", 0) <= 0:
                    continue
                rounds += 1
                out_tokens += rec.get("completion_tokens") or 0
                if first_submit_tokens is None and any((c or {}).get("name") == "submit"
                                                       for c in rec.get("tool_calls") or []):
                    first_submit_tokens = out_tokens
    solved = summary.get("solved")
    return {"seed": seed, "solved": bool(solved) if solved is not None else None,
            "submissions": summary.get("num_submissions"), "stop_reason": summary.get("stop_reason"),
            "elapsed_s": summary.get("elapsed_seconds"), "rounds": rounds, "output_tokens": out_tokens,
            "tokens_to_first_submit": first_submit_tokens, "insight": bool(summary.get("insight")),
            "trace": str(paths["transcript"])}


def collect(runs_dir: Path, slug: str, seeds=range(1, C.RUNS_PER_ROUND + 1)) -> list:
    return [r for r in (read_run(runs_dir, slug, s) for s in seeds) if r is not None]


class Solver:
    """The engine's handle on the harness: launch, wait, collect. Tests replace it with a fake."""

    def __init__(self, dry: bool = False):
        self.dry = dry

    def launch(self, problem, model, runs_dir, condition, insight_path=None, seeds=range(1, C.RUNS_PER_ROUND + 1)):
        return launch(problem, model, runs_dir, condition, insight_path, seeds, self.dry)

    def wait(self, jobs, what=""):
        return [] if self.dry else wait(jobs, what=what)

    def collect(self, runs_dir, slug, seeds=range(1, C.RUNS_PER_ROUND + 1)):
        return collect(runs_dir, slug, seeds)
