#!/usr/bin/env python3
"""Summarise an agent-arm sweep across repeat runs.

The stability, per-year and per-problem sections are the same as the
baseline arm's wf_report.py, deliberately: those are the numbers the two arms
have in common and the only ones that can be put side by side.

What this adds is the harness's own health. A solve rate says nothing about
whether the model ever reached the tools it was given, and a run whose calls
all arrived as bare code blocks is the baseline arm with extra steps. Four
numbers say whether the arm did what it claims:

  format      how calls arrived: strict / lenient / repaired / code_block.
              Mostly strict means the tool interface was actually used.
  rounds:subs how many generations each submission cost. The baseline is 1:1
              by construction, so anything above that is what retrieval and
              rethinking are being paid for.
  repeated    read-only calls the model made twice or more. A large number
              means it was circling rather than working.
  prompt      the largest prompt any round saw. This is the number the arm
              exists to hold down.

`--compare <dir>` puts a baseline-arm results directory beside this one on the
numbers that are comparable. It compares nothing else: rounds and prompt sizes
mean different things in the two arms.
"""
import argparse, glob, json, re, statistics as st, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("n_runs", nargs="?", type=int, default=5,
                help="repeats expected per problem (default 5)")
ap.add_argument("-d", "--dir", default="runs_baseline",
                help="results directory (default runs_baseline)")
ap.add_argument("-c", "--compare", default=None,
                help="a baseline-arm results directory to compare solve rates against")
args = ap.parse_args()


def load(d):
    p = Path(d) if Path(d).is_absolute() else REPO / d
    runs, models = defaultdict(dict), Counter()
    for f in sorted(glob.glob(str(p / "*_run*_summary.json"))):
        m = re.search(r"_run(\d+)_summary\.json$", f)
        try:
            s = json.load(open(f))
        except Exception:
            continue                      # a run still being written
        runs[s["problem"]][int(m.group(1))] = s
        models[s.get("model", "unrecorded")] += 1
    return p, runs, models


RESULTS, runs, models = load(args.dir)
if not runs:
    print(f"no results yet in {RESULTS}"); sys.exit(0)
if len(models) > 1:
    # Two models averaged into one directory would make every per-problem
    # number meaningless, and nothing downstream could tell afterwards.
    print(f"!! {RESULTS} holds summaries from more than one model: "
          + ", ".join(f"{m} x{n}" for m, n in models.most_common()) + "\n")

listed = ["wf" + l.strip() for l in open(REPO / "problems.txt") if l.strip()]
N = args.n_runs
done = sum(len(v) for v in runs.values())
model = models.most_common(1)[0][0] if len(models) == 1 else "mixed"
arms = {(d.get("insight"), d.get("inline_last_code"), d.get("history_in_prompt"))
        for v in runs.values() for d in v.values()}
print(f"{RESULTS.name}  model={model}  mode={ {d.get('mode') for v in runs.values() for d in v.values()} }")
if len(arms) > 1:
    print(f"!! mixed configurations in one directory: {arms}")
else:
    ins, inl, hip = arms.pop()
    print(f"配置: insight={ins}  inline_last_code={inl}  history_in_prompt={hip}")
print(f"结果文件 {done}/{len(listed) * N}  (题目 {len(runs)}/{len(listed)})\n")

rows = []
for p in listed:
    v = runs.get(p, {})
    if v:
        rows.append((p, len(v), sum(1 for d in v.values() if d.get("solved")), v))

# --- stability -------------------------------------------------------------
buckets = Counter(k for _, n, k, _ in rows if n == N)
if buckets:
    print(f"=== 稳定性（仅统计已跑满 {N} 次的题）===")
    for k in range(N, -1, -1):
        if buckets[k]:
            tag = {N: "稳定解出", 0: "稳定失败"}.get(k, "不稳定")
            print(f"  {k}/{N} 次解出: {buckets[k]:>3} 题   {tag}")
    tot = sum(buckets.values()); flaky = tot - buckets[N] - buckets[0]
    print(f"  合计 {tot} 题，其中 {flaky} 题结果不一致（{100*flaky/tot:.0f}%）")

# --- by year ---------------------------------------------------------------
print(f"\n=== 按年份（解出次数/总运行次数）===")
by = defaultdict(lambda: [0, 0])
for p, n, k, _ in rows:
    by[p.split("/")[0]][0] += n; by[p.split("/")[0]][1] += k
print(f"{'年份':<28}{'运行':>6}{'解出':>6}{'率':>7}")
for c, (n, k) in sorted(by.items()):
    print(f"{c:<28}{n:>6}{k:>6}{100*k/n:>6.0f}%")
tn = sum(n for _, n, _, _ in rows); tk = sum(k for _, _, k, _ in rows)
print(f"{'总计':<28}{tn:>6}{tk:>6}{100*tk/tn:>6.0f}%")

# --- harness health --------------------------------------------------------
fmt, tools, stop = Counter(), Counter(), Counter()
rounds, subs, ratio, prompts, repeats = [], [], [], [], []
for _, _, _, v in rows:
    for d in v.values():
        fmt.update(d.get("tool_call_formats", {}))
        tools.update(d.get("tool_calls", {}))
        stop[d.get("stop_reason", "?")] += 1
        r, s = d.get("num_rounds", 0), d.get("num_submissions", 0)
        rounds.append(r); subs.append(s)
        if s: ratio.append(r / s)
        prompts.append(d.get("max_prompt_tokens", 0))
        repeats.append(d.get("repeated_calls", 0))

print(f"\n=== harness 健康度（{len(rounds)} 次运行）===")
nf = sum(fmt.values()) or 1
print(f"  工具调用格式   " + "  ".join(f"{k}={v} ({100*v/nf:.0f}%)" for k, v in fmt.most_common()))
print(f"  工具使用       " + "  ".join(f"{k}={v}" for k, v in tools.most_common()))
print(f"  结束原因       " + "  ".join(f"{k}={v}" for k, v in stop.most_common()))
if ratio:
    print(f"  轮/提交        中位 {st.median(ratio):.1f}  均值 {st.mean(ratio):.1f}"
          f"   (baseline 臂按构造是 1.0)")
print(f"  提交次数       中位 {st.median(subs):.0f}  最多 {max(subs)}")
print(f"  最大 prompt    中位 {st.median(prompts):.0f}  最大 {max(prompts)} tok")
print(f"  重复调用       共 {sum(repeats)} 次，{sum(1 for x in repeats if x)} 次运行出现过")

# --- per problem -----------------------------------------------------------
print(f"\n=== 逐题 ===")
print(f"{'题目':<42}{'解出/运行':>10}  {'每次提交次数':<18}{'每次轮数'}")
for p, n, k, v in sorted(rows, key=lambda r: (r[2] / r[1], r[0])):
    cell = lambda key: ",".join(str(v[i].get(key, 0)) if i in v else "-" for i in range(1, N + 1))
    print(f"{p:<42}{k}/{n:<9}  {cell('num_submissions'):<18}{cell('num_rounds')}")

# --- optional comparison ---------------------------------------------------
if args.compare:
    _, other, _ = load(args.compare)
    if not other:
        print(f"\n(no results in {args.compare} to compare against)"); sys.exit(0)
    print(f"\n=== 与 {Path(args.compare).name} 对比（只比两臂语义相同的量）===")
    print(f"{'题目':<42}{'本臂':>10}{'对照':>10}   {'提交数 本/对照'}")
    a_s = a_n = b_s = b_n = 0
    for p, n, k, v in sorted(rows):
        o = other.get(p, {})
        if not o: continue
        ok, on = sum(1 for d in o.values() if d.get("solved")), len(o)
        a_s += k; a_n += n; b_s += ok; b_n += on
        ms = st.median([d.get("num_submissions", 0) for d in v.values()])
        mo = st.median([d.get("num_submissions", 0) for d in o.values()])
        print(f"{p:<42}{k}/{n:<8}{ok}/{on:<8}   {ms:.0f} / {mo:.0f}")
    if a_n and b_n:
        print(f"{'总计':<42}{a_s}/{a_n:<8}{b_s}/{b_n:<8}   "
              f"{100*a_s/a_n:.0f}% vs {100*b_s/b_n:.0f}%")
