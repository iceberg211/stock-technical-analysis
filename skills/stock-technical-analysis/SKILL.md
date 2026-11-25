---
name: stock-technical-analysis
description: 使用通用技术分析方法判断股票、期货和加密货币的趋势结构、BOS/CHoCH、支撑阻力、K线与图表形态、成交量以及 RSI/MACD，并匹配通用 Playbook。用于用户明确要求技术分析、指标分析、形态分析、综合技术分析或持仓复盘时；不作为 Al Brooks Price Action 的前置数据工具，也不负责行情缓存和账户风险计算。
---

# 通用技术分析

## 目标与边界

- 负责通用市场结构、关键位、形态、量价、指标和通用 Playbook。
- 不拥有行情接口、缓存、复权和增量聚合；缺少结构化行情时先使用 `$market-data`。
- 不作为 `$price-action-decision` 的前置步骤。用户明确要求联合分析时，两者读取同一行情快照并分别判断，再说明一致与冲突证据。
- 不计算账户仓位；需要风险计划时把已确认战法、逻辑止损和目标交给 `$trade-risk`。
- 不自动归档、不自动下单、不做确定性收益承诺。

## 分析模式

| 模式 | 内容 |
|---|---|
| `structure` | 趋势、摆动、BOS/CHoCH、关键位和当前位置 |
| `indicator` | RSI/MACD 背离、均线和量价 |
| `complete` | 结构、位置、形态、指标和通用 Playbook |
| `combined` | 与 Price Action 或订单流平级比较，不相互覆盖 |

只有 `indicator` 和 `complete` 模式强制给出 RSI/MACD 背离结论。有 `volume` 且模式包含量价分析时，才执行量价一致性判断；缺失 `volume` 时显式写明“量能数据不可用”。

## 路由

| 用户意图 | 执行路径 |
|---|---|
| 用户提供清晰图表 | `workflows/chart-analysis-workflow.md` |
| 只给标的或要求行情数据 | `$market-data` -> `workflows/chart-analysis-workflow.md` |
| 要求通用交易方案 | 分析 workflow -> `workflows/trading-decision.md` |
| 要求账户仓位或风险金额 | 已确认方案 -> `$trade-risk` |
| 每日复盘或持仓巡检 | `workflows/daily-review.md` |

## Workflow 顺序

1. 没有数据时使用 `$market-data` 取得统一无缓存行情快照。
2. 使用 `workflows/chart-analysis-workflow.md` 完成所选模式的证据分析。
3. 需要通用交易方案时读取 `workflows/trading-decision.md`。
4. 使用 `workflows/output-templates.md` 输出。
5. 仅在用户明确要求持久化时才保存信号；盘中只保存实质状态变化。

`workflows/data-acquisition-workflow.md` 仅保留旧调用兼容说明，不再定义数据源和缓存规则。

## 知识加载

默认使用 chart workflow 的内置规则，不要为了走流程机械打开全部 `references/`。只有遇到边界情况或争议时按需读取：

- 市场结构：`references/core/market-structure.md`
- 支撑阻力：`references/core/support-resistance.md`
- 通用价格行为：`references/core/price-action.md`
- 成交量：`references/core/volume-analysis.md`
- K 线和图表形态：`references/patterns/`
- RSI / MACD：`references/indicators/`
- 通用 Playbook：`references/playbooks/`
- 入场前检查与持仓管理：`references/checklists/`

> `strategies/*.yaml` 仅供外部回测引擎作近似参数使用，AI 分析不读取；AI 止损与目标位以 `references/playbooks/*.md` 和 `workflows/trading-decision.md` 的结构位规则为准。

## 多周期原则

- 各周期先独立描述，再判断是否一致。
- 高低周期冲突是证据，不是跨所有交易体系的自动否决。
- 对顺势 Playbook，方向冲突通常否决；对区间、反转或用户明确指定的目标周期，保留条件式判断并降低信心。
- 联合 Price Action 时，不把 BOS/CHoCH、Fib、指标评分翻译成 Brooks 的 Always In 或市场周期。

## 信号持久化

只有用户明确要求记录，或运行环境已启用持久化配置时，才写入共享数据目录（默认 `~/.trading-data/signals/{SYMBOL}/{signal_id}/`，可通过 `TRADING_DATA_DIR` 覆盖）。普通问答不产生外部文件；盘中相同事件不得重复归档。

## 输出约束

- 使用概率和条件语言，优先给条件式计划，不做绝对价位断言或确定性收益承诺。
- 图表或数据不足时停止推进到精确价位；若行情快照存在复权、缺口或跨周期校验告警（`data_quality_warning` / `cross_timeframe_warning`），按 `degraded_quality` 显式披露限制，不将异常数据的精确高低价当作可靠触发价。
- 指标段遵循“背离优先、数值辅助”与四态判定（`无背离 / 候选 / 已确认 / 无法判断`）：缺少成对已确认锚点、指标预热不足或数据质量无法支持比较时写 `无法判断`，不能冒充 `无背离`；数值满足关系仅作 `候选`，需结合主要结构相关性与价格确认才能升级为 `已确认`；无背离或无法判断时锚点写 `N/A`，不得虚构。
- Checklist 段必须写项目中文名与原因，禁止仅用编号（如 `3/4/5`）表达状态。
- 联合分析必须标明每条证据来自哪个分析器。
- 免责声明：完整模式、交易决策卡及涉及价位（入场/止损/目标）的更新**必须**在末尾附加非投资建议声明；纯概念澄清或单点快问快答可不附加。
