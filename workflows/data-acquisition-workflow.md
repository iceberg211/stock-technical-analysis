# 数据获取工作流 (Data Acquisition Workflow)

> **当用户要求使用结构化行情数据分析，或只给出标的名称 / 代码而未提供图表时，必须先执行本工作流，再进入 `chart-analysis-workflow.md`。**

## 执行目标

1. 识别市场类型与标的格式。
2. 确定默认周期模板或用户指定周期。
3. 选择合适的数据源与回退链路。
4. 拉取、校验、裁剪 OHLCV 数据。
5. 产出固定分析窗口与数据元信息，交给分析 workflow。

---

## 总原则

1. **先取数，再分析**：没有结构化数据时，不要直接跳进结构判断。
2. **先分市场，再分周期**：A 股、美股、港股和币圈使用各自的周期模板；股票统一走 Yahoo Finance 优先链路。
3. **先固定窗口，再做分析**：一次性分析不读取缓存，分析输入必须固定；持续监控另行使用增量数据。
4. **获取与分析分离**：本 workflow 只负责“拿到什么数据、够不够用、如何降级”，不负责方向判断。
5. **优先降级，不要硬停**：只要还能支持有效分析，就继续，但必须标记降级原因。

多标的一次性分析的工具发现、并发、响应保留与压缩交接，统一使用 `batch-fast-path.md`；本文件继续定义数据源和数据有效性。

---

## Step D0: 输入识别

先判断用户给的是哪一种输入：

| 输入形态 | 行动 |
|---------|------|
| 证券简称 / 6 位代码 / `SH.600410` 这类代码 | 进入 A 股路由 |
| 美股代码 / 美股公司名，如 `SNDK` / `AAPL` / `NVDA` / “闪迪” | 进入美股路由 |
| 港股代码 / 公司名，如 `00700` / `700.HK` / “腾讯控股” | 进入港股路由 |
| `BTCUSDT` / `ETHUSDT` 这类交易对 | 进入币圈现货路由 |
| 用户只说“看一下某个标的”且没有图表 | 本 workflow 必须执行 |
| 用户已经提供完整 OHLC / parquet / API 返回 | 直接进入 Step D4 校验 |
| 用户只给截图且不要求主动拉数据 | 可跳过本 workflow，直接进入分析 workflow |

---

## Step D1: 市场识别与标的标准化

### 1. A 股 (`cn_equity`)

- 常见输入：`SH.600519`、`SZ.300033`、`BJ.430047`、6 位代码、证券简称。
- 标准化目标：统一成 `SH.600410`、`SZ.300033` 这种交易所前缀格式。
- 按数据源分别保存 `provider_symbol`：Yahoo 使用 `SH.600519 -> 600519.SS`、`SZ.300033 -> 300033.SZ`；长桥使用 `SH.600519 -> 600519.SH`、`SZ.300033 -> 300033.SZ`。
- 若用户给证券简称，先解析成唯一代码；若匹配到多个结果，先停止并让用户确认。

### 2. 美股 (`us_equity`)

- 常见输入：`SNDK`、`AAPL`、`NVDA`，或可唯一解析到美股代码的公司名 / 中文名。
- 标准化目标：内部保留 ticker，如 `AAPL`；Yahoo 参数使用 `AAPL`，长桥备用参数使用 `AAPL.US`。
- 数据通道：Yahoo Finance chart API 优先；只有 Yahoo 失败或不完整时才使用长桥。
- 周期标准化：`15min` / `15分钟` -> `15m`，`30min` / `30分钟` -> `30m`，`1小时` -> `60m`，`4小时` -> `4h`，`1day` / `日线` -> `1d`。
- 美股 `4h` 在数据源没有可验证的常规交易时段原生周期时，由常规交易时段 `60m` 本地聚合，并标记 `derived_from=60m`。

### 3. 港股 (`hk_equity`)

- 常见输入：`00700`、`HK.00700`、`700.HK`、证券简称。
- 标准化目标：内部统一成 `HK.00700`；Yahoo 参数使用 `700.HK`，长桥备用时再按其参数格式转换。
- 股票代码不足 5 位时在内部格式左侧补零。
- 数据通道：Yahoo Finance chart API 优先；只有 Yahoo 失败或不完整时才使用长桥。
- 周期标准化与美股一致。

### 4. 币圈现货 (`crypto_spot`)

- 常见输入：`BTCUSDT`、`ETHUSDT`。
- 标准化目标：统一成大写交易对。
- 数据通道：优先使用 `spot` skill 的 Binance Spot 公开行情端点；公开行情不需要 API key。
- 周期标准化：`30min` / `30分钟` -> `30m`，`1小时` -> `1h`，`4小时` -> `4h`，`1day` / `日线` -> `1d`。

---

## Step D2: 周期模板确定

先看用户是否明确指定周期；若未指定，再套默认模板。

| 市场 | 默认模板 | 精细模板 |
|------|---------|---------|
| `cn_equity` | `1D + 60m` | `1D + 60m + 15m` |
| `us_equity` | `1D + 60m` | `1D + 60m + 30m + 15m` |
| `hk_equity` | `1D + 60m` | `1D + 60m + 30m + 15m` |
| `crypto_spot` | `4H + 1H` | `4H + 1H + 15m` |

### 特殊规则

- A 股的 `4H` 不作为默认高周期。
- 若用户明确要求 A 股 `4H`，必须由 `60m` 在本地聚合得到，并在输出中写明 `derived_from=60m`。
- 美股的 `4H` 不作为默认原生周期；若用户明确要求美股 `4H`，必须由 `60m` 在本地聚合得到，并在输出中写明 `derived_from=60m`。
- 港股的 `4H` 不作为默认周期；用户明确要求时可使用长桥原生 `4H`，但必须记录 `data_channel` 与实际交易时段。
- 用户明确指定周期时，优先尊重用户指定；默认模板只在用户未指定时生效。

---

## Step D3: 数据源路由

### 1. 股票市场共同前置步骤：Yahoo Finance 优先

对 `cn_equity / us_equity / hk_equity` 必须先执行：

1. 先将代码标准化为 Yahoo `provider_symbol`，例如 `002460.SZ`、`603986.SS`、`AAPL`、`700.HK`。
2. 通过可用的直接 HTTP 请求能力访问 Yahoo chart API：`query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}?interval={interval}&range={range}&includePrePost=false&events=div,splits`；遇到429或5xx时只切换一次同源 `query2.finance.yahoo.com`。
3. 每个 `provider_symbol + interval` 只请求一次；禁止逐个运行 `node -e fetch`、`curl` 或临时脚本。
4. 从同一响应读取 `meta` 和 `indicators.quote[0]` 的 OHLCV；在内存中完成时间戳、价格有效性、去重、完整K线过滤和 `tail(analysis_bars)`。
5. 一次性分析不调用 `market_data.py`、不新建本地脚本、不写缓存；允许使用仓库维护的 `scripts/batch-analysis.js` 处理已经取得的响应，该处理器不联网、不写行情文件。持续监控、缓存恢复或明确要求派生周期时才进入相应取数工具。
6. Yahoo限流或临时服务故障只允许一次短重试；DNS/能力不可访问、鉴权或参数错误直接记录具体原因，转长桥。首次能力失败同批共享，不能表述为Yahoo服务整体故障。长桥工具按实际schema调用。
7. 有效证券代码不需要单独查询证券名称；ETF/股票类型从同一响应的 `meta.instrumentType` 读取。
8. 日线完整性在内存中按交易所收盘时间判断，不要在取数后按“时间戳+24小时”再次修正并重复请求。

#### Yahoo Finance 调用约定

- 股票技术分析默认使用同一复权口径；用户明确要求不复权时才改变。
- `includePrePost=false`，不把盘前、盘后和午休占位段混入常规 K 线。
- 默认按 `adjclose / close` 的同一根K线比例把 OHLC 统一到前复权口径；用户明确要求不复权时直接使用原始 quote OHLC。
- 请求范围只覆盖 `requested_bars` 加必要的指标预热，不使用无关的全量历史。
- `meta` 与 OHLCV 必须来自同一响应；字段冲突时标记 `data_quality_warning`。
- 不额外请求实时行情；Yahoo chart `meta` 已提供现价和前收盘核对字段。

#### 长桥备用约定

- 只有 Yahoo 不可用、限流、标的不支持、数据不足或周期不满足时才调用。
- 使用 `provider_symbol + period + count + adjust_type + trade_session`，并记录实际工具名、参数和失败原因。
- 插件未连接、鉴权失败、行情权限不足、标的不支持、限流、返回数据不足必须分开记录。

### 2. A 股路由

| 目标 | 优先顺序 |
|------|---------|
| `1D` | `Yahoo Finance chart API interval=1d -> 长桥备用` |
| 历史 `60m` / `30m` / `15m` / `5m` | `Yahoo Finance chart API 对应 interval -> 长桥备用` |
| 当天日内结构补充 | `Yahoo Finance chart API 对应 interval -> 长桥备用` |

### 3. 美股路由

| 目标 | 优先顺序 |
|------|---------|
| 标的解析 | `长桥证券搜索/基础信息 -> 用户明确 ticker -> 其他唯一映射` |
| `1D` | `Yahoo Finance chart API interval=1d -> 长桥备用` |
| `60m` / `30m` / `15m` | `Yahoo Finance chart API 对应 interval -> 长桥备用` |
| `4H` | `Yahoo 60m 本地内存聚合 -> 长桥 60m 备用聚合` |
| 现价核对 | `同一 Yahoo chart 响应中的 meta` |

### 4. 港股路由

| 目标 | 优先顺序 |
|------|---------|
| 标的解析 | `Yahoo provider_symbol -> 用户明确代码 -> 长桥备用` |
| `1D` | `Yahoo Finance chart API -> 长桥备用` |
| `60m` / `30m` / `15m` | `Yahoo Finance chart API -> 长桥备用` |
| `4H` | `Yahoo 60m 本地内存聚合 -> 长桥 60m 备用聚合` |
| 现价核对 | `同一 Yahoo chart 响应中的 meta` |

### 5. 币圈路由

| 目标 | 优先顺序 |
|------|---------|
| 交易对校验 | `spot` skill -> `/api/v3/exchangeInfo?symbol={SYMBOL}` -> 本地交易对映射 |
| K 线 OHLCV | `spot` skill -> `/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}` -> 本地 clean parquet |
| 现价与 24h 表现 | `spot` skill -> `/api/v3/ticker/24hr?symbol={SYMBOL}` -> 仅使用 K 线最新收盘价 |
| 服务器时间 | `spot` skill -> `/api/v3/time` -> 本地当前时间 |

#### Yahoo Finance chart API 调用约定

- 数据源标记写成 `source=yahoo_finance_chart_api`；用户明确指定 Yahoo 时不记录长桥失败原因。
- API 返回的 `timestamp + indicators.quote[0]` 必须转换为统一 OHLCV 字段：`timestamp/open/high/low/close/volume`。
- 默认使用常规交易时段数据；若包含盘前盘后数据，必须在输出中写明。
- `meta` 与 OHLCV 同响应读取；一次性分析不额外调用实时行情、不写缓存、不新建脚本。
- 同一批多个标的按 `provider_symbol + interval` 去重，并行请求但限制并发，不串行重复抓取。
- 由于部分新上市、拆分、分拆或复权标的可能出现价格尺度异常，必须检查 `regularMarketPrice`、`previousClose`、`chartPreviousClose`、`currency`、`exchangeName`。若这些字段明显冲突，输出中必须标记 `data_quality_warning`，并提示用户用 TradingView 或券商行情复核绝对价位。
- 美股 `4H` 必须标记 `derived_from=60m`，不能当作原生周期。

#### 币圈 `spot` skill 调用约定

- 加密现货分析必须先尝试加载并使用 `spot` skill；数据源标记写成 `source=binance_spot_skill:/api/v3/klines`。
- `/api/v3/klines` 返回数组时，必须转换为统一 OHLCV 字段：`timestamp/open/high/low/close/volume/close_time`。
- 以 Binance `serverTime` 判断 K 线是否完成：只保留 `close_time <= serverTime` 的 K 线，避免把正在形成的当前 K 线送入分析。
- 固定处理器支持币圈现货日线、4h、1h、30m、15m；使用 `binanceRequest(task,serverTime)` 截止上一根完整K线取固定窗口，避免过滤forming后少一根又重新补拉。原始数组、插件 `result` 包装与标准OHLCV均可处理，标准字段必须保留 `close_time`。
- 单次 `limit` 最大按 Binance 公开接口约束使用 `1000`；若 `requested_bars` 超过单次返回能力，分页补足。
- 同一批分析多个币种时，所有交易对必须使用同一次数据请求时间和同一套周期模板，方便横向强弱排序。
- 若 `spot` skill 不可用、网络失败或 Binance 返回限流错误，进入本地 clean parquet 回退，并写明 `source=cache` 与 `degrade_reason`。

### 回退说明

- Yahoo 失败时才尝试长桥；实际命中的通道必须写入 `source` 与 `data_channel`。
- A 股 `1D` 成功、分钟数据失败时，允许先保留日线分析资格。
- 美股 `1D` 成功、分钟数据失败时，允许先保留日线分析资格。
- 港股 `1D` 成功、分钟数据失败时，允许先保留日线分析资格。
- 币圈任一周期低于最低门槛时，优先用 `spot` skill 分页补足；仍不足时才标记降级。

---

## Step D4: 固定窗口规则

### 标准分析窗口

| 市场 | 周期 | requested_bars | min_bars | analysis_bars |
|------|------|----------------|----------|---------------|
| A 股 | `1D` | 300 | 200 | 300 |
| A 股 | `60m` | 160 | 80 | 120 |
| A 股 | `30m` | 240 | 120 | 180 |
| A 股 | `15m` | 240 | 120 | 180 |
| A 股 | `5m` | 240 | 120 | 200 |
| 美股 | `1D` | 300 | 200 | 300 |
| 美股 | `60m` | 300 | 160 | 240 |
| 美股 | `30m` | 500 | 240 | 500 |
| 美股 | `15m` | 600 | 300 | 500 |
| 美股 | `4H` | 300 | 160 | 300 |
| 港股 | `1D` | 300 | 200 | 300 |
| 港股 | `60m` | 300 | 160 | 240 |
| 港股 | `30m` | 500 | 240 | 500 |
| 港股 | `15m` | 600 | 300 | 500 |
| 港股 | `4H` | 300 | 160 | 300 |
| 币圈 | `1D` | 300 | 200 | 300 |
| 币圈 | `4H` | 300 | 200 | 300 |
| 币圈 | `1H` | 500 | 300 | 500 |
| 币圈 | `30m` | 500 | 300 | 500 |
| 币圈 | `15m` | 500 | 300 | 500 |

### 固定窗口约束

- `requested_bars` 是向数据源请求的目标根数。
- `analysis_bars` 是实际交给分析 workflow 的固定窗口。
- 去重、交易时段校验和完整 K 线过滤先于窗口裁剪；指标在已校验的历史序列上预热，然后截取分析窗口，避免过滤后重复计算。
- 即使持续监控保留更多历史，分析层也只截取最后 `analysis_bars` 根。
- A 股 `60m` 的 `analysis_bars=120` 是正常配置，不视为降级。

---

## Step D5: 数据校验

每个周期都必须检查以下内容：

| 校验项 | 规则 |
|--------|------|
| 必需字段 | `timestamp/open/high/low/close` 必须存在 |
| 推荐字段 | `volume` 优先保留；缺失时允许继续，但要标记 |
| 时间戳 | 必须可排序；最终统一成 UTC |
| 价格有效性 | 价格不能为 0；每根必须满足 `low <= open/close <= high` |
| 标的一致性 | 长桥响应中的 symbol 必须与 `provider_symbol` 一致 |
| 去重与排序 | 按 timestamp 去重并升序排列 |
| 现价交叉核对 | 最新完整 K 线收盘价与同源实时行情出现明显冲突时标记 `data_quality_warning` |
| 复权与时段 | 必须记录 `adjust_type` 与 `trade_session`，不同设置的数据不得直接拼接 |
| 完成状态 | 先确认供应商时间戳代表开盘还是收盘；开盘时间戳的分钟 K 线用 `bar_open_time + interval <= source_time` 判断；日线按交易日历与市场收盘时间判断 |
| 收盘附加记录 | 零成交量的收盘占位记录与真实收盘集合竞价分开处理；不把所有 `15:00` 记录直接删除。时间语义无法确认时保留为 `closing_reference` 并标记质量警告 |
| 不规则时间戳 | 不因时间不整齐就判定OHLC错误；归属未确认的真实成交保留为参考，禁止自动取整或合并。先完成分类再计算指标 |
| 覆盖连续性 | 根数足够不代表连续；按已确认交易日历检查覆盖范围内缺失时段，不把午休、休市或请求窗口首尾截断判为缺口 |
| 根数 | `actual_bars` 必须可统计 |

### 分析输入生成

- 普通单标的与批量分析均可使用固定处理器；支持A股日线与分钟线、美股日线与15m/30m/60m。美股使用纽约时区及收盘截短规则；不套A股午休网格。
- 交易日历校验只请求一次，范围按已知接口限制选择；参数范围失败后标记 `calendar_unverified`，停止猜测分块重试。无日历不能把根数充足等同于历史连续性已确认。

- 使用固定窗口切片：`tail(analysis_bars)`。
- 对每个周期单独记录覆盖范围：`coverage_start / coverage_end`。
- 生成后再交给 `chart-analysis-workflow.md`。
- `actual_bars` 记录返回根数，另记录 `valid_complete_bars` 和剔除原因；`analysis_bars` 记录最终实际使用根数，不能用区间范围代替逐标的统计。

---

## Step D6: 降级与回退

`source_fallback_reason` 记录为什么没有使用首选数据源；`degrade_reason` 只记录最终分析数据为什么不完整。后备通道返回完整数据时，允许 `source_fallback_reason` 非空，同时保持 `timeframe_status=complete`、`degrade_reason=null`。

分开保存 `history_status`（样本数量）、`data_quality`（质量）和 `timeframe_status`（综合状态）。时间戳语义、交易日历或复权无法确认，存在冲突记录或时段缺口时，不能仅因根数足够标记 `complete`；使用 `degraded_quality`。固定处理器对不支持的市场、周期明确返回错误，改走该市场完整工作流，不套用A股时段。

| 失败场景 | 处理 |
|---------|------|
| Yahoo Finance 不可用 | DNS/能力不可访问直接转长桥；临时故障短重试一次，标记 `source_fallback_reason=yahoo_unavailable` |
| Yahoo Finance 限流 | 降低并发并短重试一次；仍失败才调用长桥，标记 `source_fallback_reason=yahoo_rate_limited` |
| Yahoo 不支持标的 | 核对 `provider_symbol` 后调用长桥，标记 `source_fallback_reason=yahoo_symbol_not_supported` |
| Yahoo 返回根数不足 | 不扩展到其他周期；先标记 `source_fallback_reason=yahoo_insufficient_bars`，再调用长桥补足 |
| Yahoo 返回未完成或字段缺失 | 过滤后仍不足时调用长桥，标记 `source_fallback_reason=yahoo_incomplete_data` |
| 长桥插件未暴露或未连接 | 进入市场后备通道，标记 `source_fallback_reason=longbridge_plugin_unavailable` |
| 长桥要求登录或授权失效 | 进入市场后备通道，标记 `source_fallback_reason=longbridge_auth_required` |
| 长桥行情权限不足 | 进入市场后备通道，标记 `source_fallback_reason=longbridge_quote_permission_denied` |
| 长桥不支持标的或无行情 | 核对 `provider_symbol` 后进入市场后备通道，标记 `source_fallback_reason=longbridge_symbol_not_supported` |
| 长桥触发限流 | 降低并发并重试一次；仍失败则回退，标记 `source_fallback_reason=longbridge_rate_limited` |
| 长桥返回根数不足 | 尝试历史 K 线补足；仍不足则回退，标记 `source_fallback_reason=longbridge_insufficient_bars` |
| 后备在线通道失败但本地缓存可用 | 使用缓存，并标记 `source=cache` |
| 返回数据不足 50 根 | 停止完整分析，请求用户补图或更换数据源 |
| `actual_bars < min_bars` 且大于等于 50 | 允许继续，但标记“数据不足，信心降级” |
| A 股 `1D` 成功、分钟数据失败 | 继续做日线主分析，不额外调用其他股票行情源 |
| A 股 `60m` 成功但不足 `min_bars` | 允许继续，但标记 `60m=degraded_recent_only` |
| 美股 Yahoo Finance chart API 数据字段冲突 | 继续分析同源 OHLC 结构，但标记 `data_quality_warning`，具体价位要求用户复核 |
| 美股 `1D` 成功、分钟数据失败 | 继续做日线主分析，并标记分钟周期缺失 |
| 美股请求 `4H` 但 `60m` 不足 | 不输出伪 `4H`，改回 `1D + 60m` 或直接降级 |
| 港股 `1D` 成功、分钟数据失败 | 继续做日线主分析，并标记分钟周期缺失 |
| 缺少 `volume` | 跳过量能分析，并写明“量能数据不可用” |
| A 股请求 `4H` 但 `60m` 不足 | 不输出伪 `4H`，改回 `1D + 60m` 或直接降级 |
| 币圈 `spot` skill 不可用 | 使用本地 clean parquet，并标记 `degrade_reason=spot_skill_unavailable` |
| Binance 返回未完成当前 K 线 | 剔除未完成 K 线，并在 `coverage_end` 使用最后一根完整 K 线时间 |
| Binance 限流或临时错误 | 降低请求频率或分批重试；仍失败则使用缓存并标记 `degrade_reason=binance_rate_limited_or_error` |

---

## Step D7: 输出给分析层的元信息

只要使用了结构化数据，就必须产出以下字段，并传给分析 workflow：

- `market`
- `symbol`
- `provider_symbol`
- `source`
- `data_channel`
- `adjust_type`
- `trade_session`
- `requested_bars`
- `actual_bars`
- `analysis_bars`
- `derived_from`
- `is_complete`
- `source_fallback_reason`
- `degrade_reason`
- `timeframe_status`
- `coverage_start`
- `coverage_end`
- `excluded_incomplete_bar`
- `data_quality_warning`

### `timeframe_status` 建议值

- `complete`
- `degraded_quality`
- `degraded_recent_only`
- `missing`
- `derived_from_60m`

---

## 本工作流的完成条件

满足以下条件后，才允许进入 `chart-analysis-workflow.md`：

1. 市场类型与标的已标准化。
2. 至少一个可分析周期已经就绪。
3. 每个周期的 `actual_bars`、`analysis_bars`、`timeframe_status` 已明确。
4. 已确认本次分析是“完整”还是“降级”。
