"""One ICPC World Finals problem, attempted under contest rules by a local model.

The model is shown the statement, the samples and the limits, and submits C++
to a real judge. It gets back the bare verdict -- AC/WA/TLE/RTE/CE, with no
indication of which test failed -- and may resubmit until it solves the problem
or the clock runs out. Nothing about the loop depends on which model is
running; `--model` is a path to any vLLM-loadable checkpoint.

Two arms, and --insight is the only thing that differs between them:

    python3 run.py --model <path> --problem 2025/G --seed 1
    python3 run.py --model <path> --problem 2025/G --seed 1 --insight

--insight adds one block to the prompt: the problem's own solution.tex
write-up -- the key observations, the algorithm, why it works and its
complexity, and no code. Paired with a baseline run of the same problem and
seed it separates "could not find the idea" from "could not implement it".

Model loading happens before the clock starts and is not charged against the
time budget.
"""

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from vllm import LLM, SamplingParams

import prompt as P
from judge import ValidatorError, evaluate
from problem import ARCHIVE_ROOT

_CODE_RE = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str | None:
    """Last fenced code block, whatever language it claims. A submission in the
    wrong language should reach the compiler and fail there as a real CE, not
    be silently missed and misread as the model declining to submit."""
    matches = _CODE_RE.findall(text)
    return matches[-1][1].strip() if matches else None


def patch_includes(code: str) -> str:
    prelude = []
    if "bits/stdc++.h" not in code:
        prelude.append("#include <bits/stdc++.h>")
    if "using namespace std;" not in code and "std::" not in code:
        prelude.append("using namespace std;")
    return "\n".join(prelude) + "\n\n" + code if prelude else code


def count_tokens(tokenizer, messages) -> int:
    return len(tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, enable_thinking=True))


def build_messages(base_prompt: str, rounds: list[dict]) -> list[dict]:
    messages = [{"role": "user", "content": base_prompt}]
    for r in rounds:
        messages.append({"role": "assistant", "content": r["assistant_raw"]})
        messages.append({"role": "user", "content": r["feedback"]})
    return messages


def compact(rounds: list[dict], keep_last: int) -> list[dict]:
    """Collapse all but the most recent rounds into one-line stubs. Only called
    once the measured prompt crosses the context threshold."""
    if len(rounds) <= keep_last:
        return rounds
    out, cutoff = [], len(rounds) - keep_last
    for i, r in enumerate(rounds):
        if i < cutoff and not r.get("_compacted"):
            out.append({"assistant_raw": "(earlier attempt omitted for brevity)",
                        "feedback": f"[Submission {i + 1}: {r.get('summary', 'n/a')}]",
                        "_compacted": True})
        else:
            out.append(r)
    return out


def grade(problem, code, time_limit, strict_mem=False):
    """Compile and judge one submission.

    The evaluator is handed the loaded problem rather than its path: given a
    path it would try to resolve a Kattis package, which this archive is not.
    The problem also carries its judging mode -- checker, interactor or plain
    comparison -- which is what 13 of the 53 problems need to be graded at all.
    """
    if problem.missing_judge:
        # Never fall through to output comparison. These problems accept more
        # than one correct answer, or are interactive, so comparing against the
        # answer file would reject correct submissions -- and would do it
        # silently, looking exactly like the model getting the problem wrong.
        raise SystemExit(
            f"{problem.contest}/{problem.name} is a {problem.judging_mode} problem and its "
            f"{'interactor' if problem.interactive else 'checker'} is missing from "
            f"{ARCHIVE_ROOT}/_verify/. It cannot be judged without one.")
    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
        f.write(patch_includes(code))
        cpp_path = f.name
    try:
        result = evaluate(problem, cpp_path, verbose=False,
                          strict_mem=strict_mem, time_limit=time_limit)
    except ValidatorError as e:
        # A broken checker is our bug, not the model's; never score it as WA.
        result = {"verdict": "VE", "accepted": False, "failing_test": None,
                  "n_tests": 0, "tests_run": 0, "max_time_s": 0.0,
                  "compile_error": f"judge error: {e}"}
    finally:
        Path(cpp_path).unlink(missing_ok=True)
    return result, result.get("compile_error") if result["verdict"] == "CE" else None


def resolve_problem(ref: str):
    """`2025/G`, `2025/G-lava-moat`, or a path to the problem directory."""
    return ref if Path(ref).is_dir() else ARCHIVE_ROOT / ref


def run(args, llm, tokenizer, transcript_f, insight):
    problem_prompt, meta = P.build_prompt(resolve_problem(args.problem), insight=insight)
    print(f"Problem: {meta['contest']}/{meta['name']} ({meta['title']}), "
          f"{meta['n_tests']} secret tests, tl={meta['time_limit']}s", flush=True)

    rounds, submission_num, solved = [], 0, False
    print("Problem shown. Contest clock starts now.", flush=True)
    t0 = time.time()

    while True:
        elapsed = time.time() - t0
        if args.time_budget_seconds - elapsed < 60:
            print("Time budget exhausted.", flush=True)
            break
        if solved:
            break

        active = rounds
        messages = build_messages(problem_prompt, active)
        n_tokens = count_tokens(tokenizer, messages)
        if n_tokens > args.compact_threshold * args.max_model_len:
            active = compact(rounds, args.keep_last_rounds)
            messages = build_messages(problem_prompt, active)
            n_tokens = count_tokens(tokenizer, messages)
            print(f"  [context compaction -> {n_tokens} tokens]", flush=True)

        gen_max = min(args.max_tokens_per_round, max(256, args.max_model_len - n_tokens - 16))
        print(f"Round {len(rounds) + 1}: prompt={n_tokens} tok, "
              f"elapsed={elapsed/60:.1f}min", flush=True)
        out = llm.chat([messages], SamplingParams(temperature=1.0, top_p=0.95,
                                                  max_tokens=gen_max, seed=args.seed),
                       chat_template_kwargs={"enable_thinking": True})[0].outputs[0]
        text, finish = out.text, out.finish_reason
        code = extract_code(text)
        rec = {"round": len(rounds) + 1, "prompt_tokens": n_tokens,
               "completion_tokens": len(out.token_ids), "assistant_raw": text,
               "finish_reason": finish, "elapsed_s": time.time() - t0}

        if code is None and finish == "length":
            # Cut off mid-reasoning. Not a decision to stop, and it must not
            # burn a submission (a rejection would cost 20 penalty minutes).
            rec["decision"] = "truncated_retry"
            transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); transcript_f.flush()
            print("  [truncated before a code block -- retrying, no submission]", flush=True)
            rounds.append({"assistant_raw": text, "summary": "truncated",
                           "feedback": ("(Your previous response was cut off before you produced "
                                        "a final ```cpp code block. Continue more concisely and "
                                        "end with your solution in a single ```cpp code block.)")})
            continue
        if code is None:
            rec["decision"] = "no_code_block_ending_contest"
            transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); transcript_f.flush()
            print("Model submitted no code block. Ending.", flush=True)
            break

        submission_num += 1
        result, ce = grade(meta["problem"], code, meta["time_limit"], args.strict_mem)
        solved = result["accepted"]
        elapsed_now = time.time() - t0
        feedback = P.render_feedback(result, submission_num, elapsed_now,
                                     args.time_budget_seconds, solved, compile_error=ce)
        print(f"  -> {result['verdict']}", flush=True)
        rec.update({"extracted_code": code, "grading_result": result, "feedback": feedback})
        transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); transcript_f.flush()
        rounds.append({"assistant_raw": text, "feedback": feedback,
                       "summary": result["verdict"]})

    return {"mode": "single", "problem": f"{meta['contest']}/{meta['name']}",
            "title": meta["title"], "solved": solved, "seed": args.seed,
            "num_submissions": submission_num, "num_rounds": len(rounds),
            "elapsed_seconds": time.time() - t0}


def write_prompt_record(transcript_f, prompt_text, meta, tokenizer, insight, source):
    """Record the prompt as round 0, before the contest clock starts.

    The loop records only what the model said, so a finished run would keep no
    copy of what it was asked. For an insight run that is the one thing that
    has to be checkable afterwards -- whether the write-up was really in
    context, and which version of it -- and it makes the two arms diffable
    rather than merely assumed identical.

    Round 0 has no assistant turn: anything reading the transcript as a list of
    attempts should skip it.
    """
    rec = {"round": 0,
           "problem": f"{meta['contest']}/{meta['name']}",
           "prompt": prompt_text,
           "prompt_tokens": count_tokens(tokenizer, [{"role": "user", "content": prompt_text}]),
           "insight": bool(insight),
           "insight_chars": len(insight or ""),
           "insight_source": str(source) if insight else None}
    transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    transcript_f.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem", required=True,
                    help="<year>/<letter>, <year>/<letter>-<slug>, or a path")
    ap.add_argument("--model", required=True)
    ap.add_argument("--insight", action="store_true",
                    help="show the model the problem's solution write-up from "
                         "<problem>/solution.tex: the key observations, the algorithm, "
                         "why it works and its complexity. The implementation is still "
                         "the model's -- the write-up carries no code")
    ap.add_argument("--tensor-parallel-size", type=int, default=1)
    ap.add_argument("--max-model-len", type=int, default=262144)
    ap.add_argument("--max-tokens-per-round", type=int, default=131072)
    ap.add_argument("--time-budget-seconds", type=float, default=7200.0)
    ap.add_argument("--compact-threshold", type=float, default=0.85)
    ap.add_argument("--keep-last-rounds", type=int, default=1,
                    help="rounds kept in full once the context crosses the compaction "
                         "threshold. This and --max-tokens-per-round have to be chosen "
                         "together: if two rounds can fill the context window, the "
                         "threshold is crossed with nothing droppable and every later "
                         "round is left with 256 tokens to generate in. Keep "
                         "max_tokens_per_round x (keep_last_rounds + 1) under ~240k")
    ap.add_argument("--strict-mem", action="store_true")
    ap.add_argument("--seed", type=int, default=None,
                    help="sampling seed. Repeat runs of the same problem must pass "
                         "different seeds: without one the runs are not reproducible, "
                         "and with the same one they are not independent samples")
    ap.add_argument("--transcript", default="transcript.jsonl")
    ap.add_argument("--summary", default="summary.json")
    args = ap.parse_args()

    problem_dir = resolve_problem(args.problem)
    insight = ""
    if args.insight:
        meta = P.load_problem_meta(problem_dir)
        insight = P.load_insight(meta["dir"])
        if not insight:
            # Never fall back to the baseline prompt: that would quietly write a
            # baseline result into the insight results directory, where nothing
            # afterwards could tell the two apart.
            raise SystemExit(f"--insight: no solution.tex under {meta['dir']}")
        print(f"[insight: {len(insight)} chars]", flush=True)

    print("Loading model (excluded from the contest clock)...", flush=True)
    llm = LLM(model=args.model, trust_remote_code=True, dtype="auto",
              tensor_parallel_size=args.tensor_parallel_size,
              max_model_len=args.max_model_len, kv_cache_dtype="fp8",
              mamba_ssm_cache_dtype="float32", enable_expert_parallel=True,
              enable_chunked_prefill=True, gpu_memory_utilization=0.9,
              max_cudagraph_capture_size=128, async_scheduling=True)
    tokenizer = llm.get_tokenizer()

    transcript_f = Path(args.transcript).open("w")
    try:
        prompt_text, meta = P.build_prompt(problem_dir, insight=insight or None)
        write_prompt_record(transcript_f, prompt_text, meta, tokenizer,
                            insight, Path(meta["dir"]) / "solution.tex")
        summary = run(args, llm, tokenizer, transcript_f, insight or None)
    finally:
        transcript_f.close()

    summary["model"] = Path(args.model).resolve().name
    summary["insight"] = bool(insight)
    summary["tensor_parallel_size"] = args.tensor_parallel_size
    summary["max_tokens_per_round"] = args.max_tokens_per_round
    summary["keep_last_rounds"] = args.keep_last_rounds
    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print("=== CONTEST SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
