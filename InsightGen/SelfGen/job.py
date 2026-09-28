"""One Slurm job on one GPU: rounds FIRST..LAST of one problem, back to back,
with one model load. Submitted by selfGen.py through job.sh.

    python3 job.py --problem 2025/J-stacking-cups --model "$MODEL_PATH" \
        --problem-dir runs_self/2025_J-stacking-cups --first-round 1 --last-round 10 \
        --rounds 10 --time-budget-seconds 3600

For each round in the range that has no eval.json yet:

  1. generate  If the round has no insight.txt, the generation session
               (generate.py) writes it: a fresh session, over every round
               evaluated before it.
  2. evaluate  Every seed without a summary is run exactly as
               ../GPT/eval_insight.py runs it, on the same loaded engine.
  3. score     eval.json, then the problem's insights.jsonl and best.json.

insight.txt, each summary and eval.json are written last and atomically, so
their presence means that step finished. A job that dies part-way -- a crash,
a node failure, its wall time -- leaves them on disk, and the next job starts
at the first step that is missing. A seed that crashes stops the job before
its round is scored, so that a crash is rerun rather than scored as a failure.

Any flag this script does not know is passed to ../../agent/run.py's parser,
so every contest knob has run.py's default unless named here, and the
generation session uses the same window, per-turn cap and compaction threshold
as the contest. Each run writes the same three files as runs_insight/:

    <year>_<slug>_run<N>_{summary.json,transcript.jsonl,submissions.jsonl}

The contest clock is a hard limit here. run.py checks it only between turns,
so a turn begun with a minute left runs to its end; here the generation in
flight is cut at the deadline (hard_deadline below), and the run stops there.
"""
import argparse
import copy
import json
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import generate as G  # sets WF_ARCHIVE and puts ../../agent on the path
import history as H
import selfGen as S

import agent_prompt as AP
import run as R
from store import SubmissionStore
from vllm.sampling_params import RequestOutputKind, SamplingParams


def hard_deadline(llm):
    """Give this LLM instance a `deadline` (time.time(), or None for none).

    Past it, the request in flight is aborted and comes back as a turn cut by
    the token cap: finish_reason "length", every token generated so far counted,
    and only the reasoning kept, so that nothing after the cut can be parsed as
    a call and run. run.py then records a truncated turn, finds the clock out
    and ends the contest with stop_reason "time_budget". Each cut is appended
    to `llm.cuts`.

    Prompt rendering is untouched -- the agent still goes through vLLM's own
    chat() -- only the loop that steps the engine is replaced. With no deadline
    set, both functions behave as vLLM's (0.18.1) do.
    """
    llm.deadline, llm.cuts, live = None, [], []
    vllm_run_engine = llm._run_engine

    def _add_request(prompt, params, lora_request=None, priority=0):
        if isinstance(params, SamplingParams):
            # vLLM asks for the final output only; a cut needs the tokens so far.
            params.output_kind = (RequestOutputKind.FINAL_ONLY if llm.deadline is None
                                  else RequestOutputKind.DELTA)
        request_id = str(next(llm.request_counter))
        live.append(request_id)
        return llm.llm_engine.add_request(request_id, prompt, params,
                                          lora_request=lora_request, priority=priority)

    def _run_engine(output_type, *, use_tqdm=True):
        if llm.deadline is None:
            live.clear()
            return vllm_run_engine(output_type, use_tqdm=use_tqdm)
        text, ids, reason = {r: [] for r in live}, {r: [] for r in live}, {}
        while llm.llm_engine.has_unfinished_requests():
            if time.time() >= llm.deadline:
                cut = [r for r in live if r not in reason]
                llm.llm_engine.abort_request(cut)
                for r in cut:
                    raw = "".join(text[r])
                    head, sep, tail = raw.partition("</think>")
                    text[r], reason[r] = [head + sep], "length"
                    llm.cuts.append({"tokens": len(ids[r]), "dropped_chars": len(tail)})
                break
            for out in llm.llm_engine.step():
                o = out.outputs[0]
                text[out.request_id].append(o.text)
                ids[out.request_id].extend(o.token_ids)
                if out.finished:
                    reason[out.request_id] = o.finish_reason
        outs = [SimpleNamespace(request_id=r, outputs=[SimpleNamespace(
                    text="".join(text[r]), token_ids=ids[r], finish_reason=reason[r])])
                for r in live]
        live.clear()
        return outs

    llm._add_request, llm._run_engine = _add_request, _run_engine


def run_seeds(base, llm, tokenizer, problem: str, rd: Path, seeds: list[int]) -> list[int]:
    """The agent with this round's insight, once per seed. -> the seeds that crashed."""
    slug = H.slug_of(problem)
    insight_file = (rd / "insight.txt").resolve()
    insight = insight_file.read_text().strip()
    problem_msg, meta = AP.build_problem_message_with_insight(R.resolve_problem(problem), insight)

    def path(seed, kind):
        return H.run_file(rd, slug, seed, kind)

    failed = []
    for seed in seeds:
        args = copy.copy(base)
        args.seed = seed
        args.transcript = str(path(seed, "transcript.jsonl"))
        args.summary = str(path(seed, "summary.json"))
        args.store = str(path(seed, "submissions.jsonl"))
        print(f"=== round {rd.name[5:]}, seed {seed} ===", flush=True)
        store = SubmissionStore(args.store)
        transcript_f = Path(args.transcript).open("w")
        try:
            R.write_prompt_record(transcript_f, AP.SYSTEM, problem_msg, meta, tokenizer,
                                  insight, insight_file)
            llm.cuts.clear()
            llm.deadline = time.time() + args.time_budget_seconds
            summary = R.run(args, llm, tokenizer, transcript_f, store, problem_msg, meta)
        except Exception:
            traceback.print_exc()
            failed.append(seed)
            continue
        finally:
            llm.deadline = None
            transcript_f.close()
            store.close()
        R.annotate_summary(summary, args, insight)
        summary["insight_file"] = str(insight_file)
        summary["deadline_cut"] = llm.cuts[0] if llm.cuts else None
        tmp = Path(args.summary + ".tmp")
        tmp.write_text(json.dumps(summary, indent=2))
        tmp.replace(args.summary)
        print(f"seed {seed}: solved={summary['solved']} rounds={summary['num_rounds']} "
              f"stop={summary['stop_reason']}", flush=True)
    return failed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem", required=True, help="<year>/<letter>-<slug>, as in problems.txt")
    ap.add_argument("--model", required=True)
    ap.add_argument("--problem-dir", required=True,
                    help="runs_self/<year>_<slug>; must already hold reference.json")
    ap.add_argument("--first-round", type=int, required=True)
    ap.add_argument("--last-round", type=int, required=True)
    ap.add_argument("--rounds", type=int, required=True,
                    help="rounds in the whole loop, the first included; the model is told")
    ap.add_argument("--gen-time-seconds", type=float, default=7200,
                    help="after this long a generation session is told to submit and its "
                         "next call is forced, as after its last step")
    ap.add_argument("--gen-only", action="store_true",
                    help="write the first unfinished round's insight and stop, without "
                         "running the agent")
    own, rest = ap.parse_known_args()
    base = R.build_parser().parse_args(["--problem", own.problem, "--model", own.model] + rest)

    pdir = Path(own.problem_dir).resolve()
    ref = json.loads((pdir / "reference.json").read_text())
    slug = H.slug_of(own.problem)

    def seeds_missing(rd):
        return [s for s in H.SEEDS if not H.run_file(rd, slug, s, "summary.json").exists()]

    todo = [k for k in range(own.first_round, own.last_round + 1)
            if not (H.round_dir(pdir, k) / "eval.json").exists()]
    print(f"[{own.problem}] rounds to do: {todo}", flush=True)
    if not todo:
        return 0

    llm, tokenizer = R.load_model(base)
    hard_deadline(llm)
    for k in todo:
        rd = H.round_dir(pdir, k)
        rd.mkdir(parents=True, exist_ok=True)
        if not (rd / "insight.txt").exists():
            G.generate(llm, tokenizer, own.problem, pdir, k, own.rounds,
                       time_budget_seconds=base.time_budget_seconds,
                       max_model_len=base.max_model_len,
                       max_tokens_per_round=base.max_tokens_per_round,
                       compact_threshold=base.compact_threshold,
                       gen_time_seconds=own.gen_time_seconds,
                       model_name=Path(base.model).resolve().name)
        if own.gen_only:
            return 0
        failed = run_seeds(base, llm, tokenizer, own.problem, rd, seeds_missing(rd))
        if failed:
            print(f"round {k}: seeds {failed} crashed; stopping so they are rerun", flush=True)
            return 1
        ev = S.score_round(own.problem, pdir, k, ref)
        S.write_results(own.problem, pdir, ref)
        print(f"round {k}: {S.eval_line(ev)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
