# 输出格式规范 (Output Templates)

> 本文件定义 AI 分析结果的输出格式。完成分析流程后读取本文件选择对应模板。

---

## 输出分级

| 模式 | 触发场景 | 输出内容 |
| ------ | --------- | --------- |
| 完整模式 | 首次分析 | 完整走 Step 0~8 + 交易决策卡 + 免责声明 |
| 精简模式 | 追问/更新（如“现在呢”“止损要调吗”） | 只输出变化项 + 结论更新 + 免责声明 |
| 快问快答 | 单点问题（如“支撑在哪”） | 直接回答 + 免责声明 |

---

## 标准输出模板（完整模式）

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
- 量能结论: [放量上涨 / 放量下跌 / 缩量整理 / 量价背离 / 量能数据不可用]

#### 形态识别
- K线形态: [形态名称 或 无明显形态]
- 图表形态: [形态名称 或 无明显形态]
- 信号强度: [弱 / 中 / 强]

#### 指标信号（如可见）
- RSI背离: [常规看涨 / 常规看跌 / 隐形看涨 / 隐形看跌 / 无背离 / 无数据]（价格锚点: x->y, RSI锚点: a->b）
- MACD背离: [常规看涨 / 常规看跌 / 隐形看涨 / 隐形看跌 / 无背离 / 无数据]（价格锚点: x->y, MACD锚点: a->b）
- RSI数值: xxx（仅辅助，不独立触发）
- MACD数值: xxx（仅辅助，不独立触发）
- 指标确认: [背离确认 / 无背离仅数值参考 / 无指标可判断]

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
  硬否决项:
  - Setup 匹配: [✅ / ⚠️ / ❌]（原因：一句话）
  - 触发信号: [✅ / ⚠️ / ❌]（原因：一句话）
  - 盈亏比(R:R): [✅ / ⚠️ / ❌]（原因：一句话）
  软降级项:
  - HTF 方向一致性: [✅ / ⚠️ / ❌]（原因：一句话）
  - 位置有效性: [✅ / ⚠️ / ❌]（原因：一句话）
  - 事件风险: [✅ / ⚠️ / ❌]（原因：一句话）
  - 否决理由检查: [✅ / ⚠️ / ❌]（原因：一句话）
  结论: [通过（标准仓位） / 通过但降仓至 x% / 不做]

### 交易方案（如通过检查）
- 入场: [价格或条件]
- 止损: [价格]（理由：xxx）
- 目标1: [价格]（R:R = x:1）
- 目标2: [价格]（可选）
- 仓位: [风险百分比或按公式反推的仓位]
- 失效条件: [什么情况方案失效]
- 持仓管理: [按 Playbook 差异化：趋势类 T1 减 30%，区间/反转类 T1 减 50%；均移止损至成本价]

> 以上分析仅供学习和参考，不构成投资建议。交易有风险，请基于自身判断做出决策，并自行承担所有风险。
```

---

## JSON 结构化输出（eval 模式）

### 触发规则

- 用户请求包含 `--json`。
- 或分析模式为数据模式（OHLC/MCP）。

### 核心数据结构（TypeScript）

```typescript
type PositionSizePct = number; // 0~100，观望时为 0

interface SharedStructure {
  decision: {
    action: "long" | "short" | "watch";
    playbook: "trend-pullback" | "breakout-retest" | "range-reversal" | "false-breakout-reversal" | "flag-wedge-breakout" | "none";
    checklist: {
      htf_direction: "pass" | "fail" | "degraded";
      position: "pass" | "fail" | "degraded";
      setup_match: "pass" | "fail";
      trigger: "pass" | "fail";
      risk_reward: "pass" | "fail";
      events: "pass" | "fail" | "degraded";
      counter_reason: "pass" | "fail" | "degraded";
    };
    checklist_result: "pass" | "pass_degraded" | "fail";
    position_size_pct: PositionSizePct;
  };
  trade: {
    entry_price: number | null;
    stop_loss: number | null;
    t1: number | null;
    t2: number | null;
    risk_reward: number | null;
    trigger_type: "price_touch" | "close_above" | "close_below" | null;
    invalidation: string | null;
  };
  verdict: {
    bias: "bullish" | "bearish" | "range_trade" | "watch";
    confidence: "high" | "medium" | "low";
    signal_strength: "strong" | "medium" | "weak";
    mtf_alignment?: "aligned" | "conflicting" | "neutral" | "single_tf";
  };
}

interface EvalJSON extends SharedStructure {
  meta: {
    symbol: string;
    interval: string;
    analysis_time: string; // ISO 8601 UTC
    data_source: "screenshot" | "ohlc" | "mixed";
    mtf_role: "direction" | "signal" | "entry" | "single";
  };
  structure: {
    market_state: "uptrend" | "downtrend" | "range" | "chaotic";
    trend_health: "healthy" | "exhaustion" | "possible_reversal";
    latest_bos_choch: "bos_bull" | "bos_bear" | "choch_bull" | "choch_bear" | "none";
    swing_highs: number[];
    swing_lows: number[];
  };
  levels: {
    resistances: number[];
    supports: number[];
    current_price: number;
    position: "near_support" | "near_resistance" | "middle";
  };
  price_action: {
    momentum: "bullish" | "bearish" | "indecisive" | "exhaustion" | "unclear";
    key_candle: string | null;
    volume_state: "expanding" | "normal" | "contracting" | "na";
    volume_price_alignment: "bull_confirm" | "bear_confirm" | "breakout_confirm" | "breakout_weak" | "divergent" | "na";
  };
  pattern: {
    candle_pattern: string | null;
    chart_pattern: string | null;
    signal_score: number; // 0~5
  };
  indicators: {
    rsi: {
      value: number | null;
      condition: "overbought" | "oversold" | "neutral" | "na";
      divergence: "bullish_regular" | "bearish_regular" | "bullish_hidden" | "bearish_hidden" | "none" | "na";
      anchor_price: [number, number] | null;
      anchor_indicator: [number, number] | null;
    };
    macd: {
      histogram: "expanding" | "contracting" | "near_zero" | "na";
      position: "above_zero" | "below_zero" | "na";
      divergence: "bullish_regular" | "bearish_regular" | "bullish_hidden" | "bearish_hidden" | "none" | "na";
      anchor_price: [number, number] | null;
      anchor_indicator: [number, number] | null;
    };
  };
}
```

> 强制要求：当 `decision.action = "watch"` 时，`trade` 下所有字段必须为 `null`，`position_size_pct` 必须为 `0`。

---

## 历史回测样本 JSON（backtest_sample_v1）

> 仅在历史滑窗重放且要求单段纯 JSON 时触发。

```typescript
interface BacktestJSON extends SharedStructure {
  meta: {
    schema_version: "backtest_sample_v1";
    symbol: string;
    interval: string;
    case_id: string;
    analysis_time: string;
    lookback_bars: number;
    forward_bars: number;
    data_source: "screenshot" | "ohlc" | "mixed";
  };
  structure: {
    market_state: "uptrend" | "downtrend" | "range" | "chaotic";
  };
}
```

---

## AI 注意事项

1. 不要跳步：必须从 Step 0 开始。
2. 先分析后结论：先完成 Step 0~7，再输出 Step 8。
3. 指标段必须先给 RSI/MACD 背离结论，再给数值辅助。
4. 无背离时必须显式写“无背离”，不能省略。
5. 单靠超买超卖、金叉死叉、零轴位置不得上调高信心。
6. 有 volume 字段时必须输出“量能结论”；无 volume 时明确写“量能数据不可用”。
7. 数据优先：结构化数据 > 用户指定值 > 清晰截图 > 模糊截图。
8. 不要编造价位：刻度不可读时改为条件描述。
9. Checklist 禁止只写编号（如“3/4/5”），必须写项目中文名与原因。
10. 每次文本输出末尾都要附加免责声明。
