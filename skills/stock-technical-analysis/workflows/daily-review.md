# 每日持仓复盘工作流

> **编排型工作流**：本文件按顺序协调多个独立 Skill 能力完成多标的巡检。AI 读到本文件时应：
> 1. 识别每个 Phase 的能力归属（见下方归属表）
> 2. 在对应 Phase 调用正确 Skill，不把取数或回测命令硬编码到本 Skill 中
> 3. Phase 结束后返回本文件推进下一阶段

## Phase 能力归属表

| Phase | 核心任务 | 能力归属 |
|-------|---------|---------|
| Phase 1 | 拉取并预计算各标的统一无缓存快照 | `$market-data` |
| Phase 2 | 逐标的执行多周期技术分析与 Playbook 评估 | `$stock-technical-analysis` |
| Phase 3 | 历史信号回测验证（可选，需用户明确要求） | 外部回测工具 / `stock-skill-backtest`（若环境已配置） |
| Phase 4 | 汇总总览表、风险提示与个股细节 | `$stock-technical-analysis` |

---

## 持仓清单（示例，按用户实际清单调整）

```yaml
crypto:
  - symbol: BTCUSDT
    interval: [4h, 1h]
  - symbol: ETHUSDT
    interval: [4h, 1h]
  - symbol: SOLUSDT
    interval: [4h, 1h]
  - symbol: BNBUSDT
    interval: [4h, 1h]

a_stock:
  - symbol: SZ.300033    # 同花顺
    interval: [1d, 60m]
  - symbol: SH.601899    # 紫金矿业
    interval: [1d, 60m]
  - symbol: SH.600410    # 华胜天成
    interval: [1d, 60m]
```

---

## 执行流程

### Phase 1：获取行情快照

> 能力归属：`$market-data`

- 严格遵守 `$market-data` 的**无缓存脚本直出 + 逐标的压缩消化**约束，不运行已废弃的本地 ingest pipeline，也不手写临时 HTTP 抓数脚本。
- 对每个标的直接调用：

```bash
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "<标的>" --mode tech
```

- 如有多个标的，按 `$market-data` 要求逐标的调用并压缩交接（单标的内部各周期已由脚本并发拉取），避免把多个标的的完整原始 JSON 堆在同一轮上下文中。

### Phase 2：逐标的分析（核心）

> 能力归属：`$stock-technical-analysis`

对每个标的依次或按独立子任务执行：
1. 读取 Phase 1 产出的 `$market-data` 紧凑快照，检查 `timeframe_status`、`data_quality_warning` 与 `cross_timeframe_warning`；
2. 按 `workflows/chart-analysis-workflow.md` 执行 Step 0~7（使用归一化信号强度评分与四态背离协议）；
3. 若满足中/强信号且结构允许，按 `workflows/trading-decision.md` 匹配 Playbook + 入场前检查；需要账户仓位时转交 `$trade-risk`；
4. 仅在用户明确要求持久化或运行环境已启用持久化配置时，才归档信号到 `~/.trading-data/signals/{SYMBOL}/`；
5. 返回一行摘要：`{SYMBOL} | {方向} | {偏向} | {信心} | {策略} | 关键理由`。

> 若运行平台支持子代理并行（如独立子任务），可为每个标的分配一个子任务，每个子任务内独立调用 `$market-data` 与本 Skill 完成分析并只返回紧凑摘要。

#### 子任务 Prompt 模板

```text
请使用 $market-data 和 $stock-technical-analysis 分析 {SYMBOL}（周期：{INTERVALS}）。

执行步骤：
1. 调用 $market-data 的 snapshot 脚本（--mode tech）获取最新无缓存行情快照；
2. 按 workflows/chart-analysis-workflow.md 完成分析（含数据质量与四态背离核查）；
3. 若满足方案门槛，按 workflows/trading-decision.md 输出条件式方案（不自行编造账户仓位）；
4. 仅在明确要求归档时写入 ~/.trading-data/signals/{SYMBOL}/；
5. 返回紧凑摘要：{SYMBOL} | {方向} | {偏向} | {信心} | {策略} | 关键理由
```

### Phase 3：历史信号验证（可选）

> 能力归属：外部回测工具 / `stock-skill-backtest`（若用户要求且本地已安装）

- 本 Skill **不内置且不直接执行**历史回测命令。
- 仅当用户明确要求验证历史信号表现时，切换到对应的回测 Skill 或工具执行验证，再将结果带回 Phase 4 汇总；未要求或环境无回测工具时直接跳过本阶段并注明“未执行历史回测”。

### Phase 4：输出汇总

> 能力归属：`$stock-technical-analysis`

```markdown
## 每日持仓复盘 {YYYY-MM-DD}

### 0. 执行摘要

- 市场整体状态：{一句话说明多空/震荡/风险偏好}
- 今日可执行信号：{有/无；如有列出标的}
- 今日主要风险：{列出 2-3 条最重要风险}
- 数据质量：{完整/存在 degraded_quality 或 degraded_recent_only；说明具体标的与告警原因}

### 1. 总览表

| 标的    | 方向  | 偏向    | 信心 | 策略           | 关键理由 |
| ------- | ----- | ------- | ---- | -------------- | -------- |
| BTCUSDT | short | bearish | high | trend-pullback | ...      |
| ETHUSDT | watch | neutral | low  | none           | ...      |

### 2. 历史信号验证（如执行 Phase 3）

| 标的 | 信号时间 | 方向 | 结果 | R值 |
| ---- | -------- | ---- | ---- | --- |
| ...  |          |      |      |     |

### 3. 需要关注

- {列出需要特别注意的结构变化、关键位临界或数据质量告警}

### 4. 个股细节

#### {SYMBOL} {名称}

**结论卡**
- 方向：{做多/做空/观望}
- 偏向：{bullish/bearish/range_trade/watch}
- 信心：{high/medium/low}
- Playbook：{策略名/none}
- 当前价：{last_complete_bar.close}（周期与收盘时间：{interval / local_time}）

**多周期结构**
- HTF {周期}：结构={uptrend/downtrend/range/transition}，趋势健康度={healthy/exhaustion/possible_reversal}
- LTF {周期}：结构={uptrend/downtrend/range/transition}，趋势健康度={healthy/exhaustion/possible_reversal}
- 多周期一致性：{aligned/conflicting/neutral}

**关键价位**
- 支撑：{最多 3 个}
- 阻力：{最多 3 个}
- 当前位置：{支撑附近/阻力附近/中间位置}

**行为与指标**
- 近期动量：{多头主导/空头主导/犹豫不决/动量衰竭}
- 量价关系：{放量确认/缩量整理/背离/量能数据不可用}
- RSI 背离：{无背离 / 候选 / 已确认 / 无法判断（有关系时附类型与锚点）}
- MACD 背离：{无背离 / 候选 / 已确认 / 无法判断（有关系时附类型与锚点）}
- 形态与强度：{K线/图表形态 或 无；hits/applicable_items = score_ratio}

**执行计划**
- 候选条件：{条件式触发}
- 失效条件：{结构失效或数据降级触发的放弃条件}
- 当前动作：{观望/等待回踩/等待跌破/等待突破回踩}

**数据状态**
- 数据通道与窗口：{source / data_channel；fetched_complete_bars / analysis_bars_count}
- timeframe_status：{按周期列出，含 degraded_quality / degraded_recent_only}
- 告警与回退原因：{无 / data_quality_warning / cross_timeframe_warning / source_fallback_reason}
```

> 末尾按规则附加非投资建议免责声明。

---

## 持仓变更

增减标的只需修改上方清单；市场识别、默认周期模板、复权与主备路由统一由 `$market-data` 负责，不在本文件重复维护数据源列表。
