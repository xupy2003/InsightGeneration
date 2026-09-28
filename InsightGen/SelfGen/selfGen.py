"""Generate a compact insight for an ICPC problem with the target model itself,
in a loop against that same model (../../agent).

    export MODEL_PATH=/scratch/gpfs/PMITTAL/peiyang/px4668/insights/Nemotron-Cascade-2-30B-A3B
    python3 selfGen.py --problems 2025/J-stacking-cups 2021/C-fair-division
    python3 selfGen.py --problem-list ../../agent/problems.txt
    python3 selfGen.py --problems 2025/J --stop-after-round 1          # a one-round pilot
    python3 selfGen.py --problems 2025/J-stacking-cups --show-prompt   # print, run nothing
    python3 selfGen.py --report                                         # collect results

The loop of ../GPT/openaiGen.py with the generator replaced by the agent's own
model. Every problem is its own loop of --rounds rounds, independent of the
others. A round is

  1. generate  A fresh session with the model: the problem as the agent sees
               it, the reference code, the editorial, and the index of its own
               earlier insights, with tools to look into how each one did
               (generate.py, history.py). The message, tools and rules are
               GPT's, except that the model is told the agent is itself. It
               ends when the model calls submit_insight with an insight that
               passes the rules.
  2. evaluate  The same loaded model runs as the agent with the insight on seeds
               1-5, the seeds of runs_baseline/ and runs_insight/.
  3. score     eval.json for the round; insights.jsonl and best.json for the
               problem are rewritten from every round evaluated so far.

Because the generator and the agent are one model, all three run in a Slurm job
on one GPU (job.sh, job.py), and by default one job does every round of a
problem, loading the model once and never going back into the queue.
--rounds-per-job 1 gives a job per round instead. This process only submits the
jobs, watches them, and logs what they finish.

A job that dies leaves what it finished on disk -- insights, seeds, scored
rounds -- and the next job starts at the first step that is missing. A round
gets at most MAX_JOBS_PER_ROUND jobs.

The score and the success rule are in history.py, a verbatim copy of GPT's.
The best insight is the shortest successful one.

Everything lives on disk under --out-dir/<year>_<slug>/, so rerunning the same
command after a crash or a logout resumes where it stopped, and picks up a job
that is still running.
"""
import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import generate as G  # sets WF_ARCHIVE and puts ../../agent on the path
import history as H

from problem import ARCHIVE_ROOT

GEN_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = "/scratch/gpfs/PMITTAL/peiyang/px4668/insights/Nemotron-Cascade-2-30B-A3B"

MAX_JOBS_PER_ROUND = 3    # jobs that may end with a given round unfinished, before giving up
# A job's default wall time: ROUND_HOURS per round it does, at most JOB_HOURS.
# On GPT's runs no problem's ten rounds took a day; a job that runs out is
# resubmitted and resumes.
ROUND_HOURS = 5
JOB_HOURS = 24
TERMINAL_STATES = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "OUT_OF_MEMORY",
                   "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE"}


# --------------------------------------------------------------------------- shared helpers

_tokenizer = None
_tokenizer_lock = threading.Lock()


def n_tokens(text: str, model_path: str) -> int:
    """Length in the target's tokenizer: what the agent pays to read it."""
    global _tokenizer
    with _tokenizer_lock:
        if _tokenizer is None:
            from transformers import AutoTokenizer
            _tokenizer = AutoTokenizer.from_pretrained(model_path)
        return len(_tokenizer.encode(text, add_special_tokens=False))


def canonical(problem: str) -> str:
    """`2025/J` or `2025/J-stacking-cups` -> `2025/J-stacking-cups`, the form the
    reference arms' file names use."""
    problem = problem.strip().strip("/")
    if (ARCHIVE_ROOT / problem).is_dir() and "-" in problem.split("/")[-1]:
        return problem
    year, letter = problem.split("/")[:2]
    hits = sorted((ARCHIVE_ROOT / year).glob(f"{letter.split('-')[0]}-*"))
    if len(hits) != 1:
        raise SystemExit(f"cannot resolve problem {problem!r} under {ARCHIVE_ROOT}")
    return f"{year}/{hits[0].name}"


write_atomic = G.write_atomic


def job_state(job_id: str) -> str | None:
    """Slurm's state for the job, or None when sacct cannot say (yet)."""
    try:
        out = subprocess.run(["sacct", "-j", job_id, "-X", "-n", "-P", "-o", "State"],
                             capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    lines = out.stdout.split()
    return lines[0] if out.returncode == 0 and lines else None


def _logger(slug: str, path: Path) -> logging.Logger:
    lg = logging.getLogger(f"selfgen.{slug}")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        fmt = logging.Formatter(f"%(asctime)s [{slug}] %(message)s", "%m-%d %H:%M:%S")
        for h in (logging.FileHandler(path), logging.StreamHandler(sys.stdout)):
            h.setFormatter(fmt)
            lg.addHandler(h)
    return lg


# --------------------------------------------------------------------------- the record
# Called by job.py on the GPU node, right after a round's last seed.

def score_round(problem: str, pdir: Path, k: int, ref: dict) -> dict:
    """eval.json for round k, from its five runs."""
    rd = H.round_dir(pdir, k)
    sc = H.score_runs(rd, H.slug_of(problem))
    info = json.loads((rd / "insight.json").read_text())
    ev = {"problem": problem, "round": k,
          "insight": (rd / "insight.txt").read_text().strip(),
          "insight_tokens": info["insight_tokens"], "rationale": info["rationale"],
          "passes": sc["passes"], "n_runs": sc["n_runs"], "mean_tokens": sc["mean_tokens"],
          "runs": sc["runs"], "required_passes": ref["required_passes"],
          "max_mean_tokens": ref["max_mean_tokens"]}
    ev["failed"] = H.judge(ev, ref)
    ev["success"] = not ev["failed"]
    write_atomic(rd / "eval.json", json.dumps(ev, indent=2, ensure_ascii=False))
    return ev


def write_results(problem: str, pdir: Path, ref: dict):
    """insights.jsonl and best.json, from every round evaluated so far."""
    evals = H.History(pdir, H.slug_of(problem)).evals
    best = H.pick_best(evals)
    lines = [{"problem": problem, "round": e["round"], "insight": e["insight"],
              "insight_tokens": e["insight_tokens"], "passes": e["passes"],
              "n_runs": e["n_runs"], "mean_tokens": e["mean_tokens"],
              "run_tokens": [r["scored_tokens"] for r in e["runs"]],
              "success": e["success"], "failed": e["failed"],
              "best": best is not None and e["round"] == best["round"]} for e in evals]
    write_atomic(pdir / "insights.jsonl",
                 "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    write_atomic(pdir / "best.json", json.dumps(
        {"problem": problem, "rounds_evaluated": len(evals),
         "best": None if best is None else {
             k: best[k] for k in ("round", "insight", "insight_tokens", "passes",
                                  "n_runs", "mean_tokens")},
         "reference": ref}, indent=2, ensure_ascii=False))


def insight_line(info: dict) -> str:
    return (f"insight of {info['insight_tokens']} tokens after {info['steps']} calls, "
            f"{info['gen_seconds'] / 60:.1f} min -- {info['rationale'][:150]}")


def eval_line(ev: dict) -> str:
    return (f"solved {ev['passes']}/{ev['n_runs']}, mean tokens {ev['mean_tokens']:,.0f}, "
            f"insight {ev['insight_tokens']} tokens -> "
            f"{'SUCCESS' if ev['success'] else 'failed ' + ','.join(ev['failed'])}")


# --------------------------------------------------------------------------- one problem

class ProblemLoop:
    def __init__(self, problem: str, cfg):
        self.problem, self.cfg = problem, cfg
        self.slug = H.slug_of(problem)
        self.pdir = (Path(cfg.out_dir) / self.slug).resolve()
        self.pdir.mkdir(parents=True, exist_ok=True)
        self.log = _logger(self.slug, self.pdir / "loop.log")
        self.problem_msg, self.ref_code, self.editorial = G.load_problem(problem)
        self.last = min(cfg.stop_after_round or cfg.rounds, cfg.rounds)

    def tokens(self, text: str) -> int:
        return n_tokens(text, self.cfg.model_path)

    def reference(self) -> dict:
        path = self.pdir / "reference.json"
        if path.exists():
            ref = json.loads(path.read_text())
            # Every eval.json here was judged against this file's thresholds; a
            # different rule would mix two experiments in one directory.
            rule = ref.get("token_rule", "mean tokens <= baseline arm")
            if rule != H.TOKEN_RULE:
                raise RuntimeError(f"{self.pdir} was scored with '{rule}', not "
                                   f"'{H.TOKEN_RULE}'; use a new --out-dir")
            return ref
        ref = H.reference(self.slug)
        ref["editorial_tokens"] = self.tokens(self.editorial)
        write_atomic(path, json.dumps(ref, indent=2))
        return ref

    def next_round(self) -> int | None:
        for k in range(1, self.last + 1):
            if not (H.round_dir(self.pdir, k) / "eval.json").exists():
                return k
        return None

    def _on_disk(self) -> set:
        """Which insights and scores the jobs have written so far."""
        done = set()
        for k in range(1, self.cfg.rounds + 1):
            rd = H.round_dir(self.pdir, k)
            done |= {(k, f) for f in ("insight.json", "eval.json") if (rd / f).exists()}
        return done

    def _log_new(self, seen: set) -> set:
        now = self._on_disk()
        for k, f in sorted(now - seen, key=lambda x: (x[0], x[1] == "eval.json")):
            doc = json.loads((H.round_dir(self.pdir, k) / f).read_text())
            self.log.info(f"round {k}: " + (insight_line(doc) if f == "insight.json"
                                            else eval_line(doc)))
        return now

    def run(self):
        # Two loops on one problem would overwrite each other's rounds.
        self._lock = (self.pdir / ".lock").open("w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"another selfGen.py is already running {self.problem}")
        ref = self.reference()
        self.log.info(f"target: passes >= {ref['required_passes']}/{len(H.SEEDS)}, mean tokens "
                      f"<= {ref['max_mean_tokens']:,.0f} ({ref['token_rule']}); editorial is "
                      f"{ref['editorial_tokens']} tokens")
        jobs_path = self.pdir / "jobs.json"
        jobs = json.loads(jobs_path.read_text()) if jobs_path.exists() else []
        seen = self._on_disk()                    # logged already, by an earlier run of this
        last_state = None
        while (k := self.next_round()) is not None:
            seen = self._log_new(seen)
            if jobs:
                job = jobs[-1]
                state = job_state(job["job_id"])
                if state != last_state and state is not None:
                    self.log.info(f"job {job['job_id']} (rounds {job['first_round']}-"
                                  f"{job['last_round']}) {state}")
                    last_state = state
                if state not in TERMINAL_STATES:          # pending, running, or not known yet
                    time.sleep(self.cfg.poll_seconds)
                    continue
                seen = self._log_new(seen)                # it may have finished just now
                if (k := self.next_round()) is None:
                    break
                tries = [j for j in jobs if j["first_round"] <= k <= j["last_round"]]
                if tries:
                    self.log.warning(f"job {job['job_id']} ended {state} with round {k} "
                                     f"unfinished; see {self.pdir}/slurm_{job['job_id']}.out")
                if len(tries) >= MAX_JOBS_PER_ROUND:
                    raise RuntimeError(f"round {k}: {len(tries)} jobs ended with it unfinished; "
                                       f"delete {jobs_path.name} to allow new submissions")
            last = min(k + (self.cfg.rounds_per_job or self.last) - 1, self.last)
            jobs.append({"job_id": self.submit_job(k, last), "first_round": k,
                         "last_round": last, "submitted": time.strftime("%Y-%m-%d %H:%M:%S")})
            write_atomic(jobs_path, json.dumps(jobs, indent=2))
            self.log.info(f"job {jobs[-1]['job_id']} submitted: rounds {k}-{last}")
            last_state = None
        self._log_new(seen)
        write_results(self.problem, self.pdir, ref)
        self.log.info("done")

    def submit_job(self, first: int, last: int) -> str:
        env = dict(os.environ)
        env.update(GEN_DIR=str(GEN_DIR), PROBLEM=self.problem, PROBLEM_DIR=str(self.pdir),
                   FIRST_ROUND=str(first), LAST_ROUND=str(last), ROUNDS=str(self.cfg.rounds),
                   MODEL_PATH=self.cfg.model_path,
                   TIME_BUDGET_SECONDS=str(self.cfg.time_budget_seconds),
                   GEN_TIME_SECONDS=str(self.cfg.gen_time_seconds))
        env.pop("GEN_ONLY", None)
        cmd = ["sbatch", "--parsable", f"--job-name=sg_{self.slug[:24]}_r{first:02d}",
               f"--output={self.pdir}/slurm_%j.out", f"--time={self.cfg.slurm_time}",
               f"--partition={self.cfg.partition}", "--export=ALL", str(GEN_DIR / "job.sh")]
        for attempt in range(5):
            out = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if out.returncode == 0:
                return out.stdout.strip().split(";")[0]
            self.log.warning(f"sbatch failed: {out.stderr.strip()}; retrying")
            time.sleep(60 * (attempt + 1))
        raise RuntimeError(f"sbatch kept failing: {out.stderr.strip()}")


# --------------------------------------------------------------------------- the whole set

def report(out_dir: Path):
    """Every problem's insights.jsonl into one file, and a table of the bests."""
    if not out_dir.is_dir():
        raise SystemExit(f"nothing at {out_dir}")
    all_lines = []
    print(f"{'problem':34s} {'rounds':>6s} {'ok':>3s} {'best':>5s} {'len':>6s} {'edit.len':>8s} "
          f"{'best tok':>10s} {'edit. tok':>10s} {'base tok':>10s}")
    for pdir in sorted(p for p in out_dir.iterdir() if p.is_dir()):
        f, rf = pdir / "insights.jsonl", pdir / "reference.json"
        if not f.exists() or not rf.exists():
            continue
        lines = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        ref = json.loads(rf.read_text())
        all_lines += lines
        best = next((x for x in lines if x["best"]), None)
        print(f"{pdir.name:34s} {len(lines):>6d} {sum(x['success'] for x in lines):>3d} "
              f"{best['round'] if best else '-':>5} {best['insight_tokens'] if best else '-':>6} "
              f"{ref['editorial_tokens']:>8d} "
              f"{format(best['mean_tokens'], ',.0f') if best else '-':>10} "
              f"{ref['editorial_arm']['mean_tokens']:>10,.0f} "
              f"{ref['baseline_arm']['mean_tokens']:>10,.0f}")
    write_atomic(out_dir / "all_insights.jsonl",
                 "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in all_lines))
    print(f"\n{len(all_lines)} insights -> {out_dir / 'all_insights.jsonl'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problems", nargs="*", default=[],
                    help="<year>/<letter> or <year>/<letter>-<slug>")
    ap.add_argument("--problem-list", help="a file with one problem per line, like problems.txt")
    ap.add_argument("--rounds", type=int, default=10, help="rounds per problem, the first included")
    ap.add_argument("--stop-after-round", type=int,
                    help="stop each problem after this round, for a pilot; the model is still "
                         "told there are --rounds, and rerunning without it continues")
    ap.add_argument("--rounds-per-job", type=int, default=0,
                    help="rounds one Slurm job does back to back; 0 (the default) is all of a "
                         "problem's rounds in one job, 1 is a job per round")
    ap.add_argument("--out-dir", default=str(GEN_DIR / "runs_self"))
    ap.add_argument("--model-path", default=os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH),
                    help="the checkpoint that both writes the insights and is evaluated "
                         "with them; its tokenizer measures insights")
    ap.add_argument("--time-budget-seconds", type=int, default=3600,
                    help="contest clock for one run of the target")
    ap.add_argument("--gen-time-seconds", type=int, default=7200,
                    help="clock for one generation session; after it the model is told to "
                         "submit and its next call is forced. GPT's session has none")
    ap.add_argument("--slurm-time",
                    help=f"wall time of one job; default {ROUND_HOURS} h per round it does, "
                         f"at most {JOB_HOURS} h. A job that runs out is resubmitted and "
                         f"resumes")
    ap.add_argument("--partition", default="ailab")
    ap.add_argument("--poll-seconds", type=int, default=120)
    ap.add_argument("--stagger-seconds", type=float, default=10,
                    help="delay between starting one problem's loop and the next")
    ap.add_argument("--show-prompt", action="store_true",
                    help="print what the model would be sent next for the first problem, "
                         "and exit without running anything")
    ap.add_argument("--report", action="store_true",
                    help="collect every problem's results into all_insights.jsonl and exit")
    cfg = ap.parse_args()

    out_dir = Path(cfg.out_dir)
    if cfg.report:
        report(out_dir)
        return 0

    problems = list(cfg.problems)
    if cfg.problem_list:
        problems += [x for x in Path(cfg.problem_list).read_text().split() if x]
    problems = list(dict.fromkeys(canonical(p) for p in problems))
    if not problems:
        ap.error("give --problems or --problem-list")
    if not Path(cfg.model_path, "config.json").is_file():
        ap.error(f"no target checkpoint at {cfg.model_path}")
    if str(out_dir.resolve()).startswith("/tmp") and not cfg.show_prompt:
        ap.error("--out-dir must be on a filesystem the compute nodes share; /tmp is not")
    if cfg.slurm_time is None:
        per_job = min(cfg.rounds_per_job or cfg.rounds, cfg.stop_after_round or cfg.rounds)
        hours = min(ROUND_HOURS * per_job, JOB_HOURS)
        cfg.slurm_time = f"{hours // 24}-{hours % 24:02d}:00:00"

    if cfg.show_prompt:
        loop = ProblemLoop(problems[0], cfg)
        k = loop.next_round() or cfg.rounds
        hist = H.History(loop.pdir, loop.slug, k)
        print("=== system ===\n" + G.instructions(cfg.rounds, cfg.time_budget_seconds))
        print(f"\n=== round {k} message ===\n" + G.round_message(
            k, cfg.rounds, loop.problem_msg, loop.ref_code, loop.editorial, hist))
        print("\n=== tools ===\n" + "\n".join(f"{t['function']['name']}: "
                                             f"{t['function']['description']}"
                                             for t in G.TOOLS))
        return 0

    # Hardest first -- by what the agent spent without help -- so that the
    # problems that take a day do not start last, behind the per-user GPU cap.
    loops = [ProblemLoop(p, cfg) for p in problems]
    loops.sort(key=lambda lp: -lp.reference()["baseline_arm"]["mean_tokens"])

    def go(i, loop):
        time.sleep(i * cfg.stagger_seconds)   # not every problem's first sbatch at once
        try:
            loop.run()
            return True
        except Exception:
            loop.log.exception("stopped with an error; rerun the same command to resume")
            return False

    with ThreadPoolExecutor(max_workers=len(loops)) as pool:
        ok = list(pool.map(go, range(len(loops)), loops))
    print(f"{sum(ok)}/{len(ok)} problems finished; results under {out_dir}")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
