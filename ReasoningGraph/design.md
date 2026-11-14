# ReasoningGraph Ver2：predefined graph + trace grading

2026-10-30 的设计稿，还没有代码。目标：对一道题先建一张**预定义的 reasoning graph**（节点 = 引理 / 中间结论，
汇到 END = 完整 editorial，END 再一条边到 CODE），然后让强模型把弱模型的 run 判成这张图上的一条轨迹，
最后用「AC 的 run 能到 END、失败的 run 卡在中间」来验证并修正图的粒度。

## 0. 和 Ver1 / GPTv3 的关系

Ver1 走的是 chain (layers-v2) → 带 per-result `uses` 的 DAG (layers-v3) 这条路，三个阶段已经各自踩过坑：

| Ver1 / GPTv3 的经验 | 对 Ver2 的约束 |
|---|---|
| v2 把参考代码的实现选择写进 result，2013/G 的 7 个 AC 程序有 5 个在 L3.2 被判 wrong | 节点只写「每个正确解都成立的结论」；不同解法是图上不同的路径，不是一个 result 的措辞 |
| v3 靠 reviewer 的 `route_independent` + 对 AC 程序的 calibration 才修好 | calibration 直接继承：AC 程序 `not_needed` 一个节点 ⇒ 图缺路径 |
| 失败的 baseline 全卡在 L1.1（题意建模），editorial 不写这一步 | 图的第一层必须从 statement 建题意模型，不能从 editorial 开始 |
| 带 insight 的 AC run 根本不推导 L1，`strict_frontier` 全 null | 「AC ⇒ 有路径」只能对无 insight 的 run 直接成立；insight run 要先把 insight 本身映射成 given 节点 |
| Event 抽取一条长 trace 约 500 万 token，压缩丢 90% 候选 | grader 不用 Event；读快照 round（§2.1）+ 程序 |
| v2 把 64 位、精确开方放进 L4.4，否则链断 | implementation 不进引理图，放在 END→CODE 边上作为 hazards |

直接复用的代码：`InsightGen/GPTv3/Subtask/layers.py` 的 builder / rules / reviewer 循环（改 schema 和 prompt），
`InsightGen/GPTv3/ErrorAnalysis/{windows,probe,programs}.py` 的切块、逐字引用核对（phases.py 不再需要），
`InsightGen/GeneralGenV2/session.py` 的 API 调用。按仓库惯例复制到 Ver2 下改，不跨目录 import。

## 1. 图的定义（Stage A，`graph/`）

### 1.1 节点

一个节点是关于**这道题的对象**的一条结论，满足三条：

1. **可判真假**：一句 ≤ 50 词的自包含陈述（「P(b,S) 的高度是 max(2n−1, n−b+Σ(2x−1))」），不是「推出一个公式」。
2. **路径内与实现无关**：写「每个走这条路的正确解都必须得到什么」，不写参考代码怎么做。
   同一结论的不同证明写进 `accept`（grader 认任何正确证明）；**不同的中间结论**才是不同节点。
3. **可分离**：存在一个合理的 solver，拿到了它的前提却没拿到它（否则合并进前提）；也不存在合理的 solver 只拿到它的一半（否则拆开）。
   这是粒度的定义，§3.4 用 grading 数据检验它。

节点字段：

| 字段 | 含义 |
|---|---|
| `id`, `name`, `kind` | `N1..Nk`，拓扑序；≤ 8 词的题目专属名字；modeling / reformulation / key_property / algorithm / construction |
| `statement` | 结论本身 |
| `routes` | **OR of AND**：`[["N2","N3"], ["N5"]]` 表示「由 N2+N3 可得，或由 N5 可得」。`[[]]` 表示直接从题面得到（START 隐含） |
| `accept` | 读 reasoning 或代码的人怎么判断它成立；哪些别的证法也算 |
| `anchors`, `source` | 同 v3：题面里的对象名；来自 statement / editorial / reference code |
| `traps` | 初版为空；grading 后由失败 run 的 wrong claims 聚类回填（§3.4），不让 builder 凭空猜 |
| `depth` | 派生：到 START 的最长路 |

三个特殊节点：

- **START**：题面，隐含。
- **END**：`routes` 列出**解法族**，每条 route 是一组节点，拿齐其中一组就等于拿到完整 editorial 的内容。
  `statement` 写明「持有这组结论的 solver 只差常规编码」。
- **CODE**：END→CODE 唯一一条边，带 `hazards`：每个正确程序都必须满足、但不属于算法的约束
  （「n² 到 4·10^10，超过 32 位」「只接触不重叠的 tile 不能计数，零面积要和正面积区分」）。
  用户的假设「拿到完整 editorial 却写不出代码 = implementation，insight 解决不了」在这里**变成可测量的量**：
  grader 对到达 END 却失败的 run 分成「踩了具名 hazard」（一句话 insight 就能修，2025/J 的 64 位就是）和「其他」（真正的编码问题）。
  两类的比例由 §3.3 报告，不预设。

为什么是 AND-OR 图而不是一堆显式路径：editorial 只给一条路，「所有可能的解」靠一次 proposal 列不全。
AND-OR 让新路径只增加**不同的中间结论**那几个节点，共享的建模节点不重复；
一条「路径」在这个表示下是一个**推导**（derivation）：包含 END、且其中每个节点至少有一条 route 完全落在集合内的子图。

### 1.2 结构规则（Python，blocking，不调模型）

- （2026-10-30 按用户要求删除了所有数量上限：节点数、每节点 route 数、每条 route 的前提数、END route 数、hazard 数、anchor 数
  都不再限制；只有旧的 build.py 还保留 5–20 个节点。）
- 路径只在有证据时加：editorial、reviewer 写出并论证了正确且够快的替代解法、或某个 AC 程序对现有节点 not_needed。
  三道试点题（2024/I、2025/J、2023/C）的 AC 程序里每题只有 1–2 个解法族，分歧集中在 1–2 个节点（2024/I 的可行性检查、2025/J 的子集构造）；
  猜出来的路径只会稀释 grader 的注意力，因为每个窗口都要对全部节点判一次。
- route 只引用更小的 id（DAG）；每个节点都在某条到 END 的推导上，否则退回（初版没有 dead-end 节点）。
- 至少一个 `routes == [[]]` 的节点（从题面直接得到）。
- 同一节点的两条 route 不能相同或互为子集；END 的各条 route 也不能相同或互为子集。
- 词数上限只保留探针依赖的几项：name ≤ 8、statement ≤ 50、accept ≤ 80、hazard 40 / 60；名字不是通用步骤（`GENERIC_NAME`）；
  statement 不是答案表（`ANSWER_NUMBERS`）。
- anchors 只产生警告（不在题面、statement 没提到、没有 anchor），不退回。代码照抄检查已删除（explorer 本来就看不到参考代码）。

### 1.3 建图流程：只给题面的自由探索（2026-10-30 改，`graph/explore.py`）

用户要求建图不基于 editorial：只给 GPT 题面，让它自由探索，任何它认为正确的解法只要正确就 wrap up 成一条路径，直到穷尽它能想到的解法。
实现：

1. **Explorer**（一个长会话，只看题面）：想出一种解法 → 把依赖的中间结论写成新节点（可引用已有节点）→ 交一个 C++ 程序，
   `submit_path`。程序由 judge 跑全部测试（`graph/judge.py`，ICPC 先 sample 后 secret），**AC 才接受**，路径的 END route 入图；
   否则返回 verdict、失败测试的输入和一个正确答案，让它改；一种解法连续失败 `MAX_PATH_ATTEMPTS` 次记入 `rejected` 并放弃。
2. 接受后问"还有没有依赖至少一个图上没有的结论的解法"：有就继续；没有就 `finish_exploration`，附上考虑过但放弃的想法。
   上限 `MAX_PATHS` 条路径、`MAX_SUBMISSIONS` 次提交（2026-11-03 起 20 / 60，此前 12 / 40：放开"慢做法"后 2021/G、2025/L 撞到 12）。
   explorer 不自行判断够不够快（2026-11-03）：更简单但渐近更慢的做法也要提交，由判题器裁决，只有天文数字级超限才可不提交；
   原因是 2021/L、2021/G、2025/L 上 7 个无提示 AC run 走的正是 explorer 以"太慢"为由没提交的做法（稠密细化 2×10⁸ 次查表 0.5–2.5 s、
   暴力 2×10⁹ 次比较 2.2 s 都在时限内）。、`MAX_NODES_EXPLORE` 个节点。规则（§1.2）对合并后的图检查，再加 `check_path`：
   新节点必须在这条路径的 END route 推导上，END route 不能和已有的重复或互为子集。
3. **Reviewer**（新会话，看 editorial 和参考代码）只判节点的 specific / correct / judgeable / route_independent（blocking）和
   separable / atomic / missing / end_ok / editorial_found（advisory）；blocking 退回 explorer 会话，**只允许改文字**（`revise_nodes`），
   ids、routes、END routes 由 judge 验证过不动。不再有 reviewer 提替代解法的 coverage 审查。
4. **不再有 calibration**（2026-10-30 删除）。只读 AC 程序只能证明 key node 层面的算法，证明不了 solver 推理出了引理，
   和 reasoning graph 的对象不符。图是否贴合 solver，由第 2、3 步对 reasoning trace 的判分和验证回答；validate 的
   feedback.json 通过 `explore.py --revise-from` 回灌成只改文字的修订。
5. 每接受一条路径就重写 graph.json / png（status `exploring`），结束后写 review 和 history。
6. **Editorial 补路**（用户 2026-10-30 追加）：reviewer 判定 editorial 的解法不在路径里时，integrator 会话（看题面、editorial、
   参考代码和图）把 editorial 作为一条路径加入：复用已有节点，不受路径数 / 节点数上限，不需要 judge（参考代码即程序，
   judge 只为记录跑一次）；之后对合并后的图再审一轮（仍只改文字）。节点不区分来源（用户要求），
   只有 `paths[].source` 记录来源。这样最终图 = GPT 自己探索出的解法 + editorial 的解法。

下面是之前基于 editorial 的流程（`graph/build.py`，保留作对照）。

### 1.3-old 建图流程（沿用 v3 的三段式，加一项）

1. **Builder**（gpt-6-astra, high）：读 agent 看到的题面、editorial、solution.cpp；调 `submit_graph`。
   prompt 要点：从 statement 起建模；沿 editorial 列结论；**对每个节点问「还有没有别的中间结论能替代它到达 END」**，有就加 route；
   实现选择不是节点，约束写成 hazard；每个节点要能让 solver「在这里卡住」。
2. **Rules**：§1.2，退回 ≤ 3 次。
3. **Reviewer**（新 session）：per node 判 `specific / correct / judgeable / route_independent / separable / atomic`；
   per graph 判 `missing`（没写的必要步骤，含题意建模）和 **`coverage`**：reviewer 自己写出 1–2 个它认为正确且够快的其他解法，
   逐个检查能否表示成图上的推导；不能的作为 `missing_route`（blocking）。`separable=false` ⇒ 合并建议，`atomic=false` ⇒ 拆分建议（advisory）。
4. **Calibration**（直接用 v3 的代码和 prompt）：对 ≤ 6 个历史 AC 程序，每个节点 holds / contradicts / not_needed，带代码引用。
   程序对某个节点 `not_needed`、且它所有 route 上的替代节点也 `not_needed` ⇒ 缺路径；`contradicts` ⇒ 节点写窄了。都是 blocking。
5. **Revision** ≤ 3 轮，builder 在原 session 里改，可在 `notes` 里坚持并说明。
6. **输出** `graph/graphs/<slug>/`：`graph.json`（schema `reasoning-graph-v2`，`version` = 内容哈希）、`graph.md`、`graph.dot/png`、
   `review.json`、`calibration.json`、`sessions.jsonl`、`history/graph_<version>.json`。grading 结果都记 `graph_version`。

成本和 v3 相同量级：每题 3–6 次 high-effort 调用，每次带题面 + editorial + 代码，约 10–30 万 token。

## 2. 用强模型给 run 打分（Stage B，`grade/`）

输入：一个 run 的 `*_transcript.jsonl` + `*_submissions.jsonl` + `*_summary.json`（agentv2/agentv3 格式），加 `graph.json`。
输出：每个节点随时间的状态轨迹、最终状态、是否到达 END、卡点、run 的分类。

### 2.1 读哪些地方：快照 round（2026-10-30 定）

agentv2/v3 只保留最近 3 轮的工具调用、不保留推理，所以模型每一轮都从头复述题意、自己的模型和方案：一轮就是 solver 当时信念状态的快照。
在 Ver1 ErrorAnalysis 归档的 652 个 run 上验证：只读最后一轮的窗口，失败 run 的卡点与全读 21 个窗口一致 81–91%，AC run 96–100%；
只读第一轮分别是 39–67% 和 31–49%，不一致的多数是第一轮的误解后来被修正、最终卡在别处。

1. **最后一个实质性 round**（默认，必读）：最后一个推理字数 ≥ `MIN_ROUND_CHARS`（暂定 5k）且含方案复述的 round；
   比赛在 AC 时停止，所以 AC run 的最后一轮就是 AC 那一轮。它给出最终状态、`reached_end` 和卡点。
   最后一轮没提到卡点结论时（Ver1 数据里 5–11% 的失败 run）回退到前一个实质性 round。
   它之后的短轮（tail，都不足 `MIN_ROUND_CHARS`）和它一起读（2026-11-03，`--no-tail` 关闭）：短轮里的改正属于最终状态
   （2025/D Qwen run4 在第 22 轮才改掉排列枚举起点的 bug，判分器只读到第 20 轮）；309 个已判 run 里只有 3 个有 tail，代价可忽略。
2. **第一轮**（可选，`--first-round`）：只看题面时的初始模型，跨 run、跨 arm 可比，insight 的直接效果在这里；
   2025/J 的失败 run 有 9/10 在前 4% 就写错 L1.1。
3. **程序**：最终程序，加所读 round 内提交的程序，≤ 3 个。

**round 内仍切成 ≤ 24k 字符的窗口按顺序读**。窗口和节点没有对应关系：窗口是时间片，每个窗口都对全部节点判一次状态，
节点的状态是各窗口按时间聚合的结果（§2.3）。保留窗口的原因有二：
一轮不是一个状态而是一段轨迹，Ver1 数据里最后一轮的各窗口之间有节点状态翻转的 round 占 51–57%，Qwen 的长轮更多；
24k 是 Ver1 验证过引用核对和判断可靠的尺寸，Qwen 一轮 130k–300k 字符相当于 10–12 个窗口，Nemotron 一轮 2–3 个，
整轮一次调用等于让模型自己消解轮内的反复，难核对。窗口尺寸可在试点里对 Qwen 试 48k，以 grader 一致率为准。

### 2.2 两种探针

**窗口探针**（每窗一次调用）：对每个节点给

| 状态 | 判据 |
|---|---|
| `established` | 当前窗口里对这一步的描述实质正确：陈述或使用了这条结论（任一 `accept` 认可的形式，包括顺序、复杂度、表示不同的正确变体），不要求证明，措辞不精确也算 |
| `wrong` | 陈述或使用了**会导致结论错误**的东西（在某个合法输入上给出错误答案的规则、公式、界或构造），且窗口内没改正；不同的正确路线、够快但更慢的方法、不完整的论证都不算（2026-10-30 收窄） |
| `working` | 在处理这个节点回答的问题，但既没拿到也没说错 |
| `absent` | 没涉及 |

前三种都要一段**逐字引用**（程序核对是窗口原文的子串）和 solver 自己说法的一句话。`wrong` 的说法保留，供 §3.4 回填 `traps`。
另给 `off_graph`（2026-11-03）：窗口里 solver 陈述或使用、图上没有任何节点覆盖的实质性结论，≤5 条，带引用，`wrong` 标记它是否会导致答案错；
回答只有 off_graph 条目不合格（引文不是原文等）时，`ATTEMPTS` 次后丢掉这些条目、保留节点判定（salvage，2026-11-03；之前整窗作废，2021/G Nemotron run5 因此回退到旧轮次）；
validate 按文本聚类后写进 feedback.json，作为新节点或 trap 的候选。hint 文本同样记一份 `hint_off_graph`（editorial 说了而图上没有的）。

**程序探针**（每个程序一次调用）：对每个节点 holds / contradicts / not_needed，
对每个 hazard `ok / tripped`，都带代码引用。**2026-11-03 起它不再参与节点状态**：结果只进 `implemented`（最终程序对每个节点的
holds / contradicts / not_needed）和 hazards；`code_gap` = 到达的 END route 上被程序 contradicts 的节点，只用于 END+fail 的诊断。
理由：节点问的是 solver 是否持有结论，代码只能证明程序做了什么；editorial 臂的 run 照菜谱写出 AC 程序而题目模型是错的（2025/J 四例），
混进节点状态就把这种情况盖住了。

**given 节点**（insight / editorial arm）：把 insight 文本当一个窗口过一遍窗口探针，`established` 的节点记为 `given`。
这同时给出「insight 把模型送到图的哪里」。

grader 看到的是图（statement + accept）和窗口，**不看 editorial**，避免把 editorial 的内容脑补到 solver 头上。

**grader 知不知道 run 的结果**（2026-10-31 查实；2026-11-03 起默认盲判，`--sighted` 关闭）：原来默认不盲。窗口单元来自 `assistant_raw`（推理 + 回复）和 `tool_results`，
后者是 judge 的返回，AC run 读的最后一轮必含 `Submission #k: AC -- Accepted`，失败 run 常含 `TLE/WA`；程序探针的请求里直接写着
verdict。四道题 40 个 run 的离线核对：去掉程序探针重算闭包，reached_end 40/40 不变、class 只变 1 个（卡点换节点）；
探针引用的 444 条 wrong、1000 条 established 证据没有一条来自 tool_result。排除不了的是"看过 Accepted 之后判得更宽"的隐性偏置，
所以加了 `--blind`：去掉 tool_result 单元、不给 verdict、instructions 换成不提 verdict 的版本（`probe.py` 的 `_BLIND` 变体），
`runs.jsonl` / `grade.json` 记 `blind`。solver 自己文字里提到的 verdict（40 个 run 里 32 个有）属于 trace 本身，不去。
盲判和明判的逐 run、逐节点对比用 `validate.py --compare`（`run_blind.sh`）。

### 2.3 离线汇总（`closure.py`，纯 Python）

按时间排检查点：第一轮的各窗口（如果读）、最后实质性 round 的各窗口、其后短轮（tail）的窗口、该 round 内提交的程序、最终程序。

- 节点状态只由窗口检查点决定（2026-11-03；程序检查点不参与）：一个检查点内 `wrong` 优先于 `established` 优先于 `working`；否则 absent。
  最终状态 = 最后一个非 absent 的状态。`S*` = run 自己最终 established 的节点（窗口或程序）。given 只作记录和前提（frontier / unsupported 按 S* ∪ given 算），**不计入 END**（2026-11-02 改；之前 S* 含 given，editorial 写出了 key node 的 run 必然到达 END，editorial 臂的区分度为零）。
- 终审（2026-11-03 晚）：窗口折叠后终态 wrong 的节点，再读一次它的整条轨迹（该节点的每个窗口段落 + 前后 1200/2000 字原文 + 各窗口 focus + run 末尾 8k 字，即最后实质性 round 及 tail 的结尾，可跨窗口），
  判 solver 的**最终操作版本**：据以计算、决策、写代码或最后复述的版本。它推翻的说法（总结 / 标签 / 例子算术 / 放弃的分支 / 后来改正的版本）
  是 slip，须逐条列出并说明；没列为 slip 的 wrong 段落成立 ⇒ 终态 wrong。起因：2023/B 三个 AC run 的 noEND 来自最后一窗总结写错
  （ceil/floor）、旁路算术口误和把端点 gap 叫成 cyclic 的标签错，而 2024/G 的 N4 是反复断言并写进代码的不完备判定，二者只有看整条轨迹才分得开。
- `reached_end` ⇔ 存在一条 END route，其 **key node** ∈ S* **且该 route 上没有终态 wrong 的节点**（2026-11-03：跳过可以，说错不行）；
  `derived_end` ⇔ 某条 route 全部 ∈ S*（只报告，不做门槛：无提示 AC run 只有约 1/6 写全 route）。key node 由 explorer / integrator
  在提交路径时显式指定（`end.keys`），**定义为路径的输出规则**：决定程序对每个输入输出什么的构造或算法断言（kind 必须是 algorithm /
  construction；输出是构造的题 key 是构造节点而不是最优值的公式；复杂度、可行性断言和证明步骤不能做 key，`rules.check_path` 强制，
  reviewer 另有 key_ok）。此前 key 只要求是"拿到它就等于拿到解法"的最后一个结论，explorer 为满足"依赖全路径"常写成"整个算法在限制内"
  这类收尾断言，solver 和程序探针都能脱离前面步骤持有它，2026-11-02 的 6 个残差 run 全由此而来。规则仍强制 end_route 里其他节点
  都是 key node 的祖先；到达 key node 就算到达 END，中途跳过中间结论不算错（用户 2026-10-30 定），中间节点用于 unsupported、
  frontier、wrong 阻断等诊断。validate 用同一判据；没有 `keys` 的旧图退回终点节点。
- `unsupported` = S* 中没有任何 route ⊆ S* 的节点（建立了结论却没有前提）。insight run 里正常；baseline run 里多 ⇒ 这个节点和它的前提不可分（合并信号，§3.4），或 grader 误判。
- `frontier` = 未建立、但某条 route 的前提都在 S* 的节点（下一步可做的事）。
- `stuck` = frontier 中有 `wrong` 或 `working` 证据最多的节点（`stuck_source` = frontier）；frontier 里没有证据但有终态 wrong 的节点
  ⇒ 退回 root（最浅的终态 wrong，`stuck_source` = root；2026-11-03，之前这种"跳过 frontier 往深处做错"的 run 被判成 stalled）；
  都没有而本 run 有 `off_graph` 的错误结论 ⇒ `noEND+fail/off_graph`（在做题，但做的东西图上没有）；否则 `stalled`
  （没在做题，行为层问题，对应 model-failure-profiles 里的 blind submit / 幻觉工具）。
- `root` = 最终 wrong、且它所用的前提都不 wrong 的最浅节点（v2 的 roots 规则）。
- 分类：

| class | 含义 |
|---|---|
| `END+AC` | 图正确覆盖 |
| `END+fail/hazard:Hk` | 想法对，踩了具名实现约束，insight 可修 |
| `END+fail/other` | 想法对，编码问题，用户假设里 insight 管不了的那部分 |
| `noEND+AC` | 图缺路径、grader 漏判、或读的窗口不够：先升级该 run 到 `--plan all` 重判，仍 noEND 才算图的问题 |
| `noEND+fail/stuck:Nk` | 卡点，insight 的目标 |
| `noEND+fail/off_graph` | 在做题，但陈述的结论图上没有节点覆盖（图缺节点或 trap） |
| `noEND+fail/stalled` | 没有进入图 |

### 2.4 输出和成本

`grade/runs/<slug>/<cohort>/runs.jsonl`：每个 run 一条，含 given、每个检查点的节点状态与引用、程序判断、hazards、
最终 S*、unsupported、frontier、stuck、root、class、`graph_version`。`cache/` 按（窗口哈希，图 version）缓存，`sessions.jsonl` 记用量。

每个 run：最后一轮 Nemotron 2–3 个窗口、Qwen 10–12 个，加第一轮时各翻倍，再加 ≤ 3 个程序和 1 次 insight；
约 5–25 次调用、5–25 万输入 token。一题 30 个 run 约 300–500 万，和 Event 抽**一条** trace 的量相当。

## 3. 验证图的设计（Stage C，`validate/`）

### 3.1 用哪些 run

要同时有无 insight 的 AC 和失败，否则 solved/unsolved 和有无 insight 混在一起（Ver1 Profile 的教训）。
现有 run 清点（`*_summary.json`，baseline = 无 insight）：

| 题 | baseline AC | baseline fail | 备注 |
|---|---|---|---|
| 2024/I steppe-on-it | 3 | 17 | 两个模型 |
| 2023/C three-kinds-of-dice | 4 | 6 | Nemotron |
| 2018/G panda-preserve | 4 | 3 | Nemotron |
| 2025/J stacking-cups | 1 | 21 | Ver1 已知卡点 L1.1，另有 237 个带 insight 的 AC |
| 2016/G oil、2021/L、2025/E | 5–8 | 2 | 偏易 |

试点：**2025/J**（有 ground truth 可对照）、**2024/I**（AC/fail 都够、无 insight 混杂）、**2023/C**。之后扩到 `Subtask/problems.txt` 的 11 题和 MA-07 三题。

### 3.2 指标

- **soundness** = **无提示** AC run 中 reached_end 的比例（2026-11-03）：自己解出的 run 文字里必然有解法的想法，判不到就是图或 grader 的问题。
  hinted AC 单独报 `hinted_ac_end` 和 `recipe_rate` = 1 − 它：editorial 臂里 noEND+AC 不是错，是 editorial 只给了做法没给理解的证据
  （2025/J 四个 editorial 臂 run 照 editorial 的构造写出 AC 程序，杯子的堆叠模型却是错的）。目标 ≥ 0.9，每个反例人工看一次：缺路径 / grader 漏 / 窗口不够。
- **discrimination** = fail 且（noEND 或 hazard）的比例。目标 ≥ 0.8；余下的 `END+fail/other` 比例单独报告，它就是「implementation 维度」的实际大小。
- **localization**：失败 run 的 stuck 分布按模型汇总。图太粗（极端：只有 END 一个节点）能平凡满足前两条，所以要求 stuck 至少落在 ≥ 2 个节点上、或与已知结论一致（2025/J 应集中在题意建模节点）。
- **grader 可靠性**：20% 的 run 换 seed 重判一次，按节点状态算一致率；每题人工抽查 10 条引用。

soundness 和 localization 一起把粒度夹在中间：太粗 → localization 没信息；太细 → baseline AC run 里出现大量 `unsupported`（solver 根本不分开走这两步）。

### 3.3 报告

`validate/reports/<slug>/report.md`：run 表（模型、arm、verdict、reached_end、stuck、root、unsupported、hazards、class）、
四个指标、每个节点的统计（AC/fail 中 established 次数、wrong 次数、作为 stuck 的次数、与前提的共现率）、§3.4 的建议、待抽查清单。
同时写 `feedback.json`，格式和 reviewer 的 findings 一样，`build.py --revise-from feedback.json` 可以直接把它喂回 builder 的 revision 轮。

### 3.4 粒度的经验规则（从数据反推）

| 信号 | 动作 |
|---|---|
| 节点 N 在 AC 和 fail 里都与某条 route 的前提同时建立、从不是 stuck、baseline 里常 unsupported | 合并进前提 |
| N 是 stuck 点，且 fail run 在 N 上的 wrong 说法聚成 ≥ 2 类 | 拆成两个节点，每类一个；说法回填 `traps` |
| 某条 route 上的节点在所有 AC run 里都 not_needed / absent | 路径没人走，保留但标 `unused`；连续两轮仍 unused 可删 |
| `noEND+AC` 经 `--plan all` 复核后仍 noEND，程序探针给出 not_needed 的节点集 | 缺路径，交 builder 加 route |

改图后 version 变，受影响的窗口重判（缓存按 version），未改的节点不重新调用。

## 4. 目录与实施顺序

```
Ver2/
  design.md README.md config.py api.py problems.py problems.txt
  graph/    build.py rules.py prompts.py render.py  graphs/<slug>/...     # Stage A
  grade/    rounds.py windows.py probe.py programs.py closure.py grade.py  runs/<slug>/<cohort>/...   # Stage B
  validate/ validate.py  reports/<slug>/...                              # Stage C
  tests/    离线：rules、closure、probe 的引用核对、伪造 API 的 build / grade / validate 端到端
```

实现于 2026-10-30（见 README.md）；24 个离线测试通过，真实 API 未跑。

1. `config.py` + schema + `rules.py` + `closure.py` + 测试（不调 API）。
2. `build.py`：从 `GPTv3/Subtask/layers.py` 改 schema 和三段 prompt，加 coverage 审查；在 2025/J 上跑，和现有 15-result 链对照。
3. `grade/`：从 `GPTv3/ErrorAnalysis` 复制切块、探针；加 round 选择（`rounds.py`）、`working` 状态、程序探针、given；在 2025/J 的 10 个失败 baseline + 1 个 baseline AC + 5 个 editorial AC 上跑，对照 Ver1「全卡 L1.1」。
4. `validate.py` + 报告 + `feedback.json` 回灌；在 2024/I 上做一轮完整的 建图 → 判分 → 修图 → 重判。
5. 扩到 11 + 3 题。

都在登录节点跑（API），不需要 GPU。

## 5. 已做的取舍和没定的

- END→CODE 带 hazards 而不是纯一条边：保留 Ver1 里确认过的「一句话 insight 能修的实现约束」，同时让用户的 implementation 假设可被测量。
- grader 读最后一个实质性 round 的快照，不全读：成本差 10–30 倍；对 `noEND+AC` 单独升级到全读，避免把读得不够算成图的错。
  round 内保留 24k 窗口和时间聚合，不把整轮塞进一次调用。
- 初版不建 trap 节点：错误结论从失败 run 里来，不让 builder 从 editorial 猜。
- 节点数 5–20、每节点 ≤ 3 route、END ≤ 4 route：按试点结果调。
- 87 道 editorial 是 GPT 生成的 WF 题：builder prompt 里要说 editorial 可能有错，以 solution.cpp 和 judge 为准。
- 没定：insight 工程（GPTv3 loop）什么时候改成读 `runs.jsonl` 的 stuck / root 而不是 ErrorAnalysis 的 blocking。建议等试点三题的 soundness 达标之后再切。
