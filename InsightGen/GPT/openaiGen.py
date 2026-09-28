"""Generate a compact insight for an ICPC problem with an OpenAI model, in a loop
against the target agent (../../agent).

    export MODEL_PATH=/scratch/gpfs/PMITTAL/peiyang/px4668/insights/Nemotron-Cascade-2-30B-A3B
    python3 openaiGen.py --problems 2025/J-stacking-cups 2021/C-fair-division
    python3 openaiGen.py --problem-list ../../agent/problems.txt
    python3 openaiGen.py --problems 2025/J-stacking-cups --show-prompt   # print, call nothing
    python3 openaiGen.py --report                                         # collect results

Every problem is its own loop, independent of the others and run in its own
thread, of --rounds rounds. A round is:

  1. generate  A fresh session with the model: the problem as the agent sees
               it, the reference code, the editorial, and the index of its own
               earlier insights, with tools to look into how each one did
               (history.py). It ends when the model calls submit_insight with
               an insight that passes the rules.
  2. evaluate  One Slurm job (eval_job.sh) loads the target once and runs it
               with the insight on seeds 1-5, the seeds of runs_baseline/ and
               runs_insight/. A job that dies leaves its finished seeds on
               disk and is resubmitted for the rest.
  3. score     eval.json for the round; insights.jsonl and best.json for the
               problem are rewritten from every round evaluated so far.

The score and the success rule are in history.py. The best insight is the
shortest successful one.

Everything lives on disk under --out-dir/<year>_<slug>/roundNN/, and a round
is only redone from the first step it has not finished, so rerunning the same
command after a crash or a logout resumes where it stopped.
"""
import argparse
import fcntl
import json
import logging
import os
import random
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
CODEBASE = GEN_DIR.parents[1]
os.environ.setdefault("WF_ARCHIVE", str(CODEBASE / "data" / "problems"))
sys.path.insert(0, str(CODEBASE / "agent"))

import openai  # noqa: E402

import agent_prompt as AP  # noqa: E402
import history as H  # noqa: E402
import prompt as P  # noqa: E402
from problem import ARCHIVE_ROOT  # noqa: E402

DEFAULT_MODEL_PATH = "/scratch/gpfs/PMITTAL/peiyang/px4668/insights/Nemotron-Cascade-2-30B-A3B"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

MAX_STEPS = 40            # model calls in one generation session before submit is forced
MAX_FORCED = 5            # forced calls that may still be rejected before the round gives up
MAX_JOBS_PER_ROUND = 3    # Slurm submissions for one round's evaluation, resubmits included
TERMINAL_STATES = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "OUT_OF_MEMORY",
                   "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE"}


INSTRUCTIONS = """You write hints ("insights") for a competitive-programming agent, and improve them over several rounds from measured results.

# The agent

The agent is a language model attempting one ICPC World Finals problem under contest rules. It is shown the problem statement, samples and limits, followed by your insight, exactly like this:

    ## Key insights
    {lead}

    <your insight>

It then works in turns: it reasons, and acts by calling tools. `submit` sends a C++17 program to the judge; four free tools let it look back at its own earlier submissions. The judge returns only a verdict (AC, WA, TLE, RTE or CE) and never says which test failed, and the agent cannot run code before submitting it. A run ends when a submission is accepted, when the agent gives up, or when its {budget_min}-minute clock runs out. Nothing you write reaches the agent except the insight text.

# How an insight is scored

Every insight you submit is evaluated by running the agent on the problem {n_runs} times, independently. Two numbers come out of that:

- solved: how many of the {n_runs} runs ended with an accepted submission;
- mean tokens: the agent's completion tokens per run (its reasoning included, summed over all its turns), averaged over the runs, with an unsolved run counted as {fail:,} tokens.

An insight succeeds if its solved count reaches a required level and its mean tokens stay within a budget. For each insight you are told whether it succeeded and which requirement it missed, but not the thresholds.

The outcome of the whole process is the shortest successful insight over all rounds, with length measured in the agent's tokenizer. So first find an insight that succeeds, then make it as short as you can while it still succeeds. A failed round does not undo an earlier success, which makes it safe to try a much shorter version of something that has worked. {n_runs} runs are a small sample and the token count of a single run varies a lot, so read the numbers with that in mind.

# Rules for the insight

- Do not paste the reference solution or large verbatim parts of it. Pseudocode, formulas, recurrences, key constants and exact algorithmic steps are all allowed. A submission is rejected if it contains more than {leak_chars} consecutive characters of the reference code verbatim, or more than {leak_lines} of its lines.
- The insight must stand on its own. The agent never sees the reference code, the editorial, or anything else you are shown here.

# Each round

You have {rounds} rounds in total. In each you submit exactly one insight, and it is evaluated before the next round begins, in a fresh session like this one. Your memory between rounds is the record of your earlier insights: the index in the message below, and these tools.

- get_insight(round): an earlier insight's full text, and how each run of the agent went with it.
- get_run(round, run): one of those runs turn by turn: tokens per turn, the tools the agent called, and each submission's verdict with the one-line approach the agent recorded for it. The agent's reasoning is not available.
- get_submission(round, run, id): the C++ program the agent submitted.
- check_insight(insight): a draft's length in the agent's tokenizer and whether it passes the rules, without submitting it.
- submit_insight(insight, rationale): submit this round's insight, with a sentence or two on what it is meant to test or change. You will see the rationale in later rounds. An accepted submission ends the round."""


ROUND_MESSAGE = """# Round {k} of {rounds}

<problem>
{problem}
</problem>

<reference_solution>
```cpp
{code}
```
</reference_solution>

<editorial>
{editorial}
</editorial>

<your_insights_so_far>
{index}
</your_insights_so_far>

Write this round's insight and submit it with submit_insight."""

NO_CALL_NUDGE = ("You did not call a tool, so nothing has been submitted. Finish the round "
                 "by calling submit_insight.")
OUT_OF_STEPS = "This round is out of steps. Submit your insight now with submit_insight."


def _fn(name, description, **props):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": props,
                           "required": list(props), "additionalProperties": False}}


_ROUND = {"type": "integer", "description": "an earlier round number"}
_RUN = {"type": "integer", "description": "run number, 1 to 5"}

TOOLS = [
    _fn("get_insight", "An earlier round's insight in full, your rationale for it, and how "
        "each run of the agent went with it.", round=_ROUND),
    _fn("get_run", "One run of the agent with an earlier round's insight, turn by turn: "
        "completion tokens per turn, the tools it called, and each submission's verdict "
        "with the approach the agent recorded. The agent's reasoning is not available.",
        round=_ROUND, run=_RUN),
    _fn("get_submission", "The full C++ source of one submission the agent made in a run, "
        "with its verdict and recorded approach.",
        round=_ROUND, run=_RUN, id={"type": "integer", "description": "submission id"}),
    _fn("check_insight", "Measure a draft without submitting it: its length in the agent's "
        "tokenizer, and whether it passes the rules.",
        insight={"type": "string"}),
    _fn("submit_insight", "Submit this round's insight. If it passes the rules the round "
        "ends and the insight is evaluated; if not, the reason comes back and you can fix "
        "it and submit again.",
        insight={"type": "string",
                 "description": "exactly the text the agent will see under the heading"},
        rationale={"type": "string",
                   "description": "one or two sentences: what this insight tests or changes "
                                  "relative to your earlier ones"}),
]


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


def write_atomic(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


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
    lg = logging.getLogger(f"insightgen.{slug}")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        fmt = logging.Formatter(f"%(asctime)s [{slug}] %(message)s", "%m-%d %H:%M:%S")
        for h in (logging.FileHandler(path), logging.StreamHandler(sys.stdout)):
            h.setFormatter(fmt)
            lg.addHandler(h)
    return lg


# --------------------------------------------------------------------------- one problem

class ProblemLoop:
    def __init__(self, problem: str, cfg, client):
        self.problem, self.cfg, self.client = problem, cfg, client
        self.slug = H.slug_of(problem)
        self.pdir = Path(cfg.out_dir) / self.slug
        self.pdir.mkdir(parents=True, exist_ok=True)
        self.log = _logger(self.slug, self.pdir / "loop.log")
        self.problem_msg, meta = AP.build_problem_message(ARCHIVE_ROOT / problem)
        pd = Path(meta["dir"])
        self.ref_code = (pd / "solution.cpp").read_text()
        self.editorial = P.load_insight(pd)
        if not self.editorial:
            raise SystemExit(f"{problem}: no solution.tex under {pd}")
        self.instructions = INSTRUCTIONS.format(
            lead=AP.GENERATED_INSIGHT_LEAD, budget_min=round(cfg.time_budget_seconds / 60),
            n_runs=len(H.SEEDS), fail=H.FAIL_TOKENS, leak_chars=H.LEAK_CHARS,
            leak_lines=H.LEAK_LINES, rounds=cfg.rounds)

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

    def round_message(self, k: int, hist: H.History) -> str:
        return ROUND_MESSAGE.format(k=k, rounds=self.cfg.rounds, problem=self.problem_msg.strip(),
                                    code=self.ref_code.rstrip(), editorial=self.editorial,
                                    index=hist.render_index())

    def next_round(self) -> int | None:
        for k in range(1, self.cfg.rounds + 1):
            if not (H.round_dir(self.pdir, k) / "eval.json").exists():
                return k
        return None

    def run(self):
        # Two loops on one problem would overwrite each other's rounds.
        self._lock = (self.pdir / ".lock").open("w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"another openaiGen.py is already running {self.problem}")
        ref = self.reference()
        self.log.info(f"target: passes >= {ref['required_passes']}/{len(H.SEEDS)}, mean tokens "
                      f"<= {ref['max_mean_tokens']:,.0f}; editorial is "
                      f"{ref['editorial_tokens']} tokens")
        while (k := self.next_round()) is not None:
            rd = H.round_dir(self.pdir, k)
            rd.mkdir(parents=True, exist_ok=True)
            if not (rd / "insight.txt").exists():
                self.generate(k)
            self.evaluate(k, ref)
            self.write_results(ref)
        self.write_results(ref)
        self.log.info("done")

    # ---- step 1: the model writes an insight

    def generate(self, k: int):
        rd = H.round_dir(self.pdir, k)
        hist = H.History(self.pdir, self.slug, before_round=k)
        earlier = {e["round"]: e["insight"] for e in hist.evals}
        accepted = {}

        def dispatch(name: str, raw: str) -> str:
            try:
                a = json.loads(raw or "{}")
                if name == "get_insight":
                    return hist.render_insight(int(a["round"]))
                if name == "get_run":
                    return hist.render_run(int(a["round"]), int(a["run"]))
                if name == "get_submission":
                    return hist.render_submission(int(a["round"]), int(a["run"]), int(a["id"]))
                if name in ("check_insight", "submit_insight"):
                    text = a["insight"].strip()
                    problems = H.rule_problems(text, self.ref_code, earlier)
                    n = self.tokens(text)
                    if name == "check_insight":
                        return f"{n} tokens. " + ("Passes the rules." if not problems else
                                                  "Would be rejected: " + "; ".join(problems) + ".")
                    if accepted:
                        return "This round's insight was already accepted; this call was ignored."
                    if problems:
                        return ("Rejected, nothing submitted: " + "; ".join(problems) +
                                ". Fix it and call submit_insight again.")
                    accepted.update(insight=text, rationale=" ".join(a["rationale"].split()),
                                    insight_tokens=n)
                    return f"Accepted ({n} tokens). It will now be evaluated."
                return f"error: there is no tool named {name!r}"
            except json.JSONDecodeError as e:
                return f"error: the arguments are not valid JSON ({e})"
            except KeyError as e:
                return f"error: {name} needs the argument {e}"
            except (LookupError, ValueError, TypeError) as e:
                return f"error: {e}"

        self.log.info(f"round {k}: generating ({len(hist.evals)} earlier rounds)")
        usage = Counter()
        input_items = [{"role": "user", "content": self.round_message(k, hist)}]
        prev, forced, no_call, step = None, False, 0, 0
        with (rd / "gpt_session.jsonl").open("a") as log_f:
            def record(obj):
                log_f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
                log_f.flush()

            record({"event": "session_start", "round": k, "model": self.cfg.model,
                    "instructions": self.instructions, "input": input_items,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")})
            while not accepted:
                step += 1
                if step > MAX_STEPS + MAX_FORCED:
                    raise RuntimeError(f"round {k}: no acceptable insight after {step - 1} calls")
                forced = forced or step > MAX_STEPS
                kw = dict(model=self.cfg.model, instructions=self.instructions,
                          input=input_items, tools=TOOLS)
                if prev:
                    kw["previous_response_id"] = prev
                if self.cfg.reasoning_effort:
                    kw["reasoning"] = {"effort": self.cfg.reasoning_effort}
                if forced:
                    kw["tool_choice"] = {"type": "function", "name": "submit_insight"}
                resp = self._create(**kw)
                u = resp.usage
                if u is not None:
                    usage["input_tokens"] += u.input_tokens or 0
                    usage["output_tokens"] += u.output_tokens or 0
                    details = getattr(u, "output_tokens_details", None)
                    usage["reasoning_tokens"] += getattr(details, "reasoning_tokens", 0) or 0
                record({"event": "response", "step": step, "id": resp.id, "status": resp.status,
                        "forced": forced, "usage": u.model_dump() if u is not None else None,
                        "output": [o.model_dump() for o in resp.output]})
                if resp.status == "failed":
                    self.log.warning(f"round {k}: response failed ({resp.error}); retrying")
                    time.sleep(30)
                    continue
                prev = resp.id
                calls = [o for o in resp.output if o.type == "function_call"]
                if not calls:
                    no_call += 1
                    forced = forced or no_call >= 2
                    input_items = [{"role": "user", "content": NO_CALL_NUDGE}]
                    continue
                input_items = []
                for c in calls:
                    out = dispatch(c.name, c.arguments)
                    record({"event": "tool", "step": step, "name": c.name, "call_id": c.call_id,
                            "arguments": c.arguments, "output": out})
                    input_items.append({"type": "function_call_output", "call_id": c.call_id,
                                        "output": out})
                if step == MAX_STEPS and not accepted:
                    input_items.append({"role": "user", "content": OUT_OF_STEPS})

        info = {"round": k, **accepted, "model": self.cfg.model,
                "reasoning_effort": self.cfg.reasoning_effort, "steps": step,
                "usage": dict(usage), "last_response_id": prev,
                "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        write_atomic(rd / "insight.json", json.dumps(info, indent=2, ensure_ascii=False))
        write_atomic(rd / "insight.txt", accepted["insight"] + "\n")   # marks the step done
        self.log.info(f"round {k}: insight of {accepted['insight_tokens']} tokens after "
                      f"{step} calls -- {accepted['rationale'][:150]}")

    def _create(self, **kw):
        """One Responses API call. Rate limits, timeouts and server errors are
        waited out for as long as they last -- a busy API must not end the loop.
        A request the API rejects as malformed is a bug here and is raised at once."""
        attempt = 0
        while True:
            try:
                return self.client.responses.create(**kw)
            except (openai.APIConnectionError, openai.RateLimitError,
                    openai.InternalServerError) as e:
                attempt += 1
                # Jittered, so that the threads a rate limit stopped together do
                # not all come back in the same second.
                wait = min(600, 30 * 2 ** min(attempt - 1, 5)) * random.uniform(0.8, 1.2)
                self.log.warning(f"OpenAI API: {type(e).__name__} (attempt {attempt}): "
                                 f"{str(e)[:300]}; retrying in {wait:.0f}s")
                time.sleep(wait)

    # ---- step 2: the target runs with it

    def evaluate(self, k: int, ref: dict):
        rd = H.round_dir(self.pdir, k)
        jobs_path = rd / "jobs.json"
        jobs = json.loads(jobs_path.read_text()) if jobs_path.exists() else []

        def missing():
            return [s for s in H.SEEDS
                    if not H.run_file(rd, self.slug, s, "summary.json").exists()]

        last_state = None
        while todo := missing():
            if jobs:
                state = job_state(jobs[-1]["job_id"])
                if state != last_state and state is not None:
                    self.log.info(f"round {k}: job {jobs[-1]['job_id']} {state}, "
                                  f"{len(H.SEEDS) - len(todo)}/{len(H.SEEDS)} runs done")
                    last_state = state
                if state not in TERMINAL_STATES:          # pending, running, or not known yet
                    time.sleep(self.cfg.poll_seconds)
                    continue
                todo = missing()                          # it may have finished just now
                if not todo:
                    break
                self.log.warning(f"round {k}: job {jobs[-1]['job_id']} ended {state} with "
                                 f"seeds {todo} unfinished")
                if len(jobs) >= MAX_JOBS_PER_ROUND:
                    raise RuntimeError(f"round {k}: {len(jobs)} jobs and seeds {todo} still "
                                       f"unfinished; see {rd}/slurm_*.out, and delete "
                                       f"{jobs_path.name} there to allow new submissions")
            jobs.append({"job_id": self.submit_job(k, todo), "seeds": todo,
                         "submitted": time.strftime("%Y-%m-%d %H:%M:%S")})
            write_atomic(jobs_path, json.dumps(jobs, indent=2))
            self.log.info(f"round {k}: job {jobs[-1]['job_id']} submitted for seeds {todo}")

        sc = H.score_runs(rd, self.slug)
        info = json.loads((rd / "insight.json").read_text())
        ev = {"problem": self.problem, "round": k,
              "insight": (rd / "insight.txt").read_text().strip(),
              "insight_tokens": info["insight_tokens"], "rationale": info["rationale"],
              "passes": sc["passes"], "n_runs": sc["n_runs"], "mean_tokens": sc["mean_tokens"],
              "runs": sc["runs"], "required_passes": ref["required_passes"],
              "max_mean_tokens": ref["max_mean_tokens"]}
        ev["failed"] = H.judge(ev, ref)
        ev["success"] = not ev["failed"]
        write_atomic(rd / "eval.json", json.dumps(ev, indent=2, ensure_ascii=False))
        self.log.info(f"round {k}: solved {ev['passes']}/{ev['n_runs']}, mean tokens "
                      f"{ev['mean_tokens']:,.0f}, insight {ev['insight_tokens']} tokens -> "
                      f"{'SUCCESS' if ev['success'] else 'failed ' + ','.join(ev['failed'])}")

    def submit_job(self, k: int, seeds: list[int]) -> str:
        rd = H.round_dir(self.pdir, k)
        # The job needs no API key, and some clusters keep a job's environment
        # in the accounting database.
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        env.update(GEN_DIR=str(GEN_DIR), PROBLEM=self.problem,
                   INSIGHT_FILE=str(rd / "insight.txt"), OUT_DIR=str(rd),
                   SEEDS=" ".join(map(str, seeds)), MODEL_PATH=self.cfg.model_path,
                   TIME_BUDGET_SECONDS=str(self.cfg.time_budget_seconds))
        cmd = ["sbatch", "--parsable", f"--job-name=ig_{self.slug[:24]}_r{k:02d}",
               f"--output={rd}/slurm_%j.out", f"--time={self.cfg.slurm_time}",
               f"--partition={self.cfg.partition}", "--export=ALL",
               str(GEN_DIR / "eval_job.sh")]
        for attempt in range(5):
            out = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if out.returncode == 0:
                return out.stdout.strip().split(";")[0]
            self.log.warning(f"sbatch failed: {out.stderr.strip()}; retrying")
            time.sleep(60 * (attempt + 1))
        raise RuntimeError(f"sbatch kept failing: {out.stderr.strip()}")

    # ---- step 3: the record

    def write_results(self, ref: dict):
        evals = H.History(self.pdir, self.slug).evals
        best = H.pick_best(evals)
        lines = [{"problem": self.problem, "round": e["round"], "insight": e["insight"],
                  "insight_tokens": e["insight_tokens"], "passes": e["passes"],
                  "n_runs": e["n_runs"], "mean_tokens": e["mean_tokens"],
                  "run_tokens": [r["scored_tokens"] for r in e["runs"]],
                  "success": e["success"], "failed": e["failed"],
                  "best": best is not None and e["round"] == best["round"]} for e in evals]
        write_atomic(self.pdir / "insights.jsonl",
                     "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
        write_atomic(self.pdir / "best.json", json.dumps(
            {"problem": self.problem, "rounds_evaluated": len(evals),
             "best": None if best is None else {
                 k: best[k] for k in ("round", "insight", "insight_tokens", "passes",
                                      "n_runs", "mean_tokens")},
             "reference": ref}, indent=2, ensure_ascii=False))


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
    ap.add_argument("--model", default="gpt-6-astra")
    ap.add_argument("--reasoning-effort", default="xhigh",
                    help="reasoning.effort: low, medium (the API's default), high, xhigh "
                         "or max; an empty string leaves it to the API")
    ap.add_argument("--out-dir", default=str(GEN_DIR / "runs_gpt"))
    ap.add_argument("--model-path", default=os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH),
                    help="the target checkpoint: its tokenizer measures insights, and the "
                         "evaluation jobs load it")
    ap.add_argument("--time-budget-seconds", type=int, default=3600,
                    help="contest clock for one run of the target")
    ap.add_argument("--slurm-time", default="05:00:00",
                    help="wall time of one evaluation job (five runs and one model load)")
    ap.add_argument("--partition", default="ailab")
    ap.add_argument("--poll-seconds", type=int, default=120)
    ap.add_argument("--stagger-seconds", type=float, default=10,
                    help="delay between starting one problem's loop and the next")
    ap.add_argument("--show-prompt", action="store_true",
                    help="print what the model would be sent next for the first problem, "
                         "and exit without calling anything")
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

    if cfg.show_prompt:
        loop = ProblemLoop(problems[0], cfg, None)
        k = loop.next_round() or cfg.rounds
        print("=== instructions ===\n" + loop.instructions)
        print(f"\n=== round {k} message ===\n"
              + loop.round_message(k, H.History(loop.pdir, loop.slug, k)))
        print("\n=== tools ===\n" + "\n".join(f"{t['name']}: {t['description']}" for t in TOOLS))
        return 0

    client = openai.OpenAI(api_key=OPENAI_API_KEY, timeout=3600, max_retries=3)
    loops = [ProblemLoop(p, cfg, client) for p in problems]

    def go(i, loop):
        time.sleep(i * cfg.stagger_seconds)   # not every problem's first request at once
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
