"""The report of one or more loops (plan.md §4): per problem and model, the baseline and editorial arms
(from RunPool, the current harness's arms when they exist), the key-node control, and the engine's best
and confirmed rounds: solved runs, insight tokens, output tokens of the solved runs; then every round,
and the final insight with each item's node and level.

    python3 report.py                         # every loop under runs/
    python3 report.py --problem 2024/G-kindergarten --model nemotron
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import config as C
from adapters.problems import normalize, slug_of
from adapters.solver_agentv3 import read_run

ARMS = {"baseline": ("agentv3_hard2-baseline", "agentv2_hard-baseline", "agentv2-baseline", "agent-baseline"),
        "editorial": ("agentv3_hard2-editorial", "agentv2_hard-editorial", "agentv2-editorial", "agent-insight")}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs)) if xs else None


def arm_stats(problem: str, model: str, arm: str) -> dict | None:
    """solved, runs, output tokens of the solved runs and of all, from the first RunPool source that has
    the arm (the current harness first)."""
    index = C.RUNPOOL / "index.jsonl"
    if not index.exists():
        return None
    slug = slug_of(problem)
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    for source in ARMS[arm]:
        picked = [r for r in rows if r.get("model") == model and r.get("problem") == slug and r.get("source") == source]
        if not picked:
            continue
        runs = []
        for r in picked:
            run = read_run(C.RUNPOOL / r["dir"], slug, r["run"])
            if run:
                runs.append(run)
        if not runs:
            continue
        return {"source": source, "runs": len(runs), "solved": sum(bool(x["solved"]) for x in runs),
                "solved_output_tokens": _mean([x["output_tokens"] for x in runs if x["solved"]]),
                "output_tokens": _mean([x["output_tokens"] for x in runs])}
    return None


def editorial_tokens(problem: str, model: str) -> int | None:
    """The editorial arm's hint length in the solver's tokens (the text the editorial runs read)."""
    try:
        import tokens as T
        from adapters.problems import Problem
        return T.count(model, Problem(problem).editorial)
    except Exception:
        return None


def loop_rows(runs_root: Path) -> list:
    out = []
    for state_path in sorted(runs_root.glob("*/*/state.json")):
        s = json.loads(state_path.read_text(encoding="utf-8"))
        out.append(s)
    return out


def render(states: list, with_editorial_tokens: bool = False) -> str:
    lines = ["# GPTv4 report", "",
             "| problem | model | baseline | editorial | ed. tokens | keynode ctl | engine best | insight tok | "
             "solved out tok (engine / editorial) | confirm | rounds | status |",
             "|---|---|---|---|---:|---|---|---:|---|---|---:|---|"]
    for s in states:
        base, ed = arm_stats(s["problem"], s["model"], "baseline"), arm_stats(s["problem"], s["model"], "editorial")
        best = s.get("best") or {}
        sc = best.get("score") or {}
        ctl = ((s.get("controls") or {}).get("keynode") or {}).get("score") or {}
        conf = s.get("confirmations") or []
        edtok = editorial_tokens(s["problem"], s["model"]) if with_editorial_tokens else None
        lines.append(
            f"| {s['problem']} | {s['model']} | "
            f"{base['solved']}/{base['runs']} ({base['source'].split('-')[0]}) | " if base else
            f"| {s['problem']} | {s['model']} | - | ")
        lines[-1] += (f"{ed['solved']}/{ed['runs']} | " if ed else "- | ")
        lines[-1] += (f"{edtok} | " if edtok else "- | ")
        lines[-1] += (f"{ctl['solved']}/{ctl['runs']} | " if ctl else "- | ")
        lines[-1] += (f"{sc.get('solved')}/{sc.get('runs')} ({best.get('condition')}) | {best.get('insight_tokens')} | "
                      if best else "- | - | ")
        lines[-1] += (f"{sc.get('solved_output_tokens')} / {ed['solved_output_tokens'] if ed else '-'} | ")
        lines[-1] += (", ".join(f"{c['solved']}/{c.get('runs', sc.get('runs', '?'))}" for c in conf) or "-") + " | "
        lines[-1] += f"{len(s.get('rounds') or [])} | {s.get('stop_reason') or ('phase ' + str(s.get('phase')))} |"
    for s in states:
        lines += ["", f"## {s['problem']} / {s['model']} ({s.get('mode', '?')} mode)", ""]
        if s.get("route"):
            lines.append(f"route {s['route']['index']}: {'+'.join(s['route']['nodes'])} (key {s['route']['key']}); "
                         f"missing at round 0: {', '.join(s['route']['missing'])}; held: {', '.join(s['route']['held']) or 'none'}")
        lines += ["", "| round | phase | solved | END | reached | wrong | insight tok | output tok | solved out tok | accepted | note |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
        for r in s.get("rounds") or []:
            sc = r.get("score") or {}
            note = r["group"]["name"] if r.get("group") else ", ".join(f"{c['item']}:{c['change']}" for c in (r.get("plan") or {}).get("changes") or [])
            lines.append(f"| {r['condition']} | {r['phase']} | {sc.get('solved', '?')}/{sc.get('runs', '?')} | {sc.get('ends', '?')} | "
                         f"{sc.get('reached', '?')} | {sc.get('wrong', '?')} | {r.get('insight_tokens', '?')} | "
                         f"{sc.get('output_tokens', '?')} | {sc.get('solved_output_tokens', '?')} | "
                         f"{'yes' if r.get('accepted') else ('no' if r.get('accepted') is False else '')} | {note} |")
        best = s.get("best")
        if best:
            lines += ["", f"### best insight ({best['condition']}, {best['insight_tokens']} tokens)", ""]
            for iid, it in best["items"].items():
                lines.append(f"- {iid} L{it['level']} ({it.get('tokens')} tok)")
            lines += ["", "```", best["insight"].rstrip(), "```"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem")
    ap.add_argument("--model")
    ap.add_argument("--runs-root", type=Path, default=C.RUNS)
    ap.add_argument("--out", type=Path, help="write the report here (default: stdout)")
    ap.add_argument("--editorial-tokens", action="store_true", help="count the editorial in the solver's tokens (slow)")
    args = ap.parse_args(argv)
    states = loop_rows(args.runs_root)
    if args.problem:
        states = [s for s in states if s["problem"] == normalize(args.problem)]
    if args.model:
        states = [s for s in states if s["model"] == args.model]
    text = render(states, args.editorial_tokens)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
