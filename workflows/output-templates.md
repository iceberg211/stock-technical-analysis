# 输出格式规范 (Output Templates)

> **本文件定义 AI 分析结果的输出格式。完成分析流程后读取本文件选择对应模板。**

---

## 输出分级

根据对话上下文选择输出详度：

| 模式 | 触发场景 | 输出内容 |
| ------ | --------- | --------- |
| **完整模式** | 首次分析 | 完整走 Step 0~8 + 标准输出模板 + 交易决策卡 + 免责声明 |
| **精简模式** | 追问/更新（如"现在呢""止损要调吗""新K线出来了"） | 只输出有变化的部分 + 结论更新 + 免责声明，不重复已分析过的不变内容 |
| **快问快答** | 单点问题（如"RSI 多少""支撑在哪"） | 直接回答 + 免责声明，不展开完整流程 |

---

## 标准输出模板（完整模式）

AI 完成分析后，按以下格式输出：

```text
#### 基础信息
- 品种: xxx
- 数据来源: [截图 / MCP / OHLC / 混合]
- 图表数量: [1张 / 2张及以上 / 无截图]
- 分析模式: [图片模式 / 数据模式 / 混合模式]
- 时间框架: [Direction=xxx, Signal=xxx, Entry=xxx 或 HTF=xxx, LTF=xxx 或 单一周期=xxx]

#### 市场结构
- 市场状态: [上升趋势 / 下降趋势 / 震荡 / 混乱]
- 关键 BOS/CHoCH: [描述]
- 趋势健康度: [健康 / 动量衰竭 / 可能反转]

#### 关键价位
- 阻力: xxx, xxx
- 支撑: xxx, xxx
- 当前位置: [支撑附近 / 阻力附近 / 中间]

#### 价格行为
- 近期动量: [多头主导 / 空头主导 / 犹豫不决 / 无法细判]
- 关键K线: [描述最近重要的K线特征]

#### 形态识别
- K线形态: [形态名称 或 无明显形态]
- 图表形态: [形态名称 或 无明显形态]
- 信号强度: [弱 / 中 / 强]

#### 指标信号（如可见）
- RSI: xxx
- MACD: xxx

#### 综合研判
- 偏向: [偏多 / 偏空 / 观望]
- 信心: [高 / 中 / 低]
- 多周期一致性: [一致 / 冲突 / 中性]
- 核心逻辑: [2-3 句，先讲结构，再讲位置与触发]
```

---

## 交易决策卡（有交易方案时附加）

```text
---

交易决策卡

### 决策结论
- 方向: [做多 / 做空 / 观望]
- 理由: [1-2 句话，只复述上面的综合研判，不新增证据]

### Setup & Checklist
- Playbook: [匹配的 Setup 名称 或 "无匹配"]
- 入场前检查:
  硬否决项: 3 / 4 / 5
  软降级项: 1 / 2 / 6 / 7
  结论: 通过 [仓位 100%] / 通过但降仓至 [x%] / 不做

### 交易方案（如通过检查）
- 入场: [价格或条件]
- 止损: [价格]（理由：xxx）
- 目标1: [价格]（R:R = x:1）
- 目标2: [价格]（可选）
- 仓位: [风险百分比或按公式反推的仓位]
- 失效条件: [什么情况方案失效]
- 持仓管理: [按 Playbook 差异化：趋势类 T1 减 30%，区间/反转类 T1 减 50%；均移止损至成本价]

> 以上分析仅供学习和参考，不构成任何投资建议。交易有风险，请基于自身判断做出决策，并自行承担所有风险。
```

---

## JSON 结构化输出（eval 模式）

> **本章节定义机器可解析的 JSON 输出格式，用于后续自动化评估（信心校准、一致性率、逐 Playbook 胜率统计）。**

### 触发规则

| 条件 | 行为 |
|------|------|
| 用户请求中包含 `--json` 标记 | 文本报告末尾（免责声明之前）额外输出 JSON 代码块 |
| 分析模式为「数据模式」 | 同上，自动输出 |
| 其他情况 | 不输出 JSON，仅输出文本报告 |

### JSON Schema

AI 必须严格按以下结构输出，所有枚举值只能从给定选项中选择，不可自由发挥。

```json
{
  "meta": {
    "symbol": "string",
    "interval": "string",
    "analysis_time": "string",
    "data_source": "screenshot | ohlc | mixed",
    "mtf_role": "direction | signal | entry | single"
  },
  "structure": {
    "market_state": "uptrend | downtrend | range | chaotic",
    "trend_health": "healthy | exhaustion | possible_reversal",
    "latest_bos_choch": "bos_bull | bos_bear | choch_bull | choch_bear | none",
    "swing_highs": [0.0],
    "swing_lows": [0.0]
  },
  "levels": {
    "resistances": [0.0],
    "supports": [0.0],
    "current_price": 0.0,
    "position": "near_support | near_resistance | middle"
  },
  "price_action": {
    "momentum": "bullish | bearish | indecisive | exhaustion | unclear",
    "key_candle": "string | null"
  },
  "pattern": {
    "candle_pattern": "string | null",
    "chart_pattern": "string | null",
    "signal_score": 0
  },
  "indicators": {
    "rsi": {
      "value": 0.0,
      "condition": "overbought | oversold | neutral | na"
    },
    "macd": {
      "histogram": "expanding | contracting | near_zero | na",
      "position": "above_zero | below_zero | na"
    }
  },
  "verdict": {
    "bias": "bullish | bearish | range_trade | watch",
    "confidence": "high | medium | low",
    "mtf_alignment": "aligned | conflicting | neutral | single_tf",
    "signal_strength": "strong | medium | weak"
  },
  "decision": {
    "action": "long | short | watch",
    "playbook": "trend-pullback | breakout-retest | range-reversal | false-breakout-reversal | flag-wedge-breakout | none",
    "checklist": {
      "htf_direction": "pass | fail | degraded",
      "position": "pass | fail | degraded",
      "setup_match": "pass | fail",
      "trigger": "pass | fail",
      "risk_reward": "pass | fail",
      "events": "pass | fail | degraded",
      "counter_reason": "pass | fail | degraded"
    },
    "checklist_result": "pass | pass_degraded | fail",
    "position_size_pct": 0.0
  },
  "trade": {
    "entry_price": 0.0,
    "stop_loss": 0.0,
    "t1": 0.0,
    "t2": 0.0,
    "risk_reward": 0.0,
    "trigger_type": "price_touch | close_above | close_below | null",
    "invalidation": "string | null"
  }
}
```

### 字段说明

| 对象 | 字段 | 说明 |
|------|------|------|
| `meta` | `symbol` | 标的代码，如 `"BTCUSDT"`、`"600000.SH"` |
| `meta` | `interval` | 主分析周期，如 `"4h"`、`"1d"` |
| `meta` | `analysis_time` | ISO 8601 UTC 时间戳 |
| `meta` | `mtf_role` | 当前图表在多周期分析中的角色 |
| `structure` | `swing_highs` / `swing_lows` | 最多 3 个主要 swing 价格，从近到远 |
| `pattern` | `signal_score` | 0~5 整数，对应 Step 5.3 信号强度评估 |
| `indicators` | `rsi.value` | 无 RSI 数据时设为 `null` |
| `decision` | `position_size_pct` | 最终仓位百分比（0~100），观望时为 `0` |
| `trade` | 所有字段 | 观望时（`action = "watch"`）全部设为 `null` |

### 观望场景示例

```json
{
  "meta": { "symbol": "BTCUSDT", "interval": "4h", "analysis_time": "2026-03-20T12:00:00Z", "data_source": "ohlc", "mtf_role": "single" },
  "structure": { "market_state": "chaotic", "trend_health": "possible_reversal", "latest_bos_choch": "choch_bear", "swing_highs": [88500.0], "swing_lows": [82100.0] },
  "levels": { "resistances": [88500.0, 91000.0], "supports": [82100.0, 79500.0], "current_price": 84200.0, "position": "middle" },
  "price_action": { "momentum": "indecisive", "key_candle": null },
  "pattern": { "candle_pattern": null, "chart_pattern": null, "signal_score": 0 },
  "indicators": { "rsi": { "value": 45.2, "condition": "neutral" }, "macd": { "histogram": "near_zero", "position": "below_zero" } },
  "verdict": { "bias": "watch", "confidence": "low", "mtf_alignment": "single_tf", "signal_strength": "weak" },
  "decision": { "action": "watch", "playbook": "none", "checklist": { "htf_direction": "pass", "position": "fail", "setup_match": "fail", "trigger": "fail", "risk_reward": "fail", "events": "pass", "counter_reason": "pass" }, "checklist_result": "fail", "position_size_pct": 0 },
  "trade": { "entry_price": null, "stop_loss": null, "t1": null, "t2": null, "risk_reward": null, "trigger_type": null, "invalidation": null }
}
```

---

## 历史回测样本 JSON（backtest_sample_v1）

> **本章节用于“历史滑窗重放回测”场景。**  
> 与上方 eval JSON 并存，不替换。回测时优先使用本章节格式，确保每个 case 都能被评分器直接消费。

### 输出要求（回测模式）

| 条件 | 行为 |
|------|------|
| 使用历史滑窗重放（run_eval） | 必须输出 `backtest_sample_v1` |
| 输出内容 | 仅输出一个 `json` 代码块，不附加额外解释文字 |
| 代码块数量 | 只能有一个，禁止多段 JSON |

### 回测双输出（推荐）

> 为了同时满足“可读分析过程”和“机器可评分回测”，建议在落盘阶段做双输出。

| 文件 | 目的 |
|------|------|
| `analysis_report.md` | 给人阅读，保留 Step 0~8 的分析过程、关键位、决策理由 |
| `backtest_sample_v1.json` | 给评分器读取，保证字段稳定可回测 |

推荐目录结构：

```text
<run_root>/<symbol>/cases/<case_id>/run_<n>/
  ├── analysis_report.md
  └── backtest_sample_v1.json
```

### Schema（backtest_sample_v1）

```json
{
  "meta": {
    "schema_version": "backtest_sample_v1",
    "symbol": "string",
    "interval": "string",
    "case_id": "string",
    "analysis_time": "string",
    "lookback_bars": 0,
    "forward_bars": 0,
    "data_source": "screenshot | ohlc | mixed"
  },
  "decision": {
    "action": "long | short | watch",
    "playbook": "trend-pullback | breakout-retest | range-reversal | false-breakout-reversal | flag-wedge-breakout | none",
    "checklist": {
      "htf_direction": "pass | fail | degraded",
      "position": "pass | fail | degraded",
      "setup_match": "pass | fail",
      "trigger": "pass | fail",
      "risk_reward": "pass | fail",
      "events": "pass | fail | degraded",
      "counter_reason": "pass | fail | degraded"
    },
    "checklist_result": "pass | pass_degraded | fail",
    "position_size_pct": 0.0
  },
  "trade": {
    "entry_price": 0.0,
    "stop_loss": 0.0,
    "t1": 0.0,
    "t2": 0.0,
    "risk_reward": 0.0,
    "trigger_type": "price_touch | close_above | close_below | null",
    "invalidation": "string | null"
  },
  "verdict": {
    "bias": "bullish | bearish | range_trade | watch",
    "confidence": "high | medium | low",
    "signal_strength": "strong | medium | weak"
  },
  "structure": {
    "market_state": "uptrend | downtrend | range | chaotic"
  }
}
```

### 约束规则（强制）

1. `meta.schema_version` 必须是 `backtest_sample_v1`。  
2. `meta` 必填：`symbol`、`interval`、`case_id`、`analysis_time`、`lookback_bars`、`forward_bars`、`data_source`。  
3. `decision` 必填：`action`、`playbook`、`checklist`、`checklist_result`、`position_size_pct`。  
4. `trade` 必填：`entry_price`、`stop_loss`、`t1`、`t2`、`risk_reward`、`trigger_type`、`invalidation`。  
5. 当 `decision.action = "watch"` 时，`trade` 内所有数值字段必须为 `null`。  
6. 当 `decision.action = "long"` 或 `"short"` 时，`trade.entry_price`、`trade.stop_loss`、`trade.t1` 必须为数字。  
7. 所有枚举字段必须命中白名单，不可输出自定义值。  
8. 回测模式下只允许一个 JSON 代码块，禁止输出“文本解释 + JSON”混合格式。

### backtest_sample_v1 示例（做多）

```json
{
  "meta": {
    "schema_version": "backtest_sample_v1",
    "symbol": "SH.600410",
    "interval": "1h",
    "case_id": "case_0001_20260320T150000",
    "analysis_time": "2026-03-22T08:30:00Z",
    "lookback_bars": 160,
    "forward_bars": 40,
    "data_source": "ohlc"
  },
  "decision": {
    "action": "long",
    "playbook": "breakout-retest",
    "checklist": {
      "htf_direction": "pass",
      "position": "pass",
      "setup_match": "pass",
      "trigger": "pass",
      "risk_reward": "pass",
      "events": "pass",
      "counter_reason": "degraded"
    },
    "checklist_result": "pass_degraded",
    "position_size_pct": 50.0
  },
  "trade": {
    "entry_price": 27.9,
    "stop_loss": 26.8,
    "t1": 30.1,
    "t2": 31.6,
    "risk_reward": 2.0,
    "trigger_type": "close_above",
    "invalidation": "1H 收盘跌回 26.8 下方"
  },
  "verdict": {
    "bias": "bullish",
    "confidence": "medium",
    "signal_strength": "medium"
  },
  "structure": {
    "market_state": "uptrend"
  }
}
```

---

## AI 注意事项

1. **不要跳步**：必须从 Step 0 开始，逐步分析
2. **先分析后结论**：先完成 Step 0~7，再输出 Step 8；不要边分析边下方向或点位
3. **承认看不清**：如果图片模糊或信息不完整，主动向用户确认
4. **不要过度解读**：看不到的信号不要猜，宁可说"无法判断"
5. **数据优先**：同一问题同时有图片和数据时，以结构化数据为准
6. **图片保守**：只有截图且 K 线细节不清时，不做微观 K 线强判断
7. **最小读取**：不要为了走流程机械打开所有 references，默认用 workflow 内置规则
8. **概率表述**：用"倾向于"、"可能"、"大概率"，不用"一定会"
9. **风控必须有**：即使用户没问，交易方案也必须包含止损
10. **多时间框架提醒**：如果只看到一个时间框架，提醒用户确认更大时间框架的方向
11. **禁止编造价位**：如果价格刻度不可读或数据不足，绝对不能编造具体价格数字，只能用条件描述
12. **免责声明（强制）**：每次输出分析报告末尾必须附加免责声明
13. **多图先看高周期**：同品种多周期分析时，必须先以 HTF 定方向，再用 LTF 找触发；若冲突则观望
14. **必须匹配 Playbook**：输出方案前，必须先匹配 setup；不匹配则不给方案
15. **必须过 Checklist**：匹配 Playbook 后，必须先完成检查，全部通过才给方案
16. **仓位必算**：交易方案中必须给出风险百分比或按公式反推的仓位建议
17. **持仓管理按 Playbook 差异化**：趋势类（trend-pullback、flag-wedge-breakout）T1 减仓 30%；区间/反转类（range-reversal、false-breakout-reversal、breakout-retest）T1 减仓 50%；用户追问细节时再读取 `references/checklists/in-trade-management.md`
18. **JSON 输出（eval 模式）**：当用户请求包含 `--json` 或分析模式为数据模式时，文本报告末尾必须输出 JSON 结构化代码块。枚举值必须严格使用本文件定义的选项，不能自由发挥。观望时 `decision.action = "watch"`，`trade` 对象所有数值字段设为 `null`。如果已输出 JSON 块，不需要再单独输出回测锚点表格
