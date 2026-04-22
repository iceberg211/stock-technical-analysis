# 每日持仓复盘

> 编排层：读取持仓清单，并行派发分析任务，汇总结果。
> 分析逻辑由 `chart-analysis-workflow.md` 执行，本文件只负责编排。

## 持仓清单

```yaml
crypto:
  - { symbol: BTCUSDT, interval: [4h, 1h] }
  - { symbol: ETHUSDT, interval: [4h, 1h] }
  - { symbol: SOLUSDT, interval: [4h, 1h] }
  - { symbol: BNBUSDT, interval: [4h, 1h] }

a_stock:
  - { symbol: SZ.300033, name: 同花顺, interval: [1d, 60m] }
  - { symbol: SH.601899, name: 紫金矿业, interval: [1d, 60m] }
```

## 并行执行规则

**在单条消息中，为持仓清单中的每个标的同时派发一个独立的分析子任务。**

具体要求：
1. 读取上方持仓清单
2. 为每个标的构造一个子任务（prompt 见下方模板）
3. **所有子任务必须在同一条消息中一次性派发**，不要等前一个完成再派下一个
4. 每个子任务独立运行，互不依赖
5. 等待所有子任务返回后，汇总输出

### 子任务 Prompt 模板

每个子任务使用以下 prompt（替换变量）：

```
你是技术分析助手。请分析 {symbol}。

数据目录：~/.trading-data/
分析周期：{intervals}
市场类型：{crypto / a_stock}

请按 stock-technical-analysis Skill 的 chart-analysis-workflow.md 执行完整 Step 0-8 分析。
分析完成后：
1. 将 snapshot.json + report.md 写入 ~/.trading-data/signals/{symbol}/
2. 返回一行摘要：{symbol} | {方向} | {信心} | {策略} | 一句话理由
```

### 工具适配

| 工具 | 并行方式 |
|------|---------|
| Claude Code | 在同一条消息中调用多个 Agent 工具，每个 Agent 分析一个标的 |
| Codex | 提交多个并行 task，每个 task 一个标的 |
| 不支持并行的工具 | 退化为串行，逐个执行 |

## 汇总阶段（所有子任务完成后）

### 1. 输出汇总表

```markdown
## 每日持仓复盘 {YYYY-MM-DD}

### 今日分析

| 标的 | 方向 | 信心 | 策略 | 关键理由 |
|------|------|------|------|---------|
| BTCUSDT | 🔴 做空 | 高 | trend-pullback | ... |
| ETHUSDT | ⚪ 观望 | 低 | none | ... |
| ... | | | | |

### 需要关注

- {列出方向变化、新信号、风险事件}
```

### 2. 验证历史信号（可选）

如果 stock-skill-backtest 可用，运行一次信号回测：

```bash
cd ~/Documents/GitHub/stock-skill-backtest
python3 -m src --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT SZ.300033 SH.601899 --interval 1h
```

追加输出：

```markdown
### 历史信号验证

| 标的 | 信号时间 | 方向 | 结果 | R值 |
|------|---------|------|------|-----|
| ... | | | | |
```
