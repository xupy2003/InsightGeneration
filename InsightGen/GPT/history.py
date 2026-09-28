"""Scoring, and everything the insight generator is allowed to see of its past.

A round is one insight and the five runs of the target agent that evaluated
it, in runs_gpt/<year>_<slug>/roundNN/ -- the same per-run files as
agent/runs_insight/, plus insight.txt, insight.json and eval.json.

THE SCORE
A run costs the sum of `completion_tokens` over its turns (reasoning
included), the number already used for runs_baseline/ and runs_insight/. An
unsolved run costs FAIL_TOKENS instead. An insight succeeds when both hold:

    passes      >= the editorial arm's passes on this problem       (runs_insight/)
    mean tokens <= TOKEN_BUDGET_FACTOR x the editorial arm's mean tokens

with the reference arms scored by the same rule, FAIL_TOKENS included. Among
the successes, the shortest insight (in the target's tokenizer) is the best.

WHAT THE GENERATOR IS SHOWN
The render_* methods below are the only view it gets. They show what the
agent itself saw -- verdicts as the judge worded them, its own submissions and
the approach line it recorded -- and the token counts. Never the agent's
reasoning, and never the judge's internals (failing test, tests run, slowest
time), which agent/store.py keeps for analysis and withholds from the agent
for the same reason. Nor the reference arms' numbers: the generator is told
whether each of its insights succeeded and which requirement it missed, not
the thresholds.
"""
import difflib
import json
import re
import statistics
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
AGENT_DIR = GEN_DIR.parents[1] / "agent"

FAIL_TOKENS = 3_000_000
# The token budget is relative to the editorial arm. It was the no-insight arm's
# mean at first, which the FAIL_TOKENS of its unsolved runs pushed into the
# millions on the hard problems -- loose enough that the shortest insight won
# while costing the agent ~8x what the editorial did.
TOKEN_BUDGET_FACTOR = 1.5
TOKEN_RULE = f"mean tokens <= {TOKEN_BUDGET_FACTOR} x editorial arm"
SEEDS = (1, 2, 3, 4, 5)

# A submission is rejected if it copies the reference code in bulk. Pseudocode,
# formulas and single statements are fine; these only catch a pasted block.
LEAK_CHARS = 200        # longest verbatim stretch, whitespace-normalised
LEAK_LINES = 10         # reference lines of >= LEAK_MIN_LINE chars found verbatim
LEAK_MIN_LINE = 20
MAX_RENDER_CHARS = 40000


def slug_of(problem: str) -> str:
    return problem.replace("/", "_")


def round_dir(pdir: Path, k: int) -> Path:
    return pdir / f"round{k:02d}"


def run_file(d: Path, slug: str, seed: int, kind: str) -> Path:
    return d / f"{slug}_run{seed}_{kind}"


def _clip(text: str, limit: int = MAX_RENDER_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (truncated, {len(text) - limit} more characters)"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------------------- scoring

def run_tokens(transcript: Path) -> int:
    """Completion tokens over every turn of one run. Round 0 is the prompt record."""
    return sum(r.get("completion_tokens", 0) for r in _read_jsonl(transcript))


def score_runs(d: Path, slug: str, seeds=SEEDS) -> dict:
    """Pass count and mean scored tokens over the runs in `d`. `missing` lists
    the seeds with no summary yet; the numbers are over the rest."""
    runs, missing = [], []
    for s in seeds:
        sp = run_file(d, slug, s, "summary.json")
        if not sp.exists():
            missing.append(s)
            continue
        summ = json.loads(sp.read_text())
        tok = run_tokens(run_file(d, slug, s, "transcript.jsonl"))
        runs.append({"seed": s, "solved": bool(summ["solved"]), "completion_tokens": tok,
                     "scored_tokens": tok if summ["solved"] else FAIL_TOKENS,
                     "submissions": summ["num_submissions"], "turns": summ["num_rounds"],
                     "stop_reason": summ["stop_reason"],
                     "elapsed_s": round(summ["elapsed_seconds"], 1)})
    return {"passes": sum(r["solved"] for r in runs), "n_runs": len(runs),
            "mean_tokens": statistics.mean(r["scored_tokens"] for r in runs) if runs else None,
            "runs": runs, "missing": missing}


def reference(slug: str, seeds=SEEDS) -> dict:
    """The two thresholds, from the arms already run on this problem."""
    out = {}
    for arm in ("baseline", "insight"):
        sc = score_runs(AGENT_DIR / f"runs_{arm}", slug, seeds)
        if sc["missing"]:
            raise SystemExit(f"{slug}: runs_{arm} has no summary for seeds {sc['missing']}")
        out[arm] = {k: sc[k] for k in ("passes", "n_runs", "mean_tokens")}
    return {"required_passes": out["insight"]["passes"],
            "max_mean_tokens": TOKEN_BUDGET_FACTOR * out["insight"]["mean_tokens"],
            "token_rule": TOKEN_RULE,
            "editorial_arm": out["insight"], "baseline_arm": out["baseline"],
            "fail_tokens": FAIL_TOKENS}


def judge(ev: dict, ref: dict) -> list[str]:
    """The requirements `ev` missed; empty means it succeeded."""
    failed = []
    if ev["passes"] < ref["required_passes"]:
        failed.append("passes")
    if ev["mean_tokens"] > ref["max_mean_tokens"]:
        failed.append("tokens")
    return failed


def pick_best(evals: list[dict]) -> dict | None:
    """Shortest successful insight; ties go to fewer tokens, then the earlier round."""
    ok = [e for e in evals if e["success"]]
    return min(ok, key=lambda e: (e["insight_tokens"], e["mean_tokens"], e["round"])) \
        if ok else None


# --------------------------------------------------------------------------- rules

def rule_problems(insight: str, ref_code: str, earlier: dict[int, str]) -> list[str]:
    """Why `insight` may not be submitted; empty if it may. `earlier` maps each
    evaluated round to its insight: resubmitting one would only resample it."""
    problems = []
    if not insight.strip():
        return ["the insight is empty"]
    a, b = _norm(insight), _norm(ref_code)
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b))
    if m.size > LEAK_CHARS:
        problems.append(
            f"it copies {m.size} consecutive characters of the reference code verbatim "
            f"(limit {LEAK_CHARS}), starting: {a[m.a:m.a + 80]!r}")
    lines = {_norm(l) for l in ref_code.splitlines() if len(l.strip()) >= LEAK_MIN_LINE}
    copied = [l for l in lines if l in a]
    if len(copied) > LEAK_LINES:
        problems.append(f"it contains {len(copied)} lines of the reference code verbatim "
                        f"(limit {LEAK_LINES})")
    for k, prev in sorted(earlier.items()):
        if _norm(prev) == a:
            problems.append(f"it is identical to the round {k} insight")
    return problems


# --------------------------------------------------------------------------- views

_FAILED_WORDS = {"passes": "solved too few runs", "tokens": "mean tokens over budget"}


def _result_word(e: dict) -> str:
    return "success" if e["success"] else \
        "FAILED: " + ", ".join(_FAILED_WORDS[f] for f in e["failed"])


class History:
    """The evaluated rounds of one problem, as the generator may see them."""

    def __init__(self, pdir: Path, slug: str, before_round: int | None = None):
        self.pdir, self.slug = pdir, slug
        evals = [json.loads(p.read_text()) for p in pdir.glob("round*/eval.json")]
        self.evals = sorted((e for e in evals
                             if before_round is None or e["round"] < before_round),
                            key=lambda e: e["round"])

    def _eval(self, k):
        for e in self.evals:
            if e["round"] == k:
                return e
        done = ", ".join(str(e["round"]) for e in self.evals) or "none"
        raise LookupError(f"no evaluated round {k} (evaluated rounds: {done})")

    def render_index(self) -> str:
        if not self.evals:
            return "None yet: this is the first round."
        rows = [" round  length  solved  mean tokens/run  result"]
        for e in self.evals:
            rows.append(f"{e['round']:>6}  {e['insight_tokens']:>6}  "
                        f"{e['passes']:>2}/{e['n_runs']:<3}  {e['mean_tokens']:>15,.0f}  "
                        f"{_result_word(e)}")
        best = pick_best(self.evals)
        rows.append("")
        rows.append(f"Shortest successful insight so far: round {best['round']} "
                    f"({best['insight_tokens']} tokens)." if best else
                    "No insight has succeeded yet.")
        rows.append("")
        rows.append("What you said each one was for:")
        rows += [f"  round {e['round']}: {e['rationale']}" for e in self.evals]
        rows.append("")
        rows.append("Lengths are in the agent's tokenizer. get_insight(round) has the "
                    "text and the per-run results.")
        return "\n".join(rows)

    def render_insight(self, k: int) -> str:
        e = self._eval(k)
        out = [f"Round {k} insight ({e['insight_tokens']} tokens):", "", e["insight"], "",
               f"Your rationale: {e['rationale']}", "",
               f"Runs of the agent with it ({FAIL_TOKENS:,} tokens are scored for an "
               f"unsolved run):",
               " run  solved  completion tokens  submissions  turns  minutes  stopped because"]
        for r in e["runs"]:
            out.append(f"{r['seed']:>4}  {'yes' if r['solved'] else 'no':<6}  "
                       f"{r['completion_tokens']:>17,}  {r['submissions']:>11}  "
                       f"{r['turns']:>5}  {r['elapsed_s'] / 60:>7.1f}  {r['stop_reason']}")
        out.append("")
        out.append(f"Solved {e['passes']}/{e['n_runs']}, mean scored tokens "
                   f"{e['mean_tokens']:,.0f}. Result: {_result_word(e)}.")
        return _clip("\n".join(out))

    def _run_dir(self, k: int, seed: int) -> Path:
        self._eval(k)
        if seed not in SEEDS:
            raise LookupError(f"runs are numbered {SEEDS[0]}..{SEEDS[-1]}")
        return round_dir(self.pdir, k)

    def render_run(self, k: int, seed: int) -> str:
        d = self._run_dir(k, seed)
        summ = json.loads(run_file(d, self.slug, seed, "summary.json").read_text())
        turns = [r for r in _read_jsonl(run_file(d, self.slug, seed, "transcript.jsonl"))
                 if r.get("round", 0) > 0]
        total = sum(t.get("completion_tokens", 0) for t in turns)
        out = [f"Round {k}, run {seed}: {'solved' if summ['solved'] else 'not solved'} "
               f"(stopped because: {summ['stop_reason']}), {len(turns)} turns, "
               f"{summ['num_submissions']} submissions, {total:,} completion tokens, "
               f"{summ['elapsed_seconds'] / 60:.1f} minutes.",
               "", " turn   tokens  what the agent did"]
        for t in turns:
            out.append(f"{t['round']:>5}  {t.get('completion_tokens', 0):>7,}  {_turn_action(t)}")
        out.append("")
        out.append(f"get_submission(round={k}, run={seed}, id=N) shows submission N's code.")
        return _clip("\n".join(out))

    def render_submission(self, k: int, seed: int, sid: int) -> str:
        d = self._run_dir(k, seed)
        for r in _read_jsonl(run_file(d, self.slug, seed, "submissions.jsonl")):
            if r["id"] == sid:
                # The compiler's complaint is what the agent itself was shown.
                ce = (f"\n\nThe compiler said:\n{r['compile_error'][-2000:]}"
                      if r.get("compile_error") else "")
                return _clip(f"Round {k}, run {seed}, submission #{sid}: {r['verdict']}, at "
                             f"{r['elapsed_s'] / 60:.1f} min, {r['code_lines']} lines.\n"
                             f"Approach the agent recorded: {r['approach']}\n\n"
                             f"```cpp\n{r['code'].rstrip()}\n```{ce}")
        raise LookupError(f"run {seed} of round {k} has no submission #{sid}")


def _turn_action(t: dict) -> str:
    decision = t.get("decision")
    if decision == "truncated_retry":
        return "hit the per-turn token cap before calling anything (turn discarded)"
    if decision == "no_tool_call_nudge":
        return "ended the turn without calling a tool (reminded to)"
    if decision == "no_tool_call_ending_contest":
        return "ended without a tool call again: gave up, contest over"
    subs = iter(t.get("submissions", []))
    parts = []
    for c in t.get("tool_calls", []):
        if c.get("error"):
            parts.append(f"{c['name']} (malformed call, not run)")
        elif c["name"] == "submit":
            s = next(subs, None)
            parts.append(f"submit #{s['id']} -> {s['verdict']} | approach: "
                         f"{_norm(s['approach'])[:300]}" if s else "submit (not run)")
        else:
            args = ", ".join(f"{a}={v!r}" for a, v in c.get("arguments", {}).items())
            parts.append(f"{c['name']}({args[:100]})")
    return "; ".join(parts) or "(nothing)"
