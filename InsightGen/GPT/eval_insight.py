"""Run the target agent on one problem with one generated insight, once per seed.

    python3 eval_insight.py --problem 2025/J-stacking-cups --model "$MODEL_PATH" \
        --insight-file runs_gpt/2025_J-stacking-cups/round01/insight.txt \
        --out-dir runs_gpt/2025_J-stacking-cups/round01 --seeds 1 2 3 4 5 \
        --time-budget-seconds 3600

Any flag this script does not know is passed to ../../agent/run.py's parser, so
every contest knob has run.py's default unless named here -- the target is the
same agent as in runs_baseline/ and runs_insight/, with only the insight block
changed (agent_prompt.build_problem_message_with_insight).

The model is loaded once and the seeds run one after another. Each run writes
the same three files as runs_insight/, under the same names:

    <year>_<slug>_run<N>_{summary.json,transcript.jsonl,submissions.jsonl}

The summary is written last and atomically, so its presence means the run
finished. A seed whose summary already exists is skipped, which is what lets
the orchestrator resubmit a job that died part-way and have it run only what
is missing.
"""
import argparse
import copy
import json
import sys
import traceback
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(AGENT_DIR))

import agent_prompt as AP  # noqa: E402
import run as R  # noqa: E402
from store import SubmissionStore  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem", required=True, help="<year>/<letter>-<slug>, as in problems.txt")
    ap.add_argument("--model", required=True)
    ap.add_argument("--insight-file", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    own, rest = ap.parse_known_args()
    base = R.build_parser().parse_args(["--problem", own.problem, "--model", own.model] + rest)

    insight_file = Path(own.insight_file).resolve()
    insight = insight_file.read_text().strip()
    if not insight:
        raise SystemExit(f"empty insight: {insight_file}")
    out = Path(own.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = own.problem.replace("/", "_")

    def path(seed, kind):
        return out / f"{slug}_run{seed}_{kind}"

    todo = [s for s in own.seeds if not path(s, "summary.json").exists()]
    print(f"[{own.problem}] insight {len(insight)} chars; seeds to run: {todo}", flush=True)
    if not todo:
        return 0

    llm, tokenizer = R.load_model(base)
    problem_msg, meta = AP.build_problem_message_with_insight(
        R.resolve_problem(own.problem), insight)

    failed = []
    for seed in todo:
        args = copy.copy(base)
        args.seed = seed
        args.transcript = str(path(seed, "transcript.jsonl"))
        args.summary = str(path(seed, "summary.json"))
        args.store = str(path(seed, "submissions.jsonl"))
        print(f"=== seed {seed} ===", flush=True)
        store = SubmissionStore(args.store)
        transcript_f = Path(args.transcript).open("w")
        try:
            R.write_prompt_record(transcript_f, AP.SYSTEM, problem_msg, meta, tokenizer,
                                  insight, insight_file)
            summary = R.run(args, llm, tokenizer, transcript_f, store, problem_msg, meta)
        except Exception:
            # No summary is written, so the orchestrator sees the seed as
            # missing and reruns it rather than scoring a crash as a failure.
            traceback.print_exc()
            failed.append(seed)
            continue
        finally:
            transcript_f.close()
            store.close()
        R.annotate_summary(summary, args, insight)
        summary["insight_file"] = str(insight_file)
        tmp = Path(args.summary + ".tmp")
        tmp.write_text(json.dumps(summary, indent=2))
        tmp.replace(args.summary)
        print(f"seed {seed}: solved={summary['solved']} rounds={summary['num_rounds']} "
              f"stop={summary['stop_reason']}", flush=True)

    if failed:
        print(f"seeds that crashed: {failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
