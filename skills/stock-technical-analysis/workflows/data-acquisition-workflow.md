# 行情获取兼容入口

本文件只为旧调用路径保留，不再维护数据源、周期窗口和回退规则。

需要结构化行情时，直接调用 `$market-data` 脚本获取无缓存实时快照（推荐加上 `--mode tech` 以附带 MA/VMA20/RSI14/MACD 与 Swing 锚点表）：

```bash
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "<标的>" --mode tech
```

执行步骤：

1. 使用 `$market-data` 脚本获取统一无缓存快照（不得手写临时抓数脚本或自行心算指标）；
2. 确认至少一个目标周期 `timeframe_status` 为完整或可用，并核查 `data_quality_warning` 与 `cross_timeframe_warning`：
   - 若存在复权差异、缺失时段或数据告警，即使根数达标也应按 `degraded_quality` 在报告中显式披露限制，不能掩盖异常；
   - 若包含 `forming_bars`，仅作盘中观察提醒，严禁用于确认突破或信号；
3. 直接消费快照中的 `prior_segments`、`recent_detail_bars`、`indicators`（`ma20/ma50/ema20/vma20/rsi14/macd`）、`swings` 极值锚点表以及 `forming_bars` 质量提示，交给 `chart-analysis-workflow.md`。

禁止在本 workflow 复制长桥、Yahoo、AKShare、腾讯、新浪或本地缓存、周期聚合规则。股票与多市场行情唯一来源是 `$market-data` 的：

- `references/source-routing.md`
- `references/data-contract.md`
- `scripts/market_data.py`
- `scripts/indicators.py`
