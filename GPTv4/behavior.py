"""A model's behavior profile from its agentv3 runs, and the instructions that correct it
(GPTv3/ErrorAnalysis/behavior.py, copied; the metrics and the instruction texts are unchanged).

The content items of an insight say what the model does not know; the behavior item says how it works
badly. The profile is plain statistics over the run files (no model call): how often it submits and
tests, whether it tests the code it submits, whether it edits or rewrites after a verdict, whether it
calls tools that do not exist, how often its programs fail to compile and what it does then. The failed
runs' profile is compared with a reference -- the same model's solved runs when there are any, else fixed
targets -- and every deficit becomes one instruction, so the text is model-specific by construction
(2026-10-29: Nemotron submits blind and calls a nonexistent Python tool; Qwen rewrites after every compile
error and submits edits it never retested). The engine adds the item only when the grader shows a
behavior-type failure (stalled runs, no submissions, END+fail/other); on 2021/D the instructions alone
solved nothing (0/5 on both models) and GPTv4 does not add them by default.
"""
import json
import re
import statistics as st
from pathlib import Path

TOOLS = ("submit", "run_samples", "list_submissions", "get_submission", "diff_submissions", "search_submissions",
         "list_rounds", "get_reasoning", "search_reasoning")
EDIT_SHARE = 0.5          # consecutive programs sharing at least this share of their 5-token shingles are an edit
# Targets when the model has no solved runs to take the reference from (its solved MA-07 runs: 3-18
# submits, about as many sample tests, most programs edited rather than rewritten).
DEFAULT_REFERENCE = {"submits": 15, "tested_share": 0.8, "edit_share": 0.6, "bad_tools": 0, "ce_share": 0.1,
                     "ce_edit_share": 0.8}
MIN_SUBMITS = 8           # a reference below this (a model that solved in 1-3 submissions) is not a budget to enforce


def _norm(code):
    return re.sub(r"\s+", "", code or "")


def _shingles(code, k=5):
    t = re.findall(r"[A-Za-z_]\w*|\d+|\S", re.sub(r"//[^\n]*", "", code or ""))
    return {tuple(t[i:i + k]) for i in range(max(1, len(t) - k + 1))}


def _similar(a, b):
    return len(a & b) / max(1, len(a | b))


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def profile(trace):
    """One run's behavior metrics, from its transcript, submissions and sample runs."""
    trace = Path(trace)
    recs = _jsonl(trace)
    subs_path = trace.with_name(trace.name.replace("_transcript", "_submissions"))
    samp_path = trace.with_name(trace.name.replace("_transcript", "_samples"))
    summ_path = trace.with_name(trace.name.replace("_transcript.jsonl", "_summary.json"))
    subs = _jsonl(subs_path) if subs_path.exists() else []
    tested = {_norm(r.get("code")) for r in _jsonl(samp_path)} if samp_path.exists() else set()
    solved = json.loads(summ_path.read_text(encoding="utf-8")).get("solved") if summ_path.exists() else None
    turns = [r for r in recs if r.get("round", 0) > 0]
    calls = [c.get("name") or "" for r in turns for c in (r.get("tool_calls") or [])]
    bad = sum(1 for n in calls if n not in TOOLS)
    sh = [_shingles(s.get("code")) for s in subs]
    sims = [_similar(a, b) for a, b in zip(sh, sh[1:])]
    ce = [i for i, s in enumerate(subs) if str(s.get("verdict") or "").startswith("CE")]
    ce_edit = sum(1 for i in ce if i + 1 < len(subs) and sims[i] >= EDIT_SHARE)
    ce_fetch = 0
    for i in ce:
        if i + 1 >= len(subs):
            continue
        a, b = subs[i], subs[i + 1]
        between = [c for r in turns if a.get("round", 0) <= r.get("round", -1) <= b.get("round", 0)
                   for c in (r.get("tool_calls") or [])]
        if any(c.get("name") == "get_submission" and str((c.get("arguments") or {}).get("id")) == str(a.get("id"))
               for c in between):
            ce_fetch += 1
    judged = [s for s in subs if s.get("code") and not str(s.get("verdict") or "").startswith("CE")]
    return {"run": trace.name, "solved": solved, "turns": len(turns), "submits": len(subs),
            "sample_tests": sum(1 for n in calls if n == "run_samples"),
            "tested_share": (sum(_norm(s.get("code")) in tested for s in subs) / len(subs)) if subs else None,
            "final_tested": (_norm(judged[-1]["code"]) in tested) if judged else None,
            "edit_share": (sum(x >= EDIT_SHARE for x in sims) / len(sims)) if sims else None,
            "bad_tools": bad, "bad_tool_names": sorted({n for n in calls if n not in TOOLS})[:5],
            "ce_share": (len(ce) / len(subs)) if subs else None,
            "ce_edit_share": (ce_edit / len(ce)) if ce else None, "ce_fetch_share": (ce_fetch / len(ce)) if ce else None,
            "no_call_turns": sum(1 for r in turns if not r.get("tool_calls"))}


def _median(rows, key):
    xs = [r[key] for r in rows if r.get(key) is not None]
    return st.median(xs) if xs else None


def aggregate(rows):
    """Medians over runs for the metrics an instruction looks at."""
    return {k: _median(rows, k) for k in ("submits", "sample_tests", "tested_share", "edit_share", "bad_tools",
                                           "ce_share", "ce_edit_share", "ce_fetch_share")} | \
        {"final_tested_share": (sum(bool(r["final_tested"]) for r in rows if r["final_tested"] is not None)
                                / max(1, sum(r["final_tested"] is not None for r in rows))), "runs": len(rows)}


def reference(rows):
    """The model's reference profile: its solved runs' medians where it has any, else the defaults."""
    solved = [r for r in rows if r["solved"] is True]
    ref = dict(DEFAULT_REFERENCE)
    if solved:
        agg = aggregate(solved)
        for k in ("submits", "edit_share"):
            if agg.get(k) is not None:
                ref[k] = max(agg[k], MIN_SUBMITS) if k == "submits" else agg[k]
        ref["from_solved_runs"] = len(solved)
    return ref


def instructions(failed, ref):
    """[(metric, line)]: one instruction per deficit of the failed runs' profile against the reference."""
    out = []
    tools = ", ".join(TOOLS)
    if (failed.get("bad_tools") or 0) >= 1:
        out.append(("bad_tools", f"There is no Python interpreter, shell or editor here. The only tools are {tools}; "
                                 "a call to anything else does nothing and wastes the turn."))
    if (failed.get("tested_share") or 0) < 0.5 or failed.get("final_tested_share", 1) < 0.5:
        out.append(("tested_share", "Before every submit, call run_samples on the exact code you are about to submit -- "
                                    "after every edit, not only the first version. Never submit a program that fails a sample; "
                                    "when one fails, print the intermediate values for that sample and compare them with "
                                    "the expected answer before changing anything."))
    if (failed.get("ce_share") or 0) >= 0.2:
        out.append(("ce_share", "A compile error costs a whole turn. After one, call get_submission on that submission and fix "
                                "only the lines the compiler names; do not write the program again."))
    if (failed.get("edit_share") or 0) < min(0.5, ref.get("edit_share", 0.5)):
        out.append(("edit_share", "After a Wrong Answer, keep the current program: fetch it with get_submission, find the one "
                                  "case it gets wrong, and change that part. Rewriting from scratch loses every fix so far."))
    if failed.get("submits") and failed["submits"] > 2 * ref.get("submits", DEFAULT_REFERENCE["submits"]):
        lo, hi = max(3, int(ref["submits"] * 0.6)), int(ref["submits"] * 1.2) + 1
        out.append(("submits", f"Attempts that solved problems like this used about {lo}-{hi} submissions in all. Many more "
                               "means you are guessing: stop submitting and go through the code against the samples instead."))
    return out


PROCEDURE = {   # level 2: the same deficits as one required procedure, for a model that ignored the rules
    "bad_tools": "The tools are exactly {tools}; nothing else exists, so do not call anything else.",
    "ce_share": "Call run_samples on it. If it does not compile, change only the lines the compiler names and return "
                "to step 1.",
    "tested_share": "If a sample fails, print the intermediate values for that sample, compare them with the expected "
                    "answer, fix the program and return to step 1. Do not submit.",
    "edit_share": "After a Wrong Answer, call get_submission on the program, find the one case it gets wrong, change "
                  "that part and return to step 1. Never write the program again from the start.",
    "submits": "Count your submissions: attempts that solved problems like this needed {budget}. Past that, stop "
               "submitting and read the code against the samples instead."}


def text(lines, level=1):
    """The behavior item of an insight. level 1: one rule per deficit; level 2: the same deficits as a
    numbered procedure the model must follow for every program (for a model whose metrics the rules did
    not move)."""
    if not lines:
        return ""
    if level == 1:
        return "How to work on this problem with the tools (from earlier attempts):\n" + "\n".join(f"- {t}" for _, t in lines)
    metrics = {m for m, _ in lines}
    budget = next((re.search(r"about ([\d-]+) submissions", t).group(1) + " submissions" for m, t in lines
                   if m == "submits" and re.search(r"about ([\d-]+) submissions", t)), "few submissions")
    steps = ["Write the program, or edit the current one."]
    steps.append(PROCEDURE["ce_share"] if "ce_share" in metrics else "Call run_samples on it.")
    if "tested_share" in metrics:
        steps.append(PROCEDURE["tested_share"])
    steps.append("Only when every sample passes, call submit with exactly that code.")
    if "edit_share" in metrics:
        steps.append(PROCEDURE["edit_share"])
    out = "Required procedure for every program, without exception:\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(steps, 1))
    if "bad_tools" in metrics:
        out = PROCEDURE["bad_tools"].format(tools=", ".join(TOOLS)) + "\n" + out
    if "submits" in metrics:
        out += "\n" + PROCEDURE["submits"].format(budget=budget)
    return out


def analyze(traces) -> dict:
    """{rows, failed, reference, instructions: [(metric, line)]} for a set of runs' transcripts."""
    rows = [profile(t) for t in traces if Path(t).exists()]
    failed = [r for r in rows if r["solved"] is False]
    agg, ref = aggregate(failed), reference(rows)
    return {"rows": rows, "failed": agg, "reference": ref, "instructions": instructions(agg, ref) if failed else []}
