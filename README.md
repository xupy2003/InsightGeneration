# GitHub Pages site for InsightGeneration

This branch (`gh-pages`) holds static pages only; the code is on `main`.

| path | what it is |
|---|---|
| `index.html` | landing page listing the pages below |
| `reasoning-graph/index.html` | **Reasoning Graph Pilot**: the four ReasoningGraph Ver2 pilot graphs (2025/J Stacking Cups, 2024/I Steppe on It, 2024/J The Silk Road with Robots, 2025/B Blackboard Game) and their 40 graded solver traces. Self-contained: graphs (SVG), node definitions, per-trace node states with verbatim quotes, hint texts and problem statements are embedded in the file. |
| `insight-evolution/index.html` | **Insight Evolution**: 2024/K Tower of noiHa with Nemotron-Cascade-2-30B-A3B — the same reasoning graph drawn once per condition (no hint, human editorial, engine rounds 1-9, final insight), each node coloured by what the graded runs established, with the stuck node marked. Self-contained. |
| `insight-evolution/source/` | `build_evolution.py` and `template.html`, its generator. Runs inside the research codebase (`InsightGen/GPTv4/`), reading the graph, the gradings of every round and the per-round insight texts. |
| `reasoning-graph/source/` | `build_viewer.py` and `template.html`, the generator of that page. It runs inside the research codebase (`ReasoningGraph/Ver2/`), where it reads `graph/graphs/*/graph.{json,dot}`, `grade/runs/*/pilot/runs.jsonl`, `validate/reports/*/report.json` and the solver transcripts, and renders `graph.dot` with graphviz. |

Live at <https://xupy2003.github.io/InsightGeneration/>.

Each page has its own builder and deploy script in the codebase; both copy this landing page and this
README from `ReasoningGraph/viewer/pages/`, so deploying either keeps both cards.

```bash
# Reasoning Graph Pilot, from ReasoningGraph/
python3 viewer/build_viewer.py && bash viewer/deploy_pages.sh "what changed"

# Insight Evolution, from InsightGen/GPTv4/
python3 viewer/build_evolution.py && bash viewer/deploy_pages.sh "what changed"
```
