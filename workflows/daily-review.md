# 每日持仓复盘工作流

> 对持仓标的**并行**执行技术分析，汇总后验证历史信号。

## 持仓清单

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
```

## 执行流程

### Phase 1：拉取行情（并行）

同时为所有标的拉取最新行情，不等待前一个完成：

```bash
# 所有命令并行执行
cd ~/Documents/GitHub/stock-skill-backtest
python3 -m src.pipeline.ingest --source binance --symbol BTCUSDT --interval 1h --limit 500 &
python3 -m src.pipeline.ingest --source binance --symbol ETHUSDT --interval 1h --limit 500 &
python3 -m src.pipeline.ingest --source binance --symbol SOLUSDT --interval 1h --limit 500 &
python3 -m src.pipeline.ingest --source binance --symbol BNBUSDT --interval 1h --limit 500 &
# A 股用可用数据源，不可用则跳过
wait
```

### Phase 2：并行分析（核心）

**为每个标的派发一个独立的分析子任务，所有标的同时分析。**

每个子任务执行：
1. 加载 `stock-technical-analysis` Skill
2. 按 `workflows/data-acquisition-workflow.md` 获取数据
3. 按 `workflows/chart-analysis-workflow.md` 执行 Step 0~7
4. 若产出交易方案，按 `workflows/trading-decision.md` 匹配 Playbook + Checklist
5. 归档信号到 `~/.trading-data/signals/{SYMBOL}/`
6. 返回一句话结论

**在 Claude Code 中**：用 Agent 工具同时派发多个子代理，每个子代理分析一个标的。所有子代理在同一条消息中发出，自动并行执行。

**在 Codex 中**：用并行 task 机制，每个标的一个 task。

**在其他工具中**：如果不支持并行，则按顺序逐一执行。

#### 子任务 Prompt 模板

每个并行子任务使用以下 prompt（替换 `{SYMBOL}` 和 `{INTERVALS}`）：

```
你是一个技术分析助手。请分析 {SYMBOL}。

数据目录：~/.trading-data/
分析周期：{INTERVALS}

执行步骤：
1. 从 ~/.trading-data/clean/{SYMBOL}/ 读取 OHLCV 数据
2. 按 stock-technical-analysis Skill 的 chart-analysis-workflow 执行完整分析
3. 将 snapshot.json + report.md 写入 ~/.trading-data/signals/{SYMBOL}/
4. 返回一行摘要：{SYMBOL} | {方向} | {偏向} | {信心} | {策略} | 关键理由
```

### Phase 3：验证历史信号（等 Phase 2 全部完成后）

```bash
cd ~/Documents/GitHub/stock-skill-backtest
python3 -m src --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT SZ.300033 SH.601899 --interval 1h
```

### Phase 4：输出汇总

```markdown
## 每日持仓复盘 {YYYY-MM-DD}

### 今日分析

| 标的 | 方向 | 偏向 | 信心 | 策略 | 关键理由 |
|------|------|------|------|------|---------|
| BTCUSDT | short | bearish | high | trend-pullback | ... |
| ETHUSDT | watch | neutral | low | none | ... |
| ... | | | | | |

### 历史信号验证

| 标的 | 信号时间 | 方向 | 结果 | R值 |
|------|---------|------|------|-----|
| ... | | | | |

### 需要关注

- {列出需要特别注意的变化}
```

## 使用方式

| 工具 | 用法 |
|------|------|
| Claude Code | 在 stock-technical-analysis 项目中说"每日复盘"，自动触发并行 Agent |
| Codex | 作为 task prompt 提交，Codex 自行调度并行 |
| 定时 | 配合 `/schedule` 或 cron 定时触发 |
| 手动 | 直接粘贴本文件内容作为 prompt |

## 持仓变更

增减标的只需修改上方 yaml 清单。市场类型决定默认周期和数据源：
- `crypto`: 默认 `4h + 1h`，数据源 Binance
- `a_stock`: 默认 `1d + 60m`，数据源 opend/mcp
