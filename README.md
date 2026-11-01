# GitHub Pages site for InsightGeneration

This branch (`gh-pages`) holds static pages only; the code is on `main`.

| path | what it is |
|---|---|
| `index.html` | landing page listing the pages below |
| `reasoning-graph/index.html` | **Reasoning Graph Pilot**: the four ReasoningGraph Ver2 pilot graphs (2025/J Stacking Cups, 2024/I Steppe on It, 2024/J The Silk Road with Robots, 2025/B Blackboard Game) and their 40 graded solver traces. Self-contained: graphs (SVG), node definitions, per-trace node states with verbatim quotes, hint texts and problem statements are embedded in the file. |
| `reasoning-graph/source/` | `build_viewer.py` and `template.html`, the generator of that page. It runs inside the research codebase (`ReasoningGraph/Ver2/`), where it reads `graph/graphs/*/graph.{json,dot}`, `grade/runs/*/pilot/runs.jsonl`, `validate/reports/*/report.json` and the solver transcripts, and renders `graph.dot` with graphviz. |

Live at <https://xupy2003.github.io/InsightGeneration/reasoning-graph/>.

To update after graphs or gradings change, from `ReasoningGraph/Ver2/` in the codebase:

```bash
python3 viewer/build_viewer.py && bash viewer/deploy_pages.sh "what changed"
```
