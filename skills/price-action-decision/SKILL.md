---
name: price-action-decision
description: 按 Al Brooks 价格行为思路读盘并给出条件式交易计划：先看价格事实，再判断市场环境、Always In、多空双方和位置，最后筛选一个当前最佳动作。用于强突破、窄/宽通道、交易区间、H1/H2/L1/L2、BO+FT、BLSHS、MTR、趋势后段参与、高潮反转、盘中更新、持仓管理和历史回放。
---

# Al Brooks 价格行为交易决策

## 目标

把课程里的交易思路内化成可运行流程，而不是用章节号做匹配表。

每次分析都执行 `references/decision-loop.md` 中的七步看盘。该文件是唯一内层思考顺序；其他参考卡只提供证据标准、环境交易方法和具体交易结构。

允许输出“不交易”或“等待更多证据”。课程案例中的 Tick、Point、胜率数字只能当经验量级，不能写成用户回测结果。

## 职责边界

- 负责价格行为判断、Always In、位置、状态转换、交易模式选择和交易管理。
- 不负责行情接口、缓存、复权或周期聚合。缺少 OHLCV 时先使用 `$market-data`，再执行本技能。
- 不以 `$stock-technical-analysis` 作为前置依赖。只有用户明确要求综合技术分析时，才把它作为平级分析器；RSI/MACD、BOS/CHoCH 不得覆盖价格行为判断。
- 仓位和具体风险金额交给 `$trade-risk`；本技能保留逻辑止损和交易前提失效位置。
- 不自动下单，不做确定性收益承诺。

## 运行模式

| 模式 | 用途 | 额外参考 |
|---|---|---|
| `concept` | 解释课程概念 | 必要时读原始转写 |
| `snapshot` | 一次性图表或行情分析 | `references/output-contract.md` |
| `intraday` | 5m/15m 盘中增量分析 | `references/intraday-mode.md`、`references/session-context.md` |
| `position-management` | 已有仓位管理 | `references/trade-management.md` |
| `replay` | 历史逐根K线验证 | `references/replay.md` |

除概念解释外，必须执行输入检查和交易决策回路。

### 行情规模与上下文边界

首次行情分析先读取 `references/data-budget.md`，再调用 `$market-data` 的确定性脚本（`market_data.py snapshot --mode pa`）。不得自行扩大周期数量或历史根数，也不得让 AI 手写临时 HTTP/抓取脚本或把完整原始 JSON 直接带入价格行为分析。先完成有限窗口、数据质量和紧凑事实交接，再执行七步看盘。

注意区分两层窗口：`$market-data` 脚本内部拉取的 `fetch_bars` 是为了保证 `EMA20` / `ATR14` 预热与完整过滤；`data-budget.md` 中的 `analysis_bars` 与 `detail_bars` 是归一化后交给价格行为分析的交接上限，不能把未裁剪全量原始行情直接当作分析输入。

用户要求“测试”“完整分析”“复核”时使用完整报告模式：保留每个周期的最后完整 K 线、覆盖范围、数据源、forming/剔除记录、关键推动与回调证据，以及每个标的的完整交易决策卡。完整报告不等于输出全部原始 K 线。

普通快照只输出当前相关事实；盘中更新只输出差量。除非用户明确要求历史回放或审计，不得使用无限或大规模历史窗口。

多标的取数必须遵守 `data-budget.md` 的调用顺序：默认一次只处理一个标的（单标的内部周期可由 `$market-data` 脚本并发获取），完成该标的的压缩摘要后再处理下一个；不得一次并发发出所有标的的所有周期请求。某一周期失败时只允许重试该失败周期一次，成功周期不得整组重拉。不得为了查找课程或历史测试而扫描 `/Users`、归档会话、记忆原文或其他与当前 Skill 无关的目录。

## 固定流程

### 1. 准备输入

确认市场、目标周期、分析时点、完整K线、交易时段、用户是否已有仓位。结构化行情必须来自 `$market-data` 或用户提供的等价数据。

先按 `references/data-budget.md` 申请有限行情窗口，并在交接给本技能前完成去重、排序、完整K线过滤和数据质量标注。

工具返回原始结果后立即压缩为行情交接格式；不得复制、转述或再次搜索完整原始返回。若行情工具已经提供了所需周期，不得通过 shell、历史会话或其他文件重新获取同一批数据。

左侧结构不足时：

- 只输出可观察事实与待确认条件；
- 不编造精确价位；
- 不根据单根局部K线断言整个市场状态。

### 2. 分配周期角色

盘中默认：60m 提供背景，15m 判断主要状态和交易模式，5m 负责触发与管理。用户明确指定目标周期时以用户目标为准。

每个周期独立判断。高周期是背景和位置约束，不是机械否决。

### 3. 执行七步看盘

读取：

- `references/price-action-evidence.md`
- `references/decision-loop.md`
- `references/context-selector.md`

先按 `decision-loop.md` 完成七步，再用证据卡和状态选择器校验。分析必须回答“多头在交易什么，空头在交易什么”。每次保存：主要解释、备选解释、支持证据、反对证据，以及什么新的价格事实会使主要解释切换到备选解释。

不得先写“偏多/偏空/等待突破”再补理由。状态不清楚时，不继续匹配具体入场。

### 4. 按市场环境选择交易模式

读取 `references/setup-router.md`，再只读取当前主要环境卡和必要的交易结构卡。不得为了比较而一次加载全部环境卡。只选择一个主要模式，最多保留一个触发条件不同的备选。

先用核心证据、状态选择器和路由表完成初步分类，再读取一个主要环境卡；只有候选模式确实需要时才读取第二张交易结构卡。

验证适用环境、不适用环境、位置、方向、确认和缺失证据、触发、逻辑止损、目标、失效与不交易条件。证据不足时标记为 `candidate`，不能直接升级为入场建议。

### 5. 用交易者方程过滤

在给出交易计划前，快速检查：

- 这是更高胜率、目标可以更近的顺势结构，还是更低胜率、需要更大空间的反转/逆势结构；
- 逻辑止损是否放在“交易前提被推翻”的位置，而不是情绪化窄止损；
- 到最近合理目标是否仍可能让期望为正；
- 若止损过远、空间不足、位置在区间中部、或状态冲突，输出等待/不交易。

不要输出伪精确胜率。用“更像高胜率顺势 / 更像低胜率反转 / 接近 50-50”这类课程语言即可。

### 6. 更新状态并输出

读取 `references/state-contract.md`。战法生命周期：

```text
none -> candidate -> armed -> triggered -> managing -> closed
                         \-> invalidated
```

盘中只在完整K线结束后确认状态转换。使用 `scripts/pa_state.py` 检查合法转换和生成差量。

输出规则：

- 读取 `references/output-contract.md`。
- 先给自然结论，再补必要证据和计划；不要先堆数据字典。
- 完整报告可用栏目，但基础信息保持短，价格行为用叙述写清环境和双方逻辑。
- 禁止单独输出“作者式二元决策 / Video xx”这类生硬标题。
- 普通盘中更新：只输出变化项、当前动作和下一触发。
- 已持仓：优先判断原交易前提成立、减弱或失效。
- 只有用户要求仓位或提供账户约束时，再使用 `$trade-risk`。

## 重要K线与重新分析

出现以下任一事实时重新执行决策回路：

- 突破关键位并收盘在外侧；
- 突破出现跟进或迅速失败；
- 形成新的主要摆动点；
- 出现足以挑战 Always In 的强反向运动；
- 趋势后段出现高潮棒、失望棒或最终趋势棒嫌疑；
- 当前模式触发、减弱或失效；
- 新交易时段开始或行情数据质量变化。

其他K线只记录局部证据变化，不重复完整报告。

## 参考文件选择

| 判断或任务 | 读取文件 |
|---|---|
| 行情预算、压缩交接、数据质量 | `references/data-budget.md` |
| 作者式读盘顺序、40-60、交易者方程 | `references/decision-loop.md` |
| 市场状态、Always In、状态转换 | `references/context-selector.md` |
| 从状态选择交易模式 | `references/setup-router.md` |
| 价格行为证据链 | `references/price-action-evidence.md` |
| 盘中周期、会话与增量触发 | `references/intraday-mode.md` |
| 开盘、盘中、尾盘背景 | `references/session-context.md` |
| 剥头皮、波段、混合或不交易 | `references/trade-style.md` |
| 状态保存、战法生命周期、差量 | `references/state-contract.md` |
| 无未来数据的逐根回放 | `references/replay.md` |
| 窄幅通道 | `references/tight-channel.md` |
| 宽幅通道 | `references/broad-channel.md` |
| 交易区间 / BLSHS | `references/trading-range.md` |
| 趋势后段参与 | `references/late-trend.md` |
| H1/H2/L1/L2 | `references/h2-l2.md` |
| 成功突破和失败突破 | `references/bo-ft.md` |
| MTR | `references/mtr.md` |
| 高潮反转 | `references/climactic-reversal.md` |
| 开盘反转 | `references/open-reversal.md` |
| 止损、Bailout、重新入场 | `references/trade-management.md` |
| 最终回答结构 | `references/output-contract.md` |
| 需要回查原文时的来源索引 | `references/source-map.md` |

## 强制限制

- 上下文重于形态：同一根锤子线、吞没线在不同状态下意义不同。
- 窄幅通道中不优先逆势交易；难以区分窄幅和宽幅时先按窄幅处理。
- 宽幅通道保留趋势方向，不能直接当成中性交易区间。
- BLSHS 只在有足够空间的交易区间边缘使用，中部通常等待。
- H1/H2/L1/L2 必须有趋势、旗形或突破回调背景，不能只数 K 线。
- BO+FT 必须区分突破被接受和突破失败。
- 一次普通反向K线不能确认 MTR 或高潮反转。
- 趋势后段可以缩小仓位追单，但不能把任意大K线都当成可追的强趋势。
- 开盘反转是时段场景，不是市场状态。
- Bailout 是持仓管理，不是入场战法或必然解套方法。
- 不按章节号匹配交易；只按当前市场环境和价格证据匹配。
- 每个含交易计划的回答末尾附上非投资建议声明。
