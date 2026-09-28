"""Insight length against solver output, one point per length rank.

    python3 plot_insight_vs_output.py                       # runs_gpt_v2 -> figures/
    python3 plot_insight_vs_output.py --run-dir <another run dir> --out figures/<name>

Each problem's 10 evaluated insights are sorted by length; rank k is then
averaged over the problems, giving 10 points (mean insight tokens, mean solver
output tokens). A round's output is the actual completion tokens per run,
averaged over its 5 runs -- unsolved runs at what they really cost, no penalty.
Reference lines: the no-insight arm's and the human editorial's mean output,
and the editorial's mean length, all from the same 24 problems.
"""
import argparse
import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

import history as H

BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#52514e"      # series 1, series 2, neutral
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def rank_points(run_dir: Path, problems: list[str]):
    ranks = None
    for p in problems:
        slug = H.slug_of(p)
        evals = H.History(run_dir / slug, slug).evals
        evals = sorted(evals, key=lambda e: (e["insight_tokens"], e["round"]))
        if ranks is None:
            ranks = [[] for _ in evals]
        if len(evals) != len(ranks):
            raise SystemExit(f"{slug}: {len(evals)} evaluated rounds, expected {len(ranks)}")
        for i, e in enumerate(evals):
            ranks[i].append((e["insight_tokens"],
                             st.mean(r["completion_tokens"] for r in e["runs"])))
    xs = [st.mean(x for x, _ in r) for r in ranks]
    ys = [st.mean(y for _, y in r) for r in ranks]
    return xs, ys


def references(run_dir: Path, problems: list[str]):
    base, edit, lens = [], [], []
    for p in problems:
        slug = H.slug_of(p)
        base += H.score_runs(H.AGENT_DIR / "runs_baseline", slug)["runs"]
        edit += H.score_runs(H.AGENT_DIR / "runs_insight", slug)["runs"]
        lens.append(json.loads((run_dir / slug / "reference.json").read_text())["editorial_tokens"])
    mean = lambda runs: st.mean(r["completion_tokens"] for r in runs)
    return mean(base), mean(edit), st.mean(lens)


def k(v):
    if v >= 100_000:
        return f"{v / 1000:.0f}k"
    return f"{v / 1000:.1f}k".replace(".0k", "k") if v >= 1000 else f"{v:.0f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", default="runs_gpt_v2")
    ap.add_argument("--out", default="figures/insight_vs_output")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    run_dir = here / args.run_dir
    problems = (H.AGENT_DIR / "problems.txt").read_text().split()
    xs, ys = rank_points(run_dir, problems)
    base_out, edit_out, edit_len = references(run_dir, problems)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED})
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(45, 1800)
    ax.set_ylim(15_000, 700_000)

    # Reference lines first, so the data line sits on top of them.
    ax.axhline(base_out, color=GRAY, lw=1.2, ls=(0, (6, 3, 1.5, 3)), zorder=1,
               label="No insight (baseline)")
    ax.axhline(edit_out, color=ORANGE, lw=1.2, ls=(0, (5, 3)), zorder=1,
               label="Human-written editorial")
    ax.axvline(edit_len, color=ORANGE, lw=1.2, ls=(0, (1.5, 2.5)), zorder=1)
    ax.plot([edit_len], [edit_out], marker="D", ms=6, color=ORANGE, mec="white", mew=1.2,
            zorder=3, ls="none")

    ax.plot(xs, ys, color=BLUE, lw=1.8, marker="o", ms=6, mec="white", mew=1.2, zorder=4,
            label="GPT-written insights\n(rank-wise mean over 24 problems)")

    # Selective direct labels: the two ends of the line and each reference value.
    ax.annotate("shortest", (xs[0], ys[0]), xytext=(-4, 8), textcoords="offset points",
                ha="right", fontsize=8, color=MUTED)
    ax.annotate("longest", (xs[-1], ys[-1]), xytext=(6, -12), textcoords="offset points",
                ha="left", fontsize=8, color=MUTED)
    ax.text(48, base_out * 1.08, f"No insight: {k(base_out)}", fontsize=8,
            color=MUTED, va="bottom")
    ax.text(330, edit_out * 0.9, f"Human editorial: {k(edit_out)}", fontsize=8,
            color=MUTED, va="top")
    ax.text(edit_len * 0.95, 540_000, f"Human editorial length: {edit_len:,.0f}",
            fontsize=8, color=MUTED, ha="right", va="center")

    xt = [50, 100, 200, 500, 1000]
    yt = [20_000, 50_000, 100_000, 200_000, 500_000]
    ax.xaxis.set_major_locator(FixedLocator(xt))
    ax.yaxis.set_major_locator(FixedLocator(yt))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: k(v)))
    ax.grid(True, color=GRID, lw=0.6, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.set_xlabel("Insight length (tokens, log scale)")
    ax.set_ylabel("Solver output tokens per run (log scale)")
    ax.set_title("Insight length vs. solver output", loc="left", fontsize=10, color=INK)
    leg = ax.legend(loc="center", bbox_to_anchor=(0.6, 0.6), frameon=True,
                    fontsize=8, handlelength=2.6)
    leg.get_frame().set_edgecolor(GRID)

    out = here / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"{out}.{ext}", dpi=300)
    print(f"wrote {out}.png and {out}.pdf")
    for i, (x, y) in enumerate(zip(xs, ys), 1):
        print(f"  rank {i:2d}: insight {x:7.1f} tokens, output {y:9,.0f} tokens")
    print(f"  no insight {base_out:,.0f}; editorial {edit_out:,.0f} output, {edit_len:,.1f} insight tokens")


if __name__ == "__main__":
    main()
