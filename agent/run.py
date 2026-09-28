"""One ICPC World Finals problem, attempted under contest rules by a local
model acting through tools.

Same contest, same judge and same two arms as the baseline in ../llm. What
changes is where the model's history lives. The baseline replays every earlier
attempt into every prompt and throws the oldest away once the window fills;
here each attempt is written to a submission store the moment the judge
returns, only the last few turns stay in the conversation, and the model calls
a tool when it wants an earlier one back.

    python3 run.py --model <path> --problem 2025/J --seed 1
    python3 run.py --model <path> --problem 2025/J --seed 1 --insight

--insight is unchanged: it adds the problem's own solution.tex write-up to the
problem message and nothing else. Model loading happens before the clock
starts and is not charged against the time budget.

The model has five tools and only one of them changes anything: `submit`
compiles a program and returns the bare verdict, exactly as the baseline's
code-block extraction did. The other four read the store back. See tools.py.
"""

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from vllm import LLM, SamplingParams

import agent_prompt as AP
import prompt as P
from judge import ValidatorError, evaluate
from problem import ARCHIVE_ROOT
from store import SubmissionStore
from tools import (MAX_CALLS_PER_TURN, TOOLS, execute, parse_tool_calls,
                   split_think, strip_code_fences, strip_tool_calls)


TRUNCATED_NUDGE = (
    "(Your previous turn was cut off before you finished it. Nothing was submitted and "
    "no submission was spent. Reason more concisely and end the turn with a tool call.)")

IDLE_NUDGE = (
    "You have now spent {n} rounds in a row without submitting. Reading the store "
    "cannot change the verdict and cannot solve the problem; only `submit` can, and "
    "the clock is running. Decide on a program and send it.")

NO_TOOL_NUDGE = (
    "(Your previous turn ended without a tool call, so nothing happened -- no program "
    "was judged -- and the clock is still running. Call a tool: `submit` if you have a "
    "complete program ready, or `list_submissions` to recall what you have already "
    "tried. If you genuinely have no ideas left, end one more turn without a tool call "
    "and the contest is over.)")


def patch_includes(code: str) -> str:
    """Unchanged from the baseline, so that a program that compiles in one arm
    compiles in the other and the two arms' CE rates mean the same thing."""
    prelude = []
    if "bits/stdc++.h" not in code:
        prelude.append("#include <bits/stdc++.h>")
    if "using namespace std;" not in code and "std::" not in code:
        prelude.append("using namespace std;")
    return "\n".join(prelude) + "\n\n" + code if prelude else code


def count_tokens(tokenizer, messages) -> int:
    """The tool schemas go into the system message, so they are counted here
    too -- without `tools` every measurement would be short by their size and
    the window would be fitted against the wrong number."""
    return len(tokenizer.apply_chat_template(
        messages, tools=TOOLS, tokenize=True, add_generation_prompt=True,
        enable_thinking=True))


# How much of an older turn survives in the window. Measured on the baseline
# transcripts, the bulk of a turn is the program echoed back in the submit
# call (2.3k tokens at p90, 57k at worst) and the visible commentary around it
# (3.1k at p90) -- and the program is already in the store, so replaying it
# into every later prompt is paying twice for the same bytes. An older turn
# keeps its shape, which is what the model needs to follow what it did, and
# hands back a pointer instead of the payload.
ELIDE_CONTENT_CHARS = 400
ELIDE_TOOL_CHARS = 300


def _clip_text(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " [...]"


def _elide_tool_result(call: dict, content: str) -> str:
    """An older tool result, reduced to what cannot be fetched again."""
    if call["name"] == "get_submission" and not call["error"]:
        sid = call["arguments"].get("id")
        return (f"(submission #{sid} was shown here; get_submission(id={sid}) "
                f"returns it again)")
    return _clip_text(content, ELIDE_TOOL_CHARS)


def build_messages(system: str, problem_msg: str, window: list[dict],
                   index_msg: str | None = None) -> list[dict]:
    """system, the problem, the pinned submission index, then the window.

    The system message is not optional: with no system message the chat
    template supplies its own, which says the model is not allowed to use any
    tools.

    The index sits after the problem rather than at the end so that the two
    large pinned blocks stay a stable prefix and keep their prefix-cache
    entries; only the index and the window are re-prefilled each round.

    Everything in the window but the most recent turn is the elided copy.
    """
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": problem_msg}]
    if index_msg:
        messages.append({"role": "user", "content": index_msg})
    for i, turn in enumerate(window):
        messages.extend(turn["full"] if i == len(window) - 1 else turn["elided"])
    return messages


def fit_window(tokenizer, system, problem_msg, turns, keep, max_model_len, threshold,
               index_msg=None):
    """-> (messages, n_tokens, dropped_turns).

    Keep the last `keep` turns, then drop further from the front while the
    prompt is over the threshold. The system message, the problem and the
    index are pinned: a model that cannot see the statement is not attempting
    the same task, and a model with no index is blind at the start of every
    round. Neither is what fills a window -- on these problems the statement
    is about 1k tokens and the index a line per submission. The attempts are.
    """
    k = min(keep, len(turns))
    while True:
        window = turns[len(turns) - k:] if k else []
        messages = build_messages(system, problem_msg, window, index_msg)
        n_tokens = count_tokens(tokenizer, messages)
        if n_tokens <= threshold * max_model_len or k == 0:
            return messages, n_tokens, len(turns) - k
        k -= 1


def grade(problem, code, time_limit, strict_mem=False):
    """Compile and judge one submission. Unchanged from the baseline."""
    if problem.missing_judge:
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
        result = {"verdict": "VE", "accepted": False, "failing_test": None,
                  "n_tests": 0, "tests_run": 0, "max_time_s": 0.0,
                  "compile_error": f"judge error: {e}"}
    finally:
        Path(cpp_path).unlink(missing_ok=True)
    return result, result.get("compile_error") if result["verdict"] == "CE" else None


def resolve_problem(ref: str):
    """`2025/G`, `2025/G-lava-moat`, or a path to the problem directory."""
    return ref if Path(ref).is_dir() else ARCHIVE_ROOT / ref


def run(args, llm, tokenizer, transcript_f, store, problem_msg, meta):
    """One contest. The problem message is built by the caller, once, so the
    round-0 record and the contest are guaranteed to show the same bytes."""
    print(f"Problem: {meta['contest']}/{meta['name']} ({meta['title']}), "
          f"{meta['n_tests']} secret tests, tl={meta['time_limit']}s", flush=True)

    turns: list[dict] = []   # each: {"full": [...], "elided": [...]}
    state = {"submissions": 0, "solved": False, "round": 0}
    tool_counts, format_counts = Counter(), Counter()
    round_submissions: list[dict] = []
    # Where each distinct read-only call was made. A model that re-runs one it
    # already ran is in a loop: the store does not change between submissions,
    # so the answer cannot either. Observed in a real run, and cheap rounds --
    # one of these came back after 162 tokens -- mean the clock does not stop it.
    call_history: dict[tuple, list[int]] = {}
    idle_rounds = 0
    max_prompt_tokens = 0
    t0 = time.time()

    def submit_cb(code: str, approach: str) -> str:
        """The judge, and the only thing a tool call can change."""
        state["submissions"] += 1
        result, ce = grade(meta["problem"], code, meta["time_limit"], args.strict_mem)
        state["solved"] = result["accepted"]
        rec = store.add(code, approach, result, time.time() - t0, state["round"])
        round_submissions.append({"id": rec["id"], "verdict": rec["verdict"],
                                  "accepted": rec["accepted"], "approach": rec["approach"],
                                  "code": code, "grading_result": result})
        print(f"  -> submission #{rec['id']}: {result['verdict']}", flush=True)
        return AP.render_verdict(result, state["submissions"], state["solved"], ce)

    print("Problem shown. Contest clock starts now.", flush=True)
    no_tool_streak = 0
    stop_reason = "time_budget"

    while True:
        elapsed = time.time() - t0
        if state["solved"]:
            stop_reason = "solved"
            break
        if args.time_budget_seconds - elapsed < 60:
            print("Time budget exhausted.", flush=True)
            stop_reason = "time_budget"
            break
        if args.max_rounds and state["round"] >= args.max_rounds:
            print(f"Round limit ({args.max_rounds}) reached.", flush=True)
            stop_reason = "max_rounds"
            break

        index_msg = store.render_pinned_index() if args.history_in_prompt == "index" else None
        messages, n_tokens, dropped = fit_window(
            tokenizer, AP.SYSTEM, problem_msg, turns, args.keep_last_turns,
            args.max_model_len, args.compact_threshold, index_msg)
        max_prompt_tokens = max(max_prompt_tokens, n_tokens)
        gen_max = min(args.max_tokens_per_round, max(256, args.max_model_len - n_tokens - 16))
        state["round"] += 1
        print(f"Round {state['round']}: prompt={n_tokens} tok, {len(turns) - dropped} turn(s) "
              f"in window, {dropped} dropped, elapsed={elapsed/60:.1f}min", flush=True)

        out = llm.chat([messages],
                       SamplingParams(temperature=1.0, top_p=0.95,
                                      max_tokens=gen_max, seed=args.seed),
                       tools=TOOLS,
                       chat_template_kwargs={"enable_thinking": True})[0].outputs[0]
        text, finish = out.text, out.finish_reason
        reasoning, visible = split_think(text)
        calls = parse_tool_calls(visible, accept_code_block=not args.no_code_block_submit)
        rec = {"round": state["round"], "prompt_tokens": n_tokens,
               "completion_tokens": len(out.token_ids), "dropped_turns": dropped,
               "finish_reason": finish, "assistant_raw": text,
               "reasoning_chars": len(reasoning), "content": strip_tool_calls(visible),
               "elapsed_s": time.time() - t0}

        if not calls:
            # Nothing to run. Two different things look like this and they are
            # not the same event: a turn cut off mid-reasoning is an accident
            # of the token budget, while a finished turn with no call is the
            # model saying it is out of ideas -- which is how the baseline's
            # contest ends too.
            if finish == "length":
                rec["decision"] = "truncated_retry"
                transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                transcript_f.flush()
                print("  [truncated before a tool call -- retrying, no submission]", flush=True)
                trunc = [{"role": "assistant", "content": ""},
                         {"role": "user", "content": TRUNCATED_NUDGE}]
                turns.append({"full": trunc, "elided": trunc})
                continue
            no_tool_streak += 1
            if no_tool_streak >= args.max_no_tool_rounds:
                rec["decision"] = "no_tool_call_ending_contest"
                transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                transcript_f.flush()
                print(f"Model ended {no_tool_streak} turns without a tool call. Ending.",
                      flush=True)
                stop_reason = "no_tool_call"
                break
            rec["decision"] = "no_tool_call_nudge"
            transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            transcript_f.flush()
            print("  [no tool call -- nudging]", flush=True)
            nudge = [{"role": "assistant", "content": _clip_text(visible[-2000:], 2000)},
                     {"role": "user", "content": NO_TOOL_NUDGE}]
            turns.append({"full": nudge,
                          "elided": [{"role": "assistant",
                                      "content": _clip_text(visible, ELIDE_CONTENT_CHARS)},
                                     nudge[1]]})
            continue

        no_tool_streak = 0
        idle_rounds = 0 if any(c["name"] == "submit" and not c["error"] for c in calls) \
            else idle_rounds + 1
        dropped_calls = max(0, len(calls) - MAX_CALLS_PER_TURN)
        calls = calls[:MAX_CALLS_PER_TURN]
        for c in calls:
            tool_counts[c["name"]] += 1
            format_counts[c["format"]] += 1
            if c["error"]:
                format_counts["malformed"] += 1

        # A fenced block read as a submit is already in the call arguments; leaving
        # it in the content as well would put the program back into the prompt.
        content = strip_tool_calls(visible)
        if any(c["format"] == "code_block" for c in calls):
            content = strip_code_fences(content)
        assistant_msg = {
            "role": "assistant",
            "content": content,
            "tool_calls": [{"type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"]}}
                           for c in calls]}
        tool_msgs, results = [], []
        round_submissions.clear()
        for c in calls:
            key = (c["name"], json.dumps(c["arguments"], sort_keys=True)[:4000])
            seen = call_history.get(key, [])
            if c["name"] != "submit" and not c["error"] and len(seen) >= 2:
                ok, content = True, (
                    f"You have already made this exact call in rounds "
                    f"{', '.join(map(str, seen))}. It returns the same thing every time -- "
                    f"nothing in the store changes except when you submit -- so it has not "
                    f"been run again. Do something different.")
            else:
                ok, content = execute(c, store, submit_cb)
                if c["name"] != "submit" and not c["error"] and seen:
                    content = (f"(You made this same call in round {seen[-1]}; the answer "
                               f"below is unchanged.)\n" + content)
            call_history.setdefault(key, []).append(state["round"])
            if dropped_calls:
                content += (f"\n(Only the first {MAX_CALLS_PER_TURN} calls of this turn were "
                            f"run; {dropped_calls} were ignored.)")
            content += "\n" + AP.status_footer(
                state["submissions"], time.time() - t0, args.time_budget_seconds,
                len(store), dropped)
            if idle_rounds >= args.max_idle_rounds:
                content += "\n" + IDLE_NUDGE.format(n=idle_rounds)
            tool_msgs.append({"role": "tool", "content": content})
            results.append({"name": c["name"], "ok": ok, "error": c["error"],
                            "format": c["format"], "content": content})
            if state["solved"]:
                break

        # The elided copy of this turn, built now while the submission ids that
        # its pointers refer to are still at hand.
        elided_calls, sub_i = [], 0
        for c in calls:
            eargs = dict(c["arguments"])
            if c["name"] == "submit" and not c["error"] and sub_i < len(round_submissions):
                r = round_submissions[sub_i]
                sub_i += 1
                eargs["code"] = (f"(submission #{r['id']}, {r['code'].count(chr(10)) + 1} lines "
                                 f"-- get_submission(id={r['id']}) to read it)")
            elided_calls.append({"type": "function",
                                 "function": {"name": c["name"], "arguments": eargs}})
        elided = [{"role": "assistant",
                   "content": _clip_text(content, ELIDE_CONTENT_CHARS),
                   "tool_calls": elided_calls}]
        elided += [{"role": "tool", "content": _elide_tool_result(c, m["content"])}
                   for c, m in zip(calls, tool_msgs)]

        # The most recent turn keeps its tool results in full -- it has to, or a
        # fetched submission would be replaced by a pointer before the model got
        # a turn in which to use it, and it would fetch the same thing forever.
        # Its own submitted source is a separate question. Left in, it is what
        # the next round edits: on the baseline transcripts 72% of consecutive
        # submissions are more than half the same text. Taken out, the model has
        # the verdict and its own one-line description of the idea, and has to
        # decide what to write rather than what to patch.
        latest_assistant = (assistant_msg if args.inline_last_code
                            else {**assistant_msg, "tool_calls": elided_calls})

        rec["tool_calls"] = [{"name": c["name"], "format": c["format"], "error": c["error"],
                              "arguments": c["arguments"]} for c in calls]
        rec["tool_results"] = results
        if round_submissions:
            rec["submissions"] = list(round_submissions)
        transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        transcript_f.flush()
        turns.append({"full": [latest_assistant] + tool_msgs, "elided": elided})

    return {"mode": "agent", "problem": f"{meta['contest']}/{meta['name']}",
            "title": meta["title"], "solved": state["solved"], "seed": args.seed,
            "num_submissions": state["submissions"], "num_rounds": state["round"],
            "elapsed_seconds": time.time() - t0, "stop_reason": stop_reason,
            "tool_calls": dict(tool_counts), "tool_call_formats": dict(format_counts),
            "max_prompt_tokens": max_prompt_tokens,
            "repeated_calls": sum(len(v) - 1 for v in call_history.values() if len(v) > 1),
            "turns_total": len(turns), "keep_last_turns": args.keep_last_turns}


def write_prompt_record(transcript_f, system, problem_msg, meta, tokenizer, insight, source):
    """Round 0: what was asked, before the clock starts.

    The same record the baseline writes, plus the system message and the tool
    names -- for an insight run the one thing that has to be checkable
    afterwards is whether the write-up was really in context, and for this arm
    also what the model was allowed to do with it. Round 0 has no assistant
    turn; anything reading the transcript as a list of attempts should skip it.
    """
    rec = {"round": 0,
           "problem": f"{meta['contest']}/{meta['name']}",
           "system": system,
           "prompt": problem_msg,
           "tools": [t["function"]["name"] for t in TOOLS],
           "prompt_tokens": count_tokens(tokenizer, [{"role": "system", "content": system},
                                                     {"role": "user", "content": problem_msg}]),
           "insight": bool(insight),
           "insight_chars": len(insight or ""),
           "insight_source": str(source) if insight else None}
    transcript_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    transcript_f.flush()


def build_parser() -> argparse.ArgumentParser:
    """Every knob of the contest, in one place, so that another driver (the
    insight-generation loop) runs the agent with exactly these defaults."""
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
    ap.add_argument("--keep-last-turns", type=int, default=3,
                    help="turns kept in the conversation. Everything older leaves the "
                         "context entirely and is reachable only through the store. "
                         "Kept turns are cheap: the reasoning is stripped from all of "
                         "them and every turn but the most recent also has its payloads "
                         "replaced by pointers into the store, so an older turn costs "
                         "roughly a hundred tokens. Do not set this to 0 -- a retrieved "
                         "submission would be dropped before the model could act on it, "
                         "and it would fetch the same thing round after round. 1 is the "
                         "smallest setting that works. fit_window() shrinks the window "
                         "further if it still does not fit, so this is an upper bound "
                         "rather than a budget")
    ap.add_argument("--max-rounds", type=int, default=200,
                    help="safety stop. Retrieval turns are cheap in submissions but not "
                         "in wall clock; 0 disables it and leaves the time budget as the "
                         "only limit")
    ap.add_argument("--max-idle-rounds", type=int, default=6,
                    help="consecutive rounds without a submission before every tool "
                         "result carries a reminder that only submit can change "
                         "anything. Retrieval rounds cost no submissions and can come "
                         "back in seconds, so the contest clock is not by itself a "
                         "guard against a model that reads the store in circles")
    ap.add_argument("--max-no-tool-rounds", type=int, default=2,
                    help="consecutive turns with no tool call before the contest ends. "
                         "The baseline ends on the first response with no code block; "
                         "one nudge first is the concession to a format the model can "
                         "miss by accident")
    ap.add_argument("--no-code-block-submit", action="store_true",
                    help="do not read a bare ```cpp block as a submit call. On by "
                         "default because this model reaches for that format over the "
                         "call syntax often enough to stall a run otherwise, and it is "
                         "the same shape the baseline arm reads. Pass this for the "
                         "ablation; the transcript records which form every call "
                         "arrived in either way")
    ap.add_argument("--inline-last-code", action="store_true",
                    help="keep the source of the most recent submission in the prompt. "
                         "Off by default: the program is in the store and the model is "
                         "asked to rethink the algorithm each round rather than edit the "
                         "last one, so leaving the source inline mostly supplies an "
                         "anchor. The model can still call get_submission when it "
                         "genuinely wants to look at an earlier attempt. Turn this on for "
                         "the ablation, or if you want the incremental-repair behaviour "
                         "the baseline arm has by construction")
    ap.add_argument("--history-in-prompt", choices=["index", "none"], default="index",
                    help="`index` pins the submission table into every prompt, refreshed "
                         "each round: id, verdict, length, source hash and the approach "
                         "line, about 30 tokens per submission. Without it a model whose "
                         "turns have left the conversation has to spend a generation on "
                         "list_submissions before it can act, every round. `none` is the "
                         "ablation")
    ap.add_argument("--strict-mem", action="store_true")
    ap.add_argument("--seed", type=int, default=None,
                    help="sampling seed. Repeat runs of the same problem must pass "
                         "different seeds: without one the runs are not reproducible, "
                         "and with the same one they are not independent samples")
    ap.add_argument("--transcript", default="transcript.jsonl")
    ap.add_argument("--summary", default="summary.json")
    ap.add_argument("--store", default="submissions.jsonl",
                    help="the submission store: one JSON object per submission, written "
                         "as the run goes. This is what the model's tools read")
    return ap


def load_model(args):
    """-> (llm, tokenizer). Not charged against the contest clock."""
    print("Loading model (excluded from the contest clock)...", flush=True)
    llm = LLM(model=args.model, trust_remote_code=True, dtype="auto",
              tensor_parallel_size=args.tensor_parallel_size,
              max_model_len=args.max_model_len, kv_cache_dtype="fp8",
              mamba_ssm_cache_dtype="float32", enable_expert_parallel=True,
              enable_chunked_prefill=True, gpu_memory_utilization=0.9,
              max_cudagraph_capture_size=128, async_scheduling=True)
    return llm, llm.get_tokenizer()


def annotate_summary(summary: dict, args, insight: str) -> dict:
    """The run's settings, added to what run() measured."""
    summary["model"] = Path(args.model).resolve().name
    summary["insight"] = bool(insight)
    summary["tensor_parallel_size"] = args.tensor_parallel_size
    summary["max_tokens_per_round"] = args.max_tokens_per_round
    summary["keep_last_turns"] = args.keep_last_turns
    summary["history_in_prompt"] = args.history_in_prompt
    summary["inline_last_code"] = args.inline_last_code
    summary["code_block_submit"] = not args.no_code_block_submit
    summary["store"] = str(Path(args.store).resolve())
    return summary


def main():
    args = build_parser().parse_args()

    problem_dir = resolve_problem(args.problem)
    insight = ""
    if args.insight:
        meta = P.load_problem_meta(problem_dir)
        insight = P.load_insight(meta["dir"])
        if not insight:
            raise SystemExit(f"--insight: no solution.tex under {meta['dir']}")
        print(f"[insight: {len(insight)} chars]", flush=True)

    llm, tokenizer = load_model(args)

    store = SubmissionStore(args.store)
    transcript_f = Path(args.transcript).open("w")
    try:
        problem_msg, meta = AP.build_problem_message(problem_dir, insight=insight or None)
        write_prompt_record(transcript_f, AP.SYSTEM, problem_msg, meta, tokenizer,
                            insight, Path(meta["dir"]) / "solution.tex")
        summary = run(args, llm, tokenizer, transcript_f, store, problem_msg, meta)
    finally:
        transcript_f.close()
        store.close()

    annotate_summary(summary, args, insight)
    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print("=== CONTEST SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
