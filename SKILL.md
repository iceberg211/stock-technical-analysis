---
name: stock-technical-analysis
description: |
  股票、期货、加密货币的技术分析与条件式交易计划工作流。核心功能：
  图表分析、多时间框架联动、关键位识别、结构判断、Playbook 匹配、
  入场前检查与风险控制。用户上传 K 线图、请求技术分析、判断走势、
  寻找关键点位、制定交易计划，或要求使用 MCP / OHLC 行情数据时使用。
---

# 技术分析 Skill

> 核心理念：结构定方向，行为定时机，Playbook 定执行。

## 使用规则

- 优先使用 MCP / OHLC / 结构化行情数据；截图用于辅助确认结构、关键位与形态。
- 先识别用户是图片分析、数据分析，还是二者结合，再加载 workflow。
- 先识别市场类型，再决定数据源与默认周期，禁止把 A 股、美股、港股和币圈按同一套周期模板处理。
- 默认按 workflow 内置规则完成分析，不要为了走流程而机械读取所有 `references/` 文件。
- 仅在遇到模糊形态、少见指标、复杂 Playbook 分歧时，再按最小必要原则读取单个 reference 文件。
- 只有图片、且价格刻度或最近几根 K 线细节不清晰时，只输出结构与条件，不输出具体价位或微观 K 线断言。
- RSI / MACD 判断遵循“背离优先、数值辅助”原则：先给背离状态；有候选或已确认关系时给类型与成对锚点，再补充超买超卖、零轴、金叉死叉等信息。
- 数据中存在 `volume` 时，必须执行量价一致性判断；缺失 `volume` 时必须显式写明“量能数据不可用”。
- 每次输出含交易分析的回复，末尾必须附加免责声明。

## 模式路由

| 用户意图 | 加载路径 |
|------|---------|
| 上传一张或多张同品种 K 线图，要求分析走势 | `workflows/chart-analysis-workflow.md`（分析流程 Step 0~7） |
| 要求完整技术分析或多时间框架联动分析 | `workflows/chart-analysis-workflow.md`（分析流程 Step 0~7） |
| 只给标的名称 / 代码，要求主动拉取结构化数据分析 | `workflows/batch-fast-path.md`（支持的单标的和多标的均从此进入） |
| 要求使用 MCP / OHLC / 实时行情数据分析 | 先检查 `workflows/batch-fast-path.md` 的市场与周期范围 |
| 一次分析多个标的，不要求历史信号复盘 | `workflows/batch-fast-path.md`（自带取数、分析和报告规则） |
| 分析完成后需要输出交易方案 | `workflows/trading-decision.md`（Playbook 匹配、Checklist、仓位、回测） |
| 输出格式选择 | `workflows/output-templates.md`（标准模板、决策卡、AI 注意事项） |
| 每日复盘，且要求验证历史信号 | `workflows/daily-review.md`（持仓清单 → 逐标的分析 → 信号验证 → 汇总） |

## Workflow 顺序

普通结构化行情问答，不论单标的还是多标的，先读 `workflows/batch-fast-path.md`。固定处理器支持A股日线与分钟线、美股日线与15m/30m/60m、币圈现货日线与4h/60m/30m/15m；只读取本入口与快速流程，币圈取数再加载 `spot` skill，使用同一个处理器完成校验、指标和摘要。需要详细定义、其他市场适配、交易方案或历史复盘时，再加载对应文件的相关段落。

用户明确要求逐步展开完整流程、图像分析，或快速入口不支持的市场、周期，按以下顺序执行：

1. `workflows/data-acquisition-workflow.md`
2. `workflows/chart-analysis-workflow.md`
3. `workflows/trading-decision.md`（仅在需要交易方案时）
4. `workflows/output-templates.md`

## 数据获取约定

完整细则移动到 `workflows/data-acquisition-workflow.md`，本文件只保留总约束：

- 先分市场，再取数，再分析。
- A 股、港股、美股默认模板是 `1D + 60m`，币圈默认模板是 `4H + 1H`。
- 股票市场默认直接使用 Yahoo Finance chart API；用户明确指定 Yahoo 时，跳过长桥探测和其他行情源。只有 Yahoo 不可用、数据不完整或不满足请求周期时，才尝试长桥，并记录 `source_fallback_reason`。
- Yahoo 每个 `provider_symbol + interval` 直接取得 `meta + OHLCV`；一次性分析只请求用户指定周期。允许调用仓库固定处理器完成内存校验、指标和摘要；不新建或运行临时本地脚本、不写缓存。
- 长桥仅作为备用源；使用时记录实际 `data_channel`、`provider_symbol`、`adjust_type` 与 `trade_session`。
- 加密货币现货优先使用 `spot` skill 获取 Binance Spot 公开行情数据；只有 `spot` skill 不可用或接口失败时，才进入本地缓存回退。
- 股票市场不再进入 AKShare、新浪或腾讯回退链；Yahoo 失败后只尝试长桥。
- A 股 `4H` 只能由 `60m` 派生，不能把外部 `4H` 当默认真值。
- 美股 `4H` 若数据源无原生周期，必须由常规交易时段 `60m` 本地聚合得到，并在输出中写明 `derived_from=60m`。
- 分析层必须使用固定窗口，不直接吃全量历史响应或持久化数据。
- 只要使用了结构化数据，最终输出必须保留 `data_channel / requested_bars / actual_bars / analysis_bars / timeframe_status`。

## 知识加载

### 分析层（"市场现在像什么"）

> 默认先使用 `workflows/chart-analysis-workflow.md` 中的内置判断规则；只有在边界情况时才继续打开以下 references。

- 趋势、方向、HH/HL/LH/LL、BOS、CHoCH、摆动高低点：
  `references/core/INDEX.md` -> `references/core/market-structure.md`
- 支撑、阻力、翻转、区域、画线：
  `references/core/INDEX.md` -> `references/core/support-resistance.md`
- 价格行为、突破真假、当前 K 线力度：
  `references/core/INDEX.md` -> `references/core/price-action.md`
- 成交量、量能、量价配合：
  `references/core/INDEX.md` -> `references/core/volume-analysis.md`
- K 线形态：
  `references/patterns/INDEX.md` -> `references/patterns/candlestick-patterns.md`
- 图表形态：
  `references/patterns/INDEX.md` -> `references/patterns/chart-patterns.md`
- RSI、MACD：
  `references/indicators/INDEX.md` -> 对应指标文件
- 需要总纲时：
  `references/overview.md`

### 交易计划层（"这是不是我的 setup，怎么做"）

- 顺势回调 / 突破回踩 / 区间反转 / 假突破反转 / 旗形楔形突破等交易 setup：
  `references/playbooks/INDEX.md` -> 对应 playbook 文件
- 入场前过滤、持仓管理：
  `references/checklists/INDEX.md` -> 对应检查单文件
- 仓位计算、风险控制：
  `references/risk/INDEX.md` -> `references/risk/position-sizing.md`

## 信号归档

每次产出含交易方案的分析，必须归档信号到共享数据目录：

```
~/.trading-data/signals/{SYMBOL}/{signal_id}/
  snapshot.json    — 完整分析快照（结构化 JSON）
  report.md        — 人可读分析报告
~/.trading-data/signals/{SYMBOL}/index.jsonl  — 追加式索引
```

数据目录默认 `~/.trading-data/`，可通过 `TRADING_DATA_DIR` 环境变量覆盖。

## 输出约束

- 用概率语言表达结论，不做确定性承诺。
- 优先给条件式交易计划，而不是绝对价位断言。
- 图表信息不足时，停止推进到具体执行建议。
- 指标段区分“无背离 / 候选 / 已确认 / 无法判断”；候选或已确认背离给出成对锚点。缺少锚点或预热不足写“无法判断”，不能写成“无背离”。数值关系不能自动升级为交易确认。
- Checklist 段必须写项目中文名与原因，禁止仅用编号（如 3/4/5）表达状态。
