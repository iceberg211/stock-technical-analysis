# 数据源路由与质量策略

## 标的解析规则 (`resolve_symbol`)

1. 标准前缀/后缀（`sh601899`、`601899.SS`、`00700.HK`、`hk00700`、`BTCUSDT`、`BTC-USDT`）直接无网识别。
2. 纯 6 位数字按交易所号段识别 A 股：`4/8/92` 开头为 `bj`，`5/6/9` 开头为 `sh`，`0/1/2/3` 开头为 `sz`；4～5 位数字补零识别港股 `hkxxxxx`。
3. 含中文字符或模糊英文简称时，直连腾讯 `smartbox.gtimg.cn`（~100ms）自动反查代码、名称和交易所后缀（如 `紫金矿业` → `sh601899`，`闪迪` → `usSNDK.OQ`）。

## 市场路由优先级与代理策略

| 市场 | 周期 | 主源（免/低延迟优先） | 备用源 | 代理规则 |
|---|---|---|---|---|
| **A 股 / ETF** (`cn`) | `1w, 1d` | 腾讯 `fqkline` (`qfqday`/`qfqweek` 前复权) | Yahoo Chart API | 腾讯直连不走代理 |
| **A 股 / ETF** (`cn`) | `60m, 30m, 15m, 5m` | 新浪 `CN_MarketDataService` | 腾讯 `mkline` → Yahoo | 国内源强制直连 |
| **美股** (`us`) | `1w, 1d` | 腾讯 `fqkline` | Yahoo Chart API | Yahoo 自动探测系统代理 |
| **美股** (`us`) | `60m, 30m, 15m, 5m` | 新浪 `US_MinKService` | Yahoo Chart API | 新浪直连；Yahoo 走系统代理 |
| **港股** (`hk`) | `全周期` | Yahoo Chart API（前复权 + 分钟线） | 日/周回退腾讯 `fqkline` | 自动读取环境变量及 macOS 系统代理（`urllib.getproxies()` + `curl`） |
| **加密货币** (`crypto`) | `全周期` | Binance 公共 REST `/api/v3/klines` | Yahoo Chart API | 自动使用探测到的代理；下单与私有接口交给 `$spot` |

> **可选长桥扩展**：`market_data.py` 已保留 `longbridge_status()` 探测钩子；当前环境无长桥凭据/SDK 时不强依赖、零阻塞。

## 时间戳与时段清洗铁律

1. **统一开始时间语义**：
   - 新浪 A 股/美股分钟线与腾讯 `mkline` 原生标签均为 **bar 结束时间**，解析时必须换算回 **bar 开始时间** 并保留精确 `_close_ts`。
   - 美股 60m 最后一根常规时段 `15:30~16:00` 在新浪标签为 `16:00:00`（半小时段），解析器专门校准其开盘时间为 `15:30`、收盘时间为 `16:00`，不按整 60 分钟倒退。
2. **周线（`1w`）与日线（`1d`）完整性**：
   - 日线按各交易所当地收盘时刻（A 股 `15:00`、港/美股 `16:00`）判断是否收盘；周线以所在自然周周五收盘时刻判断（若后方已有更晚一周 K 线则旧周必完整），未收盘均归入 `forming_bars`。
3. **分钟线交易时段过滤**：
   - 股票分钟线严格保留 `[开盘, 收盘)` 连续交易时段，剔除港股 `16:00` 收盘竞价扁平棒及收盘时点零量占位标记。

## 复权告警与质量降级码

- `intraday_unadjusted_mismatch_with_1d_qfq(...)`：A 股前复权 `1d` 与未复权分钟线在同一交易日收盘差异 > 1%（提示近期发生分红除权），上层禁止机械混用绝对价位。
- `stitched_latest_bar_from_tencent_fqkline`：港股 Yahoo `1d/1w` 收盘当日偶发末尾 `close=None` 被丢弃时，若前一日重叠收盘误差 `<= 0.5%`，自动用腾讯当日最新交易日补齐（因当日最新前复权因子等于 1.0）。
- `tencent_non_qfq_field_used`：腾讯接口未返回 `qfq` 字段（如部分 ETF/港美股）。
- `yahoo_missing_adjclose_unadjusted`：Yahoo 响应缺少 `adjclose`。
- `unavailable` / `degraded_recent_only`：所有源失败或完整根数少于 `min_bars`；保留真实错误链，不猜测或补造 K 线。
