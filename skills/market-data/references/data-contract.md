# 统一无缓存行情快照契约

## 顶层快照结构

```json
{
  "query": "紫金矿业",
  "name": "紫金矿业",
  "market": "cn",
  "canonical_symbol": "sh601899",
  "exchange_timezone": "Asia/Shanghai",
  "intervals_requested": ["1d", "60m", "15m"],
  "mode": "full",
  "cache_enabled": false,
  "timeframe_status": {"1d": "complete", "60m": "complete", "15m": "complete"},
  "cross_timeframe_warning": null,
  "elapsed_ms": 412,
  "timeframes": { "...": "..." }
}
```

## 单周期交付包 (`timeframes[interval]`)

每个可用周期均包含：

- **元信息与状态**：`interval`, `timeframe_status` (`complete` / `degraded_recent_only` / `unavailable`), `source`, `data_channel`, `provider_symbol`, `adjust_type`, `trade_session`, `source_time`, `fetched_complete_bars`, `analysis_bars_count`, `coverage_start`, `coverage_end`, `source_fallback_reason`, `data_quality_warning`, `elapsed_ms`。
- **`last_complete_bar`**：最后一根已收盘完整 K 线（`local_time`, `timestamp`, `open`, `high`, `low`, `close`, `volume`）。
- **`window_range`**：交付窗口（`analysis_bars` 范围）内极值及当前位置分位 `high`, `low`, `last_pos_pct`。
- **`indicators`**：在完整 `fetch_bars` 上预热计算后的末端指标事实：
  - `pa` / `full`：`ema20`, `ema20_slope_5bar`, `close_vs_ema20_streak`, `atr14`。
  - `tech` / `full`：额外增加 `ma20`, `ma50`, `vma20`, `vol_ratio_vma20`, `vol_grade`, `rsi14`, `macd` (`dif`, `dea`, `hist`, `formula="hist=dif-dea"`)。
- **`prior_segments`**：窗口前序（`detail_bars` 以前）K 线按时间分段压缩的节奏摘要（起止时间、K 线数、开高低收、阳/阴根数、净涨跌幅）。
- **`recent_detail_bars`**：最近 `detail_bars`（12～20 根）完整微结构明细，每根含 `local_time`, `o/h/l/c/v`, `dir`, `doji`, `body_pct`, `u_wick`, `l_wick`, `close_pos`, `pattern` (`IB`/`OB`), `gap`, `ema20`, `vol_ratio`。
- **`swings`**（`tech` / `full` 模式）：分形提取的主要 `swing_highs`、`swing_lows` 及 `window_high` / `window_low` 锚点（含 `local_time`, `price`, `rsi14`, `macd_dif`, `macd_hist`）。
- **`forming_bars`**：当前正在走、尚未收盘的 K 线列表；仅作观察提醒，严禁混入完整 K 线序列。
- **`bars`**（仅传 `--include-bars` 时附加）：完整裁剪后的 `analysis_bars` 原数组。

## 核心不变式

- 无本地缓存状态：每次执行均直接获取最新快照，无 `update_stats` 或增量缺口拼接风险。
- 分析输入只认已收盘完整 K 线；`forming_bars` 严格分离。
- 每根 K 线必满足 `open/high/low/close > 0` 且 `low <= open,close <= high`，按时间戳升序无重复。
