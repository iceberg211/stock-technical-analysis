---
name: market-data
description: 无缓存、纯脚本化的多市场 OHLCV 行情获取、清洗与指标预计算基座（支持 A 股/ETF、港股、美股、加密货币）。自动完成中文/代码识别、多源直连并发取数、完整 K 线剥离，以及 EMA20/MA/VMA20/RSI14/MACD/Swing 极值预计算。供 $price-action-decision 与 $stock-technical-analysis 共同调用。
---

# 市场行情数据

## 目标

只负责取得可靠、可复用的行情事实。输出无状态统一行情快照与确定性预计算指标，不判断趋势、不计算交易信号、不选择战法。

## 职责边界

- 负责标的识别（中文名称/代码/市场）、多源主备并发路由、时区与复权口径校验、交易时段过滤、未完成 K 线（`forming_bars`）严格分离，以及确定性技术指标与微观特征预计算。
- 不做本地文件缓存、不维护盘中增量状态文件；每次调用均直接获取实时无状态快照。
- 不负责 Always In、BOS/CHoCH、形态、战法、仓位或交易建议。
- 预计算字段只提供客观数值事实与极值锚点（`ema20 / ma20 / ma50 / vma20 / rsi14 / macd / atr14 / swings`），不替上层分析 Skill 下方向结论。

## 唯一标准调用方式（脚本直出，禁止 AI 绕路手写取数）

获取结构化行情数据时，**一律直接运行 `scripts/market_data.py`**，**不得**让 AI 自己拼装 HTTP 请求、重写临时脚本或手算均线/MACD/RSI：

```bash
# 1. 标准多周期快照（默认：股票 1d,60m,15m；币圈 4h,1h,15m）
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "紫金矿业"

# 2. 按上层分析 Skill 聚焦输出（减少无用字段）
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "NVDA" --mode pa    # 专注 EMA20/ATR14/K线微结构
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "NVDA" --mode tech  # 专注 MA/VMA20/RSI14/MACD/Swing 锚点

# 3. 盘中/超短模式或指定自定义周期
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "159509" --style intraday --mode pa
python3 ~/.agents/skills/market-data/scripts/market_data.py snapshot --symbol "00700" --intervals "1w,1d,60m"

# 4. 仅查代码与市场归属
python3 ~/.agents/skills/market-data/scripts/market_data.py resolve --symbol "闪迪"
```

### 多标的执行约束

- 脚本内部对**单个标的多周期**并发抓取（典型耗时 0.3s～2s）。
- 一次分析多个标的时，外层仍需**逐标的顺序调用**并逐个压缩消化，禁止把多个标的的完整 JSON 同时堆积在同一轮上下文内；如某需求必须保存全部原始 K 线，才额外附加 `--include-bars`。

## 统一 K 线规则（计算窗口与交付窗口分离）

为兼顾**指标零预热误差**与**上层分析上下文预算**，脚本严格区分内部计算根数与输出交付根数：

| 周期 | 内部拉取计算根数 (`fetch_bars`) | 交付分析窗口 (`analysis_bars`) | 逐根明细条数 (`detail_bars`) | 完整状态最低门槛 (`min_bars`) |
|---|---:|---:|---:|---:|
| `1w` | 150 根 | 100 根 | 最近 12 根 | 60 根 |
| `1d` | 250 根 | 120 根 | 最近 12 根 | 80 根 |
| `4h` | 180 根 | 100 根 | 最近 12 根 | 60 根 |
| `60m` / `1h` | 180 根 | 80 根 | 最近 12 根 | 50 根 |
| `30m` | 180 根 | 96 根 | 最近 12 根 | 60 根 |
| `15m` | 200 根 | 96 根 | 最近 16 根 | 60 根 |
| `5m` | 240 根 | 120 根 | 最近 20 根 | 80 根 |

- 所有指标（EMA20/MA50/RSI14/MACD/ATR14）均先在完整 `fetch_bars` 上预热算完，再裁剪 `tail(analysis_bars)` 生成紧凑交接摘要。
- 盘中刷新无需缓存或局部重叠拼接，直接重新执行 `snapshot` 即可，每根 K 线按收盘规则或显式结束时间自动切入 `complete` 或 `forming_bars`。

## 分市场默认周期与数据源摘要

| 市场 | 默认周期（`swing`） | 日内模式（`intraday`） | 路由优先级 |
|---|---|---|---|
| **A 股 / ETF** (`cn`) | `1d, 60m, 15m` | `60m, 15m, 5m` | 日/周：腾讯 `fqkline(qfq)` → Yahoo 备；分钟：新浪 `CN_MarketDataService` → 腾讯 `mkline` → Yahoo |
| **美股** (`us`) | `1d, 60m, 15m` | `60m, 15m, 5m` | 日/周：腾讯 `fqkline` → Yahoo 备；分钟：新浪 `US_MinKService` → Yahoo 备 |
| **港股** (`hk`) | `1d, 60m, 15m` | `60m, 15m, 5m` | 代理可用时 Yahoo 优先（完整前复权及分钟线；若末尾缺当日收盘价自动用腾讯校验补齐）；日/周可回退腾讯 |
| **加密货币** (`crypto`) | `4h, 1h, 15m` | `1h, 15m, 5m` | Binance 公共 REST API（自动识别环境或系统代理） → Yahoo 备；实盘交易/私有持仓仍走 `$spot` |

## 参考文件

- 数据源路由与代理/复权细则：`references/source-routing.md`
- 统一无缓存快照契约：`references/data-contract.md`
- 确定性取数脚本：`scripts/market_data.py`、`scripts/indicators.py`
