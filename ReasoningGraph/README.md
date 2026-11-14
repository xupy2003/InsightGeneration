# ReasoningGraph Ver2：predefined graph → grading → validation

设计见 [design.md](design.md)。三段：

1. **graph/** 建图（`explore.py`，2026-10-30 起的默认方式）。explorer（gpt-6-astra）**只看题面**，自由探索：想出一种解法，
   把它依赖的中间结论写成节点（`routes` = 由哪些更早节点推出的若干备选组合），交一个 C++ 程序给 judge 跑全部测试；
   **AC 才成为图上的一条路径**（END 的一条 route），否则改了再交，一种解法连续失败 `MAX_PATH_ATTEMPTS` 次就放弃。
   接着被问"还有没有依赖至少一个新结论的、本质不同的解法"，有就继续，直到 explorer 调 `finish_exploration` 说穷尽，或达到 `MAX_PATHS`
   （2026-11-03 起 20 条、`MAX_SUBMISSIONS` 60 次）。**够不够快由判题器裁决**（2026-11-03）：更简单但渐近更慢的做法（暴力、稠密模拟、
   跳过优化步）只要有自己的算法节点就必须提交，只有天文数字级超限才可不提交；TLE 后最多再试一次并记入 considered。
   editorial 和参考代码 explorer 看不到；之后 reviewer 用它们检查节点的真伪和措辞（只允许改文字，结构由 judge 验证过不动）。
   END→CODE 边上的 `hazards` 是 explorer 在实现时发现的实现约束。图是否贴合真实 solver，只由第 2、3 步对 reasoning trace 的判分和验证来回答
   （2026-10-30 删除了只读 AC 程序的 calibration：程序只能证明 key node 层面的算法，证明不了 solver 推理出了引理）。
   **Editorial 补路**（`--editorial missing`，默认）：reviewer 判定 editorial 的解法不在图里时，一个看得到 editorial 和参考代码的
   integrator 会话把它作为一条路径加入（复用已有节点，不受路径数和节点数上限约束，不需要 judge，参考代码就是它的程序）。
   节点不区分来源，和探索出的节点一样；只有 `paths[].source` 记录这条路径来自 editorial。
   `--editorial always|never` 改这个行为，`--editorial-only` 对已有的图单独跑这一步。
   `build.py` 是之前基于 editorial 的建图方式，保留作对照。
2. **grade/** 判分。对每个 run 读**最后一个实质性 round 及其后的所有短轮**（tail，2026-11-03，`--no-tail` 关闭；可选第一轮），round 内切 24k 窗口按顺序读；每个窗口对全部节点判
   established / wrong / working / absent（逐字引用核对），另记 `off_graph`（图上没有节点覆盖的实质性结论）；insight / editorial 文本
   先过一遍探针得到 `given`（只记录和作前提，不计入 END；2026-11-02 起）。**节点状态只由窗口决定**（2026-11-03）：最终程序由程序探针判
   holds / contradicts / not_needed 和 hazard ok / tripped，结果进 `implemented` 和 hazards，不进节点状态。离线闭包（`closure.py`）算
   reached_end（key node 成立且 route 上没有说错的节点）、derived_end、unsupported、frontier、stuck（frontier 无证据时退回 root）、
   roots、code_gap 和七类之一。默认盲判（`--sighted` 关闭）。最后一轮（含 tail）对所有节点都 absent 时自动回退读前一个实质性 round。
   窗口回答只有 off_graph 引文不合格时，丢掉这些条目、保留节点判定（salvage，2026-11-03，记在 `windows_salvaged`），不再整窗作废。
   **终审**（adjudication，2026-11-03 晚）：窗口折叠后终态 wrong 的节点，再由一次探针读它在整条轨迹上的所有段落（每段带前后原文）、
   各窗口的 focus 和 run 末尾 8k 字（最后实质性 round 及 tail 的结尾，可跨窗口；最终写法和代码），判 solver 对这一步的**最终操作版本**（它据以计算、决策、写代码或最后复述的版本）：wrong / established / working；
   被 solver 自己的计算、代码或更细的陈述推翻的说法（总结、标签、例子里的算术错、放弃的分支、后来改正的版本）是 slip，必须逐条列出并说明；
   没列为 slip 的 wrong 段落就成立，终态仍是 wrong。窗口的判定保留为 `window_final`，报告里 `x ⇒ +`。`--no-adjudicate` 关闭。
3. **validate/** 验证。soundness（AC ⇒ END）、discrimination（fail ⇒ noEND 或 hazard）、END+fail/other 残差、localization、
   两次判分的一致率；每节点统计；合并 / 拆分 / 缺路径建议写成 `feedback.json`，`build.py --revise-from` 直接读；
   `--apply-traps` 把失败 run 的错误说法回填到节点的 `traps`。

## 运行

都在 `ReasoningGraph/` 目录执行（先 `source ../env.sh`），建图和判分要在登录节点（API）。离线测试：

```bash
python3 -m unittest discover -s tests -t . -v        # 39 个测试，伪造 API，不联网
```

建图（探索）：

```bash
python3 graph/explore.py --problems 2025/J-stacking-cups        # 写 graph/graphs/2025_J-stacking-cups/
python3 graph/explore.py --problems P --force [--max-paths 12] [--no-review] [--editorial missing|always|never]
python3 graph/explore.py --editorial-only --problems P           # 对已有的图单独跑 editorial 补路
python3 graph/explore.py --revise-from validate/reports/<slug>/feedback.json --problems P   # 按验证结果只改文字
```

END 的判据是 **key node**：explorer / integrator 提交路径时显式指定的**路径的输出规则**（`end.keys`）——决定程序对每个输入输出什么的
构造或算法断言（kind 必须是 algorithm / construction；输出是构造的题 key 是构造节点，不是最优值的公式；复杂度、可行性断言和证明步骤
不能做 key，check_path 强制；2026-11-03 起，之前 key 常被写成"整个算法在限制内"这类脱离步骤也能成立的收尾断言）。规则要求 end_route
里其他节点都是它的祖先，所以路径是循序渐进的。solver 在文字里持有 key node、且这条 route 上没有说错的节点，就算到达 END；
跳过中间结论不算错，说错不行。图里只有 key node 连到 END。复杂度不单独成节点，写进它修饰的算法节点的 accept。

2026-10-30 起的两条口径：节点 statement 只写结论本身（不写复杂度、扫描顺序、tie-break、特例位置、等价公式中的某一个，
这些放进 accept 作为"也算"的例子）；判分端同步放宽：`wrong` 只记会导致结论错误的实质性错误，
算法描述正确但顺序、复杂度、表示不同的都算 established（probe 缓存版本号已升到 2）。validate 的 feedback.json
通过 `--revise-from` 回灌成只改文字的修订；缺路径走 editorial 补路或重新探索。

```bash
python3 graph/explore.py --list
python3 graph/judge.py 2025/J-stacking-cups some.cpp             # 单独跑一次 judge
```

探索过程中每接受一条路径就重写一次 graph.json / graph.md / graph.png（status `exploring`），可以随时看。
`paths/P<k>.cpp` 是每条路径的 AC 程序，`judged.jsonl` 和 `judged/` 记录每次提交。

基于 editorial 的旧方式（对照用）：`python3 graph/build.py --problems P [--audit-only|--revise-from F]`。

题目名用 `2025/J-stacking-cups`（`wf2025/J-...` 也接受）。本 repo 只带 ICPC WF 的加载器；AtCoder 名字能识别，但加载器（CategoryEval）不在这里。

判分（先 `--dry-run` 看要读什么）：

```bash
python3 grade/grade.py --graph graph/graphs/2025_J-stacking-cups/graph.json \
    --runs '/path/to/runs/*/baseline/2025_J-stacking-cups_run*_transcript.jsonl' \
    --out grade/runs/2025_J-stacking-cups/baseline --first-round --dry-run
python3 grade/grade.py ... --out grade/runs/2025_J-stacking-cups/baseline --first-round --workers 8
```

验证与回灌：

```bash
python3 validate/validate.py --graph graph/graphs/2025_J-stacking-cups/graph.json \
    --runs grade/runs/2025_J-stacking-cups/*/runs.jsonl --out validate/reports/2025_J-stacking-cups \
    [--compare grade/runs/2025_J-stacking-cups-seed2/*/runs.jsonl] [--apply-traps]
python3 graph/build.py --revise-from validate/reports/2025_J-stacking-cups/feedback.json --problems 2025/J-stacking-cups
```

改图后 version 变；判分结果记录 `graph_version`，validate 会警告版本不一致。缓存按（请求内容，图 version）命中，
未改的内容不重新调用。

一条龙（建图 → 判 `grade/runs/<slug>/pilot_runs.txt` 里列的 run → 验证）：

```bash
bash run_pilot.sh 2024/J-the-silk-road-with-robots        # 日志在 graph/logs/<slug>_{explore,pilot}.log、grade/runs/<slug>/pilot_grade.log
```

按列表批量建图（每题一个 explore.py 进程、一个 `graph/logs/<slug>_explore.log`，N 个并行，已有 graph.json 的题跳过，退出状态记在
`graph/logs/explore_list_<date>.log`；在登录节点上、最好放进 tmux）：

```bash
bash explore_list.sh problems.txt                                # 4 个并行
bash explore_list.sh LIST 2 --max-paths 8                        # 2 个并行，其余参数透传给 explore.py
```

`pilot_runs.txt` 一行一个 transcript 路径（绝对路径或相对 `ReasoningGraph/`，`#` 注释）；`RUNLIST=<文件>` 换一个列表。
agentv2 / agentv3 的 transcript 和 GPTv3 insight 臂的 run 都能读（提示标记相同）。

**盲判**（`--blind`，2026-10-31）：默认判分不是盲的，窗口里带 judge 返回的 tool_result（最后一轮含 `AC -- Accepted` 或 `TLE` 等），
程序探针的请求里也写着 verdict。`--blind` 把 tool_result 单元整个去掉、不给程序探针 verdict、两种探针换成不提 verdict 的
instructions（`WINDOW_INSTRUCTIONS_BLIND` / `PROGRAM_INSTRUCTIONS_BLIND`），结果记 `blind: true`；请求内容不同所以缓存自然分开，
但要用单独的 `--out`。solver 自己文字里提到的"上次 WA"去不掉。现在默认就是盲判（`config.GRADE_BLIND`），`--sighted` 关闭。

## 文件

| 目录 / 文件 | 内容 |
|---|---|
| `config.py` | 路径、模型、节点数 / 词数 / 窗口等上限 |
| `api.py` | OpenAI client（`OPENAI_API_KEY`）；strict 工具；usage；重试；JSONL 记录 |
| `problems.py` | 题目名规范化、slug、`ProblemContext`（题面 = `Solver/agent_prompt.py` 给 solver 的消息，逐字节相同） |
| `graph/rules.py` | 结构规则、`depths`、`reachable`、`version_of`、`graph_text` |
| `graph/prompts.py` | explorer / integrator / reviewer / 修订 / 旧 builder 的 instructions |
| `graph/explore.py` | 探索式建图与 CLI（默认）；`graphs/<slug>/{graph.json, review.json, graph.md, graph.dot/png, sessions.jsonl, judged.jsonl, paths/, judged/, history/}` |
| `graph/judge.py` | 用 `Solver/` 的题目加载和 judge 跑全部测试；先 sample 后 secret |
| `graph/build.py` | 基于 editorial 的建图循环（对照用）；explore.py 复用它的 reviewer 调用和写文件 |
| `graph/render.py` | graph.md / graph.dot / graph.png |
| `grade/rounds.py` | 读 round、选最后实质性 round / 其后短轮 tail / 第一轮 / fallback、取 insight 文本 |
| `grade/windows.py` | 切 unit 与窗口（不跨 round） |
| `grade/probe.py` | 窗口 / insight / 程序三种探针，引用核对，缓存 |
| `grade/programs.py` | 选要读的程序 |
| `grade/closure.py` | 节点状态聚合、END / unsupported / frontier / stuck / roots / class |
| `grade/grade.py` | CLI；`runs/<slug>/<cohort>/{runs.jsonl, grade.json, report.md, cache/, sessions.jsonl}` |
| `validate/validate.py` | 指标、建议、一致率；`reports/<slug>/{report.md, report.json, feedback.json}` |
| `tests/` | 离线测试 |

## 状态

30 道 ICPC WF 题的图在 `graph/graphs/`（repo 里每题只收 `graph.json`、`graph.md`、`review.json`；探索会话、各路径的 AC 程序、
判分记录和验证报告都不在 repo 里，重新生成或从旧工作目录拷进来，这些目录已 gitignore）。
在这 30 题、309 个无提示 run 上：soundness 188/195（96%），discrimination 113/114（2026-11-03）。
