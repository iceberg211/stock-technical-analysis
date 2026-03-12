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
- 默认按 workflow 内置规则完成分析，不要为了走流程而机械读取所有 `references/` 文件。
- 仅在遇到模糊形态、少见指标、复杂 Playbook 分歧时，再按最小必要原则读取单个 reference 文件。
- 只有图片、且价格刻度或最近几根 K 线细节不清晰时，只输出结构与条件，不输出具体价位或微观 K 线断言。
- 每次输出含交易分析的回复，末尾必须附加免责声明。

## 模式路由

| 用户意图 | 加载路径 |
|------|---------|
| 上传一张或多张同品种 K 线图，要求分析走势 | `workflows/chart-analysis-workflow.md` |
| 要求完整技术分析或多时间框架联动分析 | `workflows/chart-analysis-workflow.md` |
| 要求使用 MCP / OHLC / 实时行情数据分析 | `workflows/chart-analysis-workflow.md` |

## 知识加载

### 分析层（"市场现在像什么"）

> 默认先使用 `workflows/chart-analysis-workflow.md` 中的内置判断规则；只有在边界情况时才继续打开以下 references。

- 趋势、方向、HH/HL/LH/LL、BOS、CHoCH、摆动高低点：
  `references/core/INDEX.md` -> `references/core/market-structure.md`
- 支撑、阻力、翻转、区域、画线：
  `references/core/INDEX.md` -> `references/core/support-resistance.md`
- 价格行为、突破真假、当前 K 线力度：
  `references/core/INDEX.md` -> `references/core/price-action.md`
- K 线形态：
  `references/patterns/INDEX.md` -> `references/patterns/candlestick-patterns.md`
- 图表形态：
  `references/patterns/INDEX.md` -> `references/patterns/chart-patterns.md`
- RSI、MACD、SMC：
  `references/indicators/INDEX.md` -> 对应指标文件
- 需要总纲时：
  `references/overview.md`

### 交易计划层（"这是不是我的 setup，怎么做"）

- 顺势回调 / 突破回踩 / 区间反转等交易 setup：
  `references/playbooks/INDEX.md` -> 对应 playbook 文件
- 入场前过滤、持仓管理：
  `references/checklists/INDEX.md` -> 对应检查单文件
- 仓位计算、风险控制：
  `references/risk/INDEX.md` -> `references/risk/position-sizing.md`

## 输出约束

- 用概率语言表达结论，不做确定性承诺。
- 优先给条件式交易计划，而不是绝对价位断言。
- 图表信息不足时，停止推进到具体执行建议。
