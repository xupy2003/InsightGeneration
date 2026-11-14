# InsightGeneration

用 reasoning graph 给弱 solver 模型写 model-specific insight：先给一道题建一张“中间结论”图，再按图给 solver 的推理轨迹判分，
找出这个模型自己到不了的节点，只把缺的节点写成提示，用真实 solver run 评测，按判分结果逐轮修改。

| 目录 | 内容 |
|---|---|
| [`ReasoningGraph/`](ReasoningGraph/) | 建图（`graph/explore.py`：explorer 只看题面，每条解法交 judge AC 才成为一条路径；reviewer / integrator 用 editorial 核对和补路）、判分（`grade/`：把 run 的文字逐窗口判成每节点 established / wrong / working / absent）、验证（`validate/`：soundness 与 discrimination）。30 道 ICPC WF 题的图在 `graph/graphs/`。 |
| [`GPTv4/`](GPTv4/) | insight 引擎（`loop.py`）：模型画像 → 选 END route → 逐节点写提示 → 在 Slurm 上跑 solver → 用同一张图判分 → 升级 / 前移 / 压缩 → 确认。 |
| [`Solver/`](Solver/) | solver harness（agentv3）：vLLM 上的工具调用 agent、ICPC judge、`contest.sh`（一个 Slurm 作业 = 一次 2 h 的 run）。 |

设计细节见 [ReasoningGraph/design.md](ReasoningGraph/design.md) 和 [GPTv4/plan.md](GPTv4/plan.md)；每个目录的 README 有完整命令。

## 准备

```bash
pip install -r requirements.txt        # 登录节点：openai、pytest
cp env.example.sh env.sh               # 填 OPENAI_API_KEY、题库、模型、conda、Slurm 设置；env.sh 不进 git
source env.sh
```

需要的外部数据（都不在 repo 里，路径由 `env.sh` 指定）：

- `WF_ARCHIVE`：ICPC WF 题库，每题一个目录（题面、`data/sample`、`data/secret`、`solution.tex`、`solution.cpp`），以及 `_verify/judging.json`。
- `MODELS_DIR`：solver 权重 `Qwen3.6-35B-A3B/`、`Nemotron-Cascade-2-30B-A3B/`；`CONDA_ENVS` 下的 `qwen` / `nemotron` 环境（vLLM、transformers）。
- `RUNPOOL`（可选）：以前的 solver run（`index.jsonl`），GPTv4 用它给模型做无提示画像；没有就先在 GPU 上跑 baseline。

## 检查

```bash
(cd ReasoningGraph && python3 -m pytest -q tests)      # 39 个离线测试（伪 API）
(cd GPTv4 && python3 -m pytest -q tests)               # 40 个离线测试（伪 API、伪 solver、伪 grader）
(cd Solver && python3 -m pytest -q tests)              # 8 个 sample runner 测试（需要 WF_ARCHIVE）
python3 ReasoningGraph/graph/judge.py 2024/K-tower-of-noiha $WF_ARCHIVE/2024/K-tower-of-noiha/solution.cpp   # AC
```

## 运行

```bash
cd ReasoningGraph
python3 graph/explore.py --problems 2025/J-stacking-cups              # 建图（API，20 min–2 h）
python3 grade/grade.py --graph graph/graphs/2025_J-stacking-cups/graph.json --runs '<transcripts>' --out grade/runs/2025_J-stacking-cups/x
python3 validate/validate.py --graph graph/graphs/2025_J-stacking-cups/graph.json --runs grade/runs/2025_J-stacking-cups/x/runs.jsonl --out validate/reports/2025_J-stacking-cups

cd ../GPTv4                                                           # 登录节点、tmux 里跑
python3 loop.py --problem 2024/K-tower-of-noiha --model qwen --dry-run      # 判画像 + 写第 1 轮 insight（调 API），作业只 sbatch --test-only
python3 loop.py --problem 2024/K-tower-of-noiha --model qwen                # 端到端，Ctrl-C 后重跑从 state.json 续
python3 report.py
```

## 不在这个 repo 里的

- 所有运行输出：agent trace、判分记录、验证报告、探索会话、`GPTv4/runs*/`（都已 gitignore，留在原工作目录）。
- AtCoder 的题目加载器（CategoryEval），所以只支持 ICPC WF 题。
- 结果页面（`gh-pages` 分支）的构建脚本。
- 更早的代码（`LLM/`、`agent/`、`InsightGen/` 的 GPT / SelfGen 循环）在 [`legacy`](../../tree/legacy) 分支。
