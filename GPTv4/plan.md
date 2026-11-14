# GPTv4：基于 reasoning graph 的 model-specific insight 引擎（实施计划，2026-11-03）

目标：对一道求解模型（Qwen3.6-35B-A3B / Nemotron-Cascade-2-30B-A3B，agentv3 harness）解不出的题，自动生成一段 **compact** 的
insight，让它解出来，并且用比 editorial 臂更少的 reasoning token。要求：效果 ≥ editorial / 简单提示；全自动；端到端；引擎核心不绑定 ICPC。

## 0. 现状盘点（本计划建立在这些已有件上）

| 件 | 位置 | 可直接用的接口 |
|---|---|---|
| 求解 harness | `Solver/agentv3` | `run.py --insight-file F`；`contest.sh`（Slurm ailab，1 GPU，2 h）；输出 `<slug>_runN_{transcript,submissions,reasoning,samples}.jsonl + summary.json`；transcript 每轮有 `completion_tokens`（= reasoning token 的度量） |
| 推理图 | `ReasoningGraph/graph` | `explore.py --problems P` 只看题面建 AND-OR 图（30 题已建）；`graph.json`：nodes(statement/accept/routes/traps)、end.routes + keys、hazards、paths/P*.cpp |
| 判分 | `ReasoningGraph/grade` | `grade.py --graph G --runs ... --out D`：每个 run 的 `results[N]`（trajectory、final、claims 带逐字 quote）、`given`、`established`、`reached_end`、`frontier`、`stuck`、`root`、`class`、`implemented`、`code_gap`、`hazards_tripped`、`off_graph`；盲判、终审默认开 |
| 验证 | `ReasoningGraph/validate` | 30 题 309 run：soundness 188/195、discrimination 113/114 → grader 已可作为 loop 的信号源（design.md §5 留的"何时切换"条件已满足） |
| 轨迹池 | `RunPool` | 2485 run，`index.jsonl`（model/problem/source/solved/insight）；每题两模型都有 baseline、editorial、GPT insight 臂 |
| 旧引擎 | `InsightGen/GPTv3` | 可复用：`PricedGuidance/hints.py` 的写作规则与检查（ASCII、COPY_RUN=16、ANSWER_NUMBERS=8、无 `#include`/`main(`）、`tokens.py`（solver 自己的 tokenizer 计数）、`ErrorAnalysis/behavior.py`（行为画像）、`launch_eval.sh` 的 Slurm 模式（路径已失效：agentv3 搬到了 `Solver/`） |
| API | `GeneralGenV2/session.py` 经 `ReasoningGraph/api.py` | gpt-6-astra、strict tool、重试、JSONL 记录 |

GPTv3 留下的结论，GPTv4 直接采纳：
- 自推率 / 逐字计价 / 选择题难度都不预测真实解出 → **唯一的信号是真实 run + grader**。
- 0/5 → 0/5 的轮次在 GPTv3 里没有任何信号，loop 退化成随机游走 → GPTv4 用图上的**进度**（到达的节点深度、END 数）替代单一解出数。
- MA-07 最好轮次都超过"½ editorial"上限，先压缩再删会丢公式精度 → 阶段 1 不设硬上限，靠"只写模型没有的节点"做到紧凑，阶段 2 再做消融压缩。
- 行为指令单独给（beh_only）两模型 2021/D 都 0/5，加在 editorial 上 +1/5 → 行为层只在诊断为行为型失败时才加，不默认加。
- 2025/J Qwen：3 轮 57 词 0/5→5/5；editorial 776 词 → compact 可行；Nemotron 上一直没成 → 需要 model-specific 的 route 和写法。

## 1. 核心思想

把 insight 定义为**图上的一个割**：从该模型在无提示 run 里已经自己到达的节点集 H_M 出发，到某条 END route 的 key node，
缺的那几个节点就是 insight 的内容；每个节点的写法针对该模型在这个节点上的**自己的错误说法**（grader 的 claims/quotes）。
模型不同 → H_M 不同、卡点不同、错误说法不同 → 选的 route、写的节点、措辞都不同，这就是 model-specific 的全部来源，不靠猜。

每轮用真实 agentv3 run（×5）评测，再用**同一张图**判分带提示的 run：
- `given`（insight 送到了哪）vs `established`（模型自己接住了哪）→ 没接住的节点换写法 / 升级；
- 新的 `stuck` / `root` → 下一个要写的节点；
- `hazards_tripped` / `code_gap` / `END+fail` → 实现层条目；
- `stalled` / 零提交 / 盲提交 → 行为层条目（或改 harness）。

进度度量（每轮每个 run，纯离线）：目标 route 上被 held 且无 wrong 的最深节点深度、reached_end 数、solved 数、输出 token。
这让 0/5 的轮次之间也能比较，keep-best 有了梯度。

## 2. 引擎流程（`loop.py`，一条命令端到端）

```
python3 loop.py --problem 2024/G-kindergarten --model nemotron      # 可 --resume；状态在 runs/<slug>/<model>/state.json
```

1. **ensure_graph**：`graph/graphs/<slug>/graph.json` 不存在就调 `ReasoningGraph/graph/explore.py`（新题自动建图）。
2. **round 0**：取该模型无提示 run（RunPool 优先；不足 5 个就用 `launch` 补跑 baseline），判分（已判过的 30 题直接读 `grade/runs/<slug>/pilot/runs.jsonl`）。
   得到模型画像 `profile.json`：每节点 held 率 / wrong 率 / 作为 stuck 的次数、错误说法聚类（traps）、hazards、行为画像（behavior.py）。
3. **diagnose**：
   - **选 route**：对每条 END route 算代价 = Σ_{节点 ∉ H_M} w(节点)，w 由该模型在该节点的 wrong 率和深度定；取最小。两个模型可能选不同 route。
   - **目标集**：route 上 ∉ H_M 的节点，按拓扑序。**2026-11-03 晚改为逐节点给（step 模式）**：第 1 轮只写第一个缺失节点；每轮判分后看前沿
     （第一个在 <3/5 run 里 held 的节点）：前沿仍是刚给的节点 → 升一级，前沿越过它 → 在新前沿加一条等级 1；最后再压缩。
     原来的"第 1 轮全部写再消融"保留为 cut 模式作对照：它第 1 轮就能解出，但盖住了"哪句话让模型过了哪个节点"，压缩只能一组组试，
     且 2025/J 的压缩显示全给的文本里至少三个节点模型本可自己推出。
   - **等级**：L1 仅结论（≤ 40 词）；L2 结论 + 该模型错的那个条件的否定（来自 quotes）；L3 输出规则的 case list / 伪代码；L4 加一个微型算例。只在 grader 判"given 但未 established / wrong"时升级。
   - **附加条目**：hazards（只收该模型踩过的）；code_gap 对应的实现约束；行为指令（仅当 class 为 stalled、零提交、或 END+fail/other 占多数）。
4. **write**（gpt-6-astra）：每个条目一次调用，输入 = 节点 statement/accept、该模型在此节点的 wrong claims 原文、上一版措辞及其接住情况、图上前驱节点（已写的）；
   输出纯 ASCII 一段。检查：COPY_RUN（对 `paths/P*.cpp` 和 solution.cpp）、ANSWER_NUMBERS、无代码骨架、solver-token 计数（`tokens.py`）。
5. **compose**：条目按 route 顺序 → hazards → 行为（放最前）；写成 `insight.txt`。
6. **launch**：`Solver/agentv3/contest.sh` × 5 seed（Slurm，`--insight-file`，`MAX_TOKENS_PER_ROUND=262144`），等待完成（squeue 轮询，断点续跑）。
7. **grade**：`ReasoningGraph/grade/grade.py` 判这 5 个 run（盲判；同图同缓存）。
8. **score / keep-best**：分数 = (solved, reached_end 数, 平均目标 route 深度, −平均输出 token, −insight token) 字典序；不比最好差才接受，否则回退到最好轮的快照，写手看到"试过、更差"的版本。
9. 停止：5/5 → 阶段 2；轮数上限（默认 8）；目标节点升到 L4 仍未接住且连续 2 轮无进度 → 报告"content 失败 / behavior 失败"并停。
10. **阶段 2 压缩**（默认 6 轮）：按组消融——删掉该模型在带提示 run 里已能自己 established 的节点（given 之外仍 held）、高等级降到 L1、删 hazards / 行为；每次 5 run，5/5 且 END 数不降才接受，否则二分；最后确认轮 5 run。
11. **report**：baseline / editorial / 引擎最终版：solved、insight token、解出 run 的平均输出 token、每节点接住率。

## 3. Model-specific 的具体落点

| 层 | 来源（都是该模型自己的 run） | 做法 |
|---|---|---|
| route 选择 | 无提示 run 的 held 集 | 不同模型走它更接近的路径（2025/L Qwen 的排序+线段树 DP 就是 explorer 没想到但图里补上的那种） |
| 内容节点 | stuck / root / frontier | 只写缺的，不写它已会的 → 紧凑 |
| 措辞 | 该节点的 wrong claims 逐字引用 | 写手直接针对模型的误解写否定条件；接不住再升级，不预先升级 |
| 实现层 | hazards_tripped、implemented.contradicts、code_gap | 只在 END+fail 时加，一条一个约束 |
| 行为层 | behavior.py 画像（Nemotron 盲提交 / 幻觉工具；Qwen CE 后重写、131k 截断零提交） | 诊断触发才加；若两轮无效，改 harness（用户已同意这条路线），不再占 insight 篇幅 |
| 表示 | 上一轮接住率 | 对 Qwen 公式版接住率高（2025/J 0.95），Nemotron 待测；写手可在升级时换表示 |

## 4. 评测协议（效果 ≥ 人写提示 / 简单提示）

- 题集：先 **editorial-resistant 六题**（2023/J、2024/G、2024/K、2025/A、2023/F、2022/U；agentv3 baseline+editorial 臂已有、图已建、无提示 run 已判分）
  + **2025/J**（有 GPTv3 的 ground truth）。之后扩 2024/J、2025/B、2024/I（只有 agentv2 臂，见 §6）。
- 对照：baseline（已有）、editorial（已有，不重跑）、**key-node-only**（图的 key node 一句话，自动生成，作为"简单提示"对照，5 run）。
- 指标：solved/5（最终 + 确认轮共 10）；insight 的 solver token；解出 run 的平均输出 token；未解按 2 h 实际 token 计。
  通过线：solved ≥ editorial 且 insight token < editorial token；再报输出 token 的比值。
- 成本：每轮 5 GPU-run（2.5 h 墙钟，并行）+ 判分约 0.5–1.5M 输入 token + 写作约 50k；一题一模型阶段 1+2 约 14 轮 ≈ 35 h 墙钟；
  QOS 16 GPU → 3 个 (题, 模型) 并行。

## 5. 目录与实施顺序

```
GPTv4/
  plan.md README.md config.py        # 路径、模型、等级、轮数、分数定义
  adapters/problems.py               # → ReasoningGraph/problems.py（ICPC + AtCoder 已支持）
  adapters/solver_agentv3.py         # launch / wait / collect（Slurm；路径指向 Solver/agentv3）
  graph.py   grade.py                # 调 ReasoningGraph 的 explore / grade，读 graph.json / runs.jsonl
  profile.py                         # 模型画像：held/wrong/stuck/traps/hazards/behavior
  diagnose.py                        # route 选择、目标集、等级、附加条目、接住判定
  write.py   compose.py              # 写手 prompt、检查、拼装
  loop.py    report.py               # 状态机 + 报告
  tests/                             # 伪 API + 伪 solver 的离线测试
  runs/<slug>/<model>/round<k>/{diagnosis.json, items.json, insight.txt, eval/, grade/}
```

顺序：
1. `config/adapters/graph/grade/profile` + 离线测试（读现有 30 题的 runs.jsonl，不调 API、不占 GPU）：半天。
2. `diagnose/write/compose` + 伪 API 测试；在 2024/G、2023/J 两题上对两模型各生成第 1 轮 insight 人工看一遍：半天。
3. `loop` + Slurm 适配 + `report`；2025/J Qwen 走通一轮（已知 3 轮可到 5/5，作为冒烟）：1 天。
4. 六题 × 两模型正式跑（3 并行）：约 1 周墙钟；中途按 §2.9 的停止报告修引擎而不是修测量。
5. 泛化检查：AtCoder 一题走完整链（problems.py 已支持），确认引擎核心无 ICPC 特定代码。

## 6. 需要用户定的点（我先按推荐做，可否决）

1. 2025/J、2024/J、2025/B、2024/I 只有 agentv2 的 baseline/editorial 臂；推荐先做 hard2 六题 + 2025/J，这四题暂与 agentv2 臂对照并注明，不补跑 agentv3 editorial 臂（符合"不重测 editorial"）。
2. 阶段 1 不设 insight 长度硬上限，只报超过 ½ editorial 的情况；阶段 2 压缩。
3. 行为层默认关，诊断触发；两轮无效改 harness。
4. 可选的廉价预筛（只跑 1 轮、只判第一轮是否接住目标节点，约 15 min GPU）：先不做，阶段 4 若写法迭代太贵再加。
