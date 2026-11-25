# 输出格式规范 (Output Templates)

> 本文件定义 AI 分析结果的输出格式。完成分析流程后读取本文件选择对应模板。

---

## 输出分级

| 模式 | 触发场景 | 输出内容 |
| ------ | --------- | --------- |
| 完整模式 | 首次分析 | 先通过 `$market-data` 取得快照（如需），再走 Step 0~8 + 交易决策卡（如有方案）+ 免责声明 |
| 精简模式 | 追问/更新（如“现在呢”“止损要调吗”） | 只输出变化项 + 结论更新；若涉及入场/止损/目标价位则附免责声明，纯概念澄清可不附 |
| 快问快答 | 单点问题（如“支撑在哪”） | 直接回答；不附加免责声明（避免噪音） |

---

## 标准输出模板（完整模式）

```text
#### 基础信息
- 品种: xxx
- 市场类型: [cn / us / hk / crypto / futures / forex]
- 数据来源: [截图 / $market-data / 用户提供 OHLC / 混合]
- 数据通道: [按 $market-data 快照如实填写 source / data_channel，如 tencent:fqkline:qfqday / sina:cn:60m / yahoo:chart / binance:spot 等]
- 数据参数: [provider_symbol=xxx, adjust_type=xxx, trade_session=xxx]
- 样本窗口: [fetched_complete_bars=xxx, analysis_bars_count=xxx（外部原始输入可写 requested_bars / actual_bars / analysis_bars）]
- 周期状态: [1d=complete, 60m=degraded_quality / degraded_recent_only, 15m=complete ...]
- 回退与质量告警: [source_fallback_reason=无/具体原因; data_quality_warning=无/具体告警; cross_timeframe_warning=无/具体告警]
- 数据完整性: [完整 / 降级(degraded_quality 或 degraded_recent_only)]（原因: xxx）
- 图表数量: [1张 / 2张及以上 / 无截图]
- 分析模式: [数据模式 / 图片模式 / 混合模式]（子模式: [structure / indicator / complete / combined]）
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
- 近期动量: [多头主导 / 空头主导 / 犹豫不决 / 动量衰竭 / 无法细判]
- 关键K线: [描述最近重要的K线特征]
- 量能结论: [放量上涨 / 放量下跌 / 缩量整理 / 量价背离 / 量能数据不可用]（有量时区分末根量比与近 5 根均量特征）

#### 形态识别
- K线形态: [形态名称 或 无明显形态]
- 图表形态: [形态名称 或 无明显形态]
- 信号强度: [弱 / 中 / 强]（hits/applicable_items = score_ratio）

#### 指标信号（仅 indicator / complete 模式输出；structure 模式可省略）
- RSI背离: [无背离 / 候选 / 已确认 / 无法判断]（有候选或已确认关系时给类型、价格锚点: x->y, RSI锚点: a->b；否则锚点填 N/A）
- MACD背离: [无背离 / 候选 / 已确认 / 无法判断]（有候选或已确认关系时给类型、价格锚点: x->y, DIF锚点: a->b；否则锚点填 N/A）
- RSI数值: xxx（仅辅助，不独立触发）
- MACD数值: xxx（仅辅助，不独立触发；注明柱状图口径）
- 指标确认: [背离确认 / 候选待价格确认 / 无背离仅数值参考 / 无法判断]

#### 综合研判
- 偏向: [偏多 / 偏空 / 区间交易 / 观望]
- 信心: [高 / 中 / 低]
- 多周期一致性: [一致 / 冲突 / 中性 / 单周期]
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
  - Setup 匹配: [✅ / ❌]（原因：一句话）
  - 触发信号: [✅ / ❌]（原因：一句话）
  - 收益风险关系: [✅ / ⚠️ / ❌]（原因：目标是否来自可到达结构；不套跨体系统一固定门槛）
  混合项（❌ 否决，⚠️ 降级）:
  - HTF 方向一致性: [✅ / ⚠️ / ❌]（原因：一句话）
  - 位置有效性: [✅ / ⚠️ / ❌]（原因：一句话）
  软降级项:
  - 事件风险: [✅ / ⚠️ / ❌]（原因：一句话）
  - 否决理由检查: [✅ / ⚠️ / ❌]（原因：一句话）
  结论: [通过（标准预期） / 通过但降级处理 / 不做]

### 交易方案（如通过检查）
- 入场: [价格或条件]
- 止损: [价格]（理由：xxx）
- 目标1: [价格]（R:R = x:1）
- 目标2: [价格]（可选）
- 仓位: [未要求时写“未计算”；需要时交给 $trade-risk]
- 失效条件: [什么情况方案失效]
- 持仓管理: [按 Playbook 差异化：趋势类 T1 减 30%，区间/反转类 T1 减 50%；均移止损至成本价]

> 以上分析仅供学习和参考，不构成投资建议。交易有风险，请基于自身判断做出决策，并自行承担所有风险。
```

---

## JSON 结构化输出（eval 模式）

### 触发规则

- 用户请求包含 `--json`。
- 或用户明确要求 eval / 结构化 JSON 输出。普通行情快照问答默认输出人可读报告。

### 核心数据结构（TypeScript）

```typescript
type PositionSizePct = number | null; // 未经 $trade-risk 计算或观望时为 null / 0

interface SharedStructure {
  decision: {
    action: "long" | "short" | "watch";
    playbook: "trend-pullback" | "breakout-retest" | "range-reversal" | "false-breakout-reversal" | "flag-wedge-breakout" | "none";
    checklist: {
      htf_direction: "pass" | "fail" | "degraded";
      position: "pass" | "fail" | "degraded";
      setup_match: "pass" | "fail";
      trigger: "pass" | "fail";
      risk_reward: "pass" | "fail" | "degraded";
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
    market: "cn" | "us" | "hk" | "crypto" | "cn_equity" | "us_equity" | "hk_equity" | "crypto_spot" | "other";
    interval: string;
    analysis_time: string; // ISO 8601 UTC
    data_source: "screenshot" | "ohlc" | "mixed";
    source_name?: string;
    data_channel?: string;
    provider_symbol?: string;
    adjust_type?: string;
    trade_session?: string;
    fetched_complete_bars?: number;
    analysis_bars_count?: number;
    requested_bars?: number;
    actual_bars?: number;
    analysis_bars?: number;
    derived_from?: string | null;
    is_complete?: boolean;
    source_fallback_reason?: string | null;
    data_quality_warning?: string[] | null;
    cross_timeframe_warning?: string | null;
    degrade_reason?: string | null;
    timeframe_status?: Record<string, string>;
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
    mean5_volume_ratio?: number | null;
    volume_price_alignment: "bull_confirm" | "bear_confirm" | "breakout_confirm" | "breakout_weak" | "divergent" | "na";
  };
  pattern: {
    candle_pattern: string | null;
    chart_pattern: string | null;
    signal_score_hits?: number;
    applicable_items?: number;
    signal_score_ratio?: number; // 0~1
    signal_score?: number; // 兼容旧消费方
  };
  indicators: {
    rsi: {
      divergence_status: "none" | "candidate" | "confirmed" | "insufficient";
      value: number | null;
      condition: "overbought" | "oversold" | "neutral" | "na";
      divergence: "bullish_regular" | "bearish_regular" | "bullish_hidden" | "bearish_hidden" | "none" | "na";
      anchor_price: [number, number] | null; // 无背离或无法判断时为 null
      anchor_indicator: [number, number] | null;
    };
    macd: {
      divergence_status: "none" | "candidate" | "confirmed" | "insufficient";
      histogram: "expanding" | "contracting" | "near_zero" | "na";
      position: "above_zero" | "below_zero" | "na";
      divergence: "bullish_regular" | "bearish_regular" | "bullish_hidden" | "bearish_hidden" | "none" | "na";
      anchor_price: [number, number] | null; // 无背离或无法判断时为 null
      anchor_indicator: [number, number] | null;
    };
  };
}
```

> 强制要求：当 `decision.action = "watch"` 时，`trade` 下所有字段必须为 `null`，`position_size_pct` 为 `0` 或 `null`。

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
3. 结构化数据场景下，先使用 `$market-data` 取得统一无缓存行情快照，再进入 `chart-analysis-workflow.md`；不在本 Skill 内自行规定或覆写数据源优先级。
4. 只要使用结构化数据，必须保留 `data_channel / fetched_complete_bars / analysis_bars_count / timeframe_status`（如为外部原始输入则标明 `requested_bars / actual_bars / analysis_bars`），并如实披露 `data_quality_warning` 与 `cross_timeframe_warning`。
5. 若快照带有质量告警、复权异常或时段缺口，须按 `degraded_quality` 说明数据限制，不能把带告警周期描述为无异常完整数据。
6. 周期模板遵循 `$market-data` 默认配置或用户显式指定周期；若高周期成功但低周期失败，允许输出高周期主结论，但必须显式写明 `timeframe_status` 与降级原因。
7. 含有 `forming_bars` 时仅作盘中观察提醒，严禁用于确认突破、形态完成或背离锚点。
8. `indicator` 或 `complete` 模式必须先给 RSI/MACD 背离结论，再给数值辅助；`structure` 模式可省略整个指标段。
9. 背离状态严格区分 `无背离 / 候选 / 已确认 / 无法判断`：只有做过有效同类锚点比较才可写 `无背离`（锚点写 `N/A`），缺少锚点、预热不足或质量受限写 `无法判断`；纯数值关系先写 `候选`。
10. 单靠超买超卖、金叉死叉、零轴位置不得上调至高信心。
11. 有 `volume` 字段时必须输出“量能结论”（结合末根与近 5 根均量特征）；无 `volume` 时明确写“量能数据不可用”。
12. 数据优先：结构化数据 > 用户指定值 > 清晰截图 > 模糊截图。
13. 不要编造价位：刻度不可读或数据存在未校准复权跳空时改为条件描述。
14. Checklist 禁止只写编号（如 `3/4/5`），必须写项目中文名与原因；账户仓位交给 `$trade-risk`。
15. 免责声明：完整模式、交易决策卡以及涉及入场/止损/目标价位的精简更新**必须**附加免责声明；纯概念澄清或单点快问快答可不附加。
