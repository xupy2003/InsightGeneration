# GPTv4：基于 reasoning graph 的 model-specific insight 引擎

设计与理由见 [plan.md](plan.md)。一句话：insight 是图上的一个割——从这个模型在无提示 run 里自己到达的节点集出发，
到某条 END route 的 key node，缺的节点就是内容；每个节点的写法针对该模型自己的错误说法；每一轮用真实 agentv3 run（×5）评测，
再用**同一张图**判带提示的 run，由判分结果决定下一轮改什么。

**逐节点给（`step` 模式，默认，2026-11-03 晚起）**：第 1 轮只写 route 上第一个模型不 held 的节点；每轮判分后看 route 的"前沿"——
第一个没被**全部** run（3/3）held 的节点（held = 自己推出了，或提示给了且它没推翻；给了却被推翻不算。前沿节点若有多数运行（3 次里 2 次）接受但不是全部，就先不升级它，保留它的提示，再加上多数运行也缺的下一个节点，下一轮同时检验两个（用户 2026-11-04 的决定：2023/J Qwen 三次里两次接受 N2 并走到 N4，一次反驳却让循环连升三级磨 N2）；多数运行反驳的节点才升级。前沿节点的提示已到 L4 或以上仍不被多数接受时，不是立刻升级或封锁：若多数失败运行的卡点（评分器的 stuck）在 route 上更靠后的节点，说明它们已经越过前沿在做后面的事，对前沿的"反驳"只是顺手的小错，就保留 L4 的提示，再加上后面第一个多数运行也缺的节点；只有卡点就是前沿本身（或更前）才继续升级，升到 L5（整个过程的伪代码、例子逐步走一遍、再写明模型自己的做法在这个例子上得到什么）还不行才封锁；停掉的循环可用 `--reopen` 在新规则下从最后一轮的记录重新规划并继续（2023/J Nemotron r4 的教训：N2 L4 被 2/3 反驳，但三次运行全卡在 N4，N2 上只是漏掉最后一次过桥、容量差 1 之类的小错）。已通过的节点（profile 里已掌握的前缀，或之前某轮 3/3 通过的）保持通过，除非本轮多数运行推翻它：一次运行没重述它只是噪声，不回退前沿（2024/G Nemotron r4 的教训：N4 在 L4 被三次运行全部接受，却因一次运行把 N1 留在 working 而被判 passed 0，循环误停））。前沿还是刚给的那个节点 → 这句没被接住，升一级（结论 → 针对它自己误读的否定句 →
可执行的规则 → 规则加小算例 → 整个过程的伪代码加逐步走例子，L5）；前沿已经越过它 → 这句过了，模型自己又往前走了几步，在新前沿加一条等级 1。5/5 后压缩只试较早的 item
（后面的 item 可能已让它多余）、降级、hazard、行为。`cut` 模式（`--mode cut`）是旧流程：第 1 轮写全部缺失节点再消融，留作对照。

路线上的节点全部给出、没有运行反驳、但仍有运行没解出（也没走到 END）时，没有前沿可提示；这时把这些失败运行最多停在的那个路线节点（评分器的 stuck 节点，平局取路线上靠前的）升一级，一轮一个节点，而不是原文重跑直到停滞规则把循环停掉（2024/G Nemotron r6：五个节点都给了，1/3，两次失败分别停在 N4、N5）。

## 运行

登录节点（API + sbatch），放进 tmux：一轮约 2.5 小时（3 个 2 h 的 GPU run 并行 + 判分）；确认轮和对照臂跑 5 个 run。

```bash
source ../env.sh && cd GPTv4                 # 在 repo 根目录
python3 -m unittest discover -s tests -t . -v                 # 离线测试：伪 API、伪 solver、伪 grader

python3 loop.py --problem 2024/G-kindergarten --model nemotron --write-only   # 只写第 1 轮的 insight（调 API，不占 GPU）
python3 loop.py --problem 2024/G-kindergarten --model nemotron                # 端到端；可随时 Ctrl-C，重跑从 state.json 续
python3 loop.py --problem 2024/G-kindergarten --model nemotron --status
python3 loop.py --problem 2024/G-kindergarten --model nemotron --control keynode   # 对照臂：只给 key node 一句话
python3 report.py [--problem P --model M] [--out report.md]
```

常用参数：`--mode step|cut --rounds1 12 --rounds2 6 --runs 3 --confirm-runs 5 --gate-runs 5 --phase2-runs 5 --phase2-min 3 --no-gate --no-confirm --dry-run`（只写 insight 并 `sbatch --test-only`）。

## 一轮做什么（`loop.py`）

| 步 | 模块 | 做什么 |
|---|---|---|
| 0 | `graph.py` | 读 `ReasoningGraph/graph/graphs/<slug>/graph.json`；没有就调 `explore.py` 建图 |
| 0 | `grading.py` + `profile.py` | 该模型无提示 run 的判分（优先读 ReasoningGraph 的 `grade/runs/<slug>/pilot/runs.jsonl`，否则判 RunPool 里的 run，再否则自己跑 baseline 臂）→ `profile.json`：每节点 held / wrong / stuck、错误说法（逐字引用）、行为画像（`behavior.py`） |
| 0 | `diagnose.py` | 选 route：缺失节点代价 Σ(1 + wrong_rate) 最小；第 1 轮的 items：step 模式 = route 上第一个未 held 的节点（cut 模式 = 全部），等级 1 |
| 1 | `write.py` | 每个没有文本的 item 一次 API 调用（gpt-6-astra）；等级 1 只写结论，2 加针对该模型误读的否定子句，3 写成 case list / 伪代码，4 加微型算例；检查：ASCII、无空行、solver token 上限（`tokens.py`）、不含完整程序、不抄参考程序 / route 程序（COPY_RUN 16）、不写节点 id、不列答案表 |
| 2 | `compose.py` | 行为 item → 节点 item（图序）→ hazard item，空行分隔 → `r<k>/insight.txt` |
| 3 | `adapters/solver_agentv3.py` | `sbatch contest.sh` × 3（确认轮 × 5；qwen 80G / nemotron 64G，2.5 h），等待，读回 solved 和输出 token（transcript 每轮 `completion_tokens` 之和） |
| 4 | `grading.py` | `ReasoningGraph/grade/grade.py` 盲判这些 run（缓存 `grade_cache/`） |
| 5 | `loop.py` | 分数 = (solved, END 数, 通过的 route 节点数, route 上到达深度均值, −route 上说错节点数均值)，字典序；不比最好差就接受，否则回退到最好轮的快照（被拒的写法进 history 作"更差"版本） |
| 6 | `diagnose.update` | step：前沿节点有 item → 升一级，没有 → 加等级 1（同级已有"更差"版本则跳到更高一级）；cut：失败 run 的 stuck 在哪个 item → 升一级；两种模式都有：grader 没在 hint 里识别出的节点 → 重写；END+fail 踩的 hazard → hazard item；最终程序 contradicts 的 route 节点 → 升级并给程序证据；stalled / 零提交 / END+fail/other 过半 → 行为 item。顶级仍卡住 → 该节点 blocked，换最便宜的不含它的 route；失败 run 过半卡在 route 外的节点 → 换到含该节点的 route；跳跃（用户 2026-11-05）：前沿之后的 route 节点或平行 route 上的节点，在最近 2 轮各被 ≥½ 的 run（含已解出的）推翻 → 立即加 L1 的 item（一轮一个，最被推翻者优先），持续被推翻则升级，顶级不封锁、不换 route（2023/F Qwen 连续 7 轮 3/3 推翻 N9 而循环还在提示 N2–N6） |

3/3 之后先过**门（gate，`g<k>`）**，再压缩（用户 2026-11-06）：把那一轮**同一段文字**用 5 个全新 seed（101–105）重跑一次，
解出数 ≥ GATE_RUNS − GATE_TOLERANCE（5 − 1 = 4）才算过。过了就进阶段 2；没过就回到阶段 1，用门这 5 个 run 自己的判分（比一轮 3 个更可信）规划下一轮，
门不计入阶段 1 的 budget 也不计 stall；门按 insight 文本记账，同一段文字不会被测第二次，而门失败后若诊断无事可改就直接停。
起因：2025/J Nemotron 的 r2 三个 run 全解出，压缩了 6 轮，最后确认只有 3/5，整段压缩白做。

**阶段 2 压缩**：候选组（step 模式）依次为 hazards、行为、升级过的 item 降回等级 1、除最后加入的以外的节点逐个（按 route 顺序），
最后是“缩写”（shorten）：所有剩下的项按原级别重写得更短，目标 SHORTEN_SHARE（0.65）倍的 token 数、不低于 SHORTEN_MIN（20）；被接受就再缩一轮。
每组 **PHASE2_RUNS = 5 run**，解出数 ≥ 5 − PHASE2_TOLERANCE（4）且 END 数不降（`PHASE2_REQUIRE_END`，现为关）才接受。
压缩轮本身就是确认规模，所以接受的 insight 不再另跑确认轮，**第一次被拒就结束阶段 2**（`PHASE2_STOP_ON_FAIL`，用户 2026-11-06 “直到失败为止”；
置 False 可恢复旧的二分搜索，把被拒的组拆半继续试）。写不进目标长度时保留原文。

**确认轮（`f<k>`）** 只剩一种用途：阶段 1 用完 budget 也没有哪一轮全解出时，用 5 个 run 量一下最好那段文字的解出率（目标 = 最好轮解出率换算到 5 个 run，允许差 1）。

## 目录

```
config.py  api.py  tokens.py  behavior.py        路径 / API / solver tokenizer 计数 / 行为画像（后两者自 GPTv3 复制）
adapters/problems.py  adapters/solver_agentv3.py 题目加载（经 ReasoningGraph/problems.py，ICPC）/ Slurm 适配
graph.py  grading.py  profile.py  diagnose.py  write.py  compose.py  loop.py  report.py
tests/                                           离线测试（fixtures.py 的玩具图）
runs/<slug>/<model>/
    profile.json  state.json  loop.log  sessions.jsonl  grade_cache/  grade.log
    r<k>/{insight.txt, items.json, eval/<run files>, grade/runs.jsonl}      阶段 1 轮次
    g<k>/...  c<k>/...  f<k>/...  ctl_keynode/...                             门、阶段 2、确认轮、对照臂
```

限制：只支持 ICPC WF 题。

第 0 步的无提示 run 判分：repo 不带 ReasoningGraph 的判分记录（`ReasoningGraph/grade/runs/`），所以默认会用 API 判 `RUNPOOL` 里的 run
（每题每模型最多 10 个）；要复用旧判分，把旧的 `grade/runs/<slug>/pilot/runs.jsonl` 拷到同一位置即可。旧记录里搬家前的 trace 路径
（`codebase/agent*`）由 `grading.fix_trace` 改到 `Solver/` 下。

## 状态（2026-11-08）

7 道 editorial-resistant 题 × 2 个模型共 14 个 loop 已跑完：baseline 在 14 对上都是 0/5；engine 在 7 对上达到 ≥4/5，
其中 5 对的 editorial 臂 ≤1/5（旗舰是 2024/K：Qwen 4/5、Nemotron 5/5，editorial 两个模型都是 0/5）。2023/J、2024/G 卡在 N4。
各轮的输出（`runs*/`）不在 repo 里。
