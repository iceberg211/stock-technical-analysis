# 单标的与多标的一次性分析

普通结构化行情问答读仓库 `SKILL.md` 和本文件即可，单标的也走此入口。只有下面的明确分支才加载其他文件的相关段落，不逐标的重复读取规则。

## 范围与分支

- 固定处理器 `scripts/batch-analysis.js` 支持A股 `1d / 5m / 15m / 30m / 60m`、美股 `1d / 15m / 30m / 60m` 和币圈现货 `1d / 4h / 60m / 30m / 15m`，统一 `1h=60m`、`30min=30m`、`5min=5m`、`day=1d`。股票未指定周期默认 `1d + 60m`，币圈默认 `4h + 1h`。
- A股窗口由 `CN_WINDOWS` 提供，美股由 `US_WINDOWS` 提供；按配置的 requested/minimum/analysis 根数取数。美股1d为300/200/300，60m为300/160/240，30m为500/240/500，15m为600/300/500。
- 币圈窗口由 `CRYPTO_WINDOWS` 提供；4h为300/200/300，1h为500/300/500，日线300/200/300，30m与15m均500/300/500。
- 港股、期货或派生周期：读取 `data-acquisition-workflow.md` 的对应市场与窗口段落，再使用图表分析规则。
- 复杂结构或形态争议：只读 `chart-analysis-workflow.md` 或单个 reference 的相关段落。
- 中/强信号且方向、数据与事件约束允许交易方案：读取 `trading-decision.md`，完成检查并按入口归档；历史信号验证进入 `daily-review.md`。

## 取数

1. 股票优先通过直接HTTP能力访问Yahoo chart API，同一响应取得 `meta + OHLCV`，只请求用户指定周期，成功响应立即保留。
2. 当前请求能力不可访问端点时（如DNS失败），同批共享该能力结果，记 `source_fallback_reason=yahoo_unavailable` 和具体原因，转长桥。不要继续浏览器探测，不能表述成Yahoo服务整体故障。
3. 429/5xx只重试失败项一次，query2切换计入这一次；代码错误、鉴权失败、解析失败不盲重试。股票唯一备用源是长桥。
4. 精确发现长桥K线工具，只加载选中schema；简称有歧义才核对代码。保持同一复权与常规交易时段口径。
5. 使用处理器 `fetchBatch(tasks, fetcher, options)` 建立去重队列，并发最多6；两个周期同时派发。`fetcher` 调用真实工具，不现场编写第二套队列。`runAnalysis` 可在一次工具执行中完成队列、处理和摘要。
6. `onResponse` 立即将每个实际响应（含失败）保存到会话内存；需要重试时由 `retryable` 明确识别限流/临时故障。解析问题重用已保存响应。长桥需要报价核对时批量一次。

币圈先加载 `spot` skill，使用Binance现货公开 `/api/v3/time` 与 `/api/v3/klines`，不以合约K线替代。同批服务器时钟只获取一次，以 `api.binanceRequest(task,serverTime)` 生成请求；固定UTC、endTime截止上一根已完成K线，从而取得完整固定窗口，避免常规请求包含forming bar导致少一根后再次补拉。先取得时钟再并发各周期；服务器时钟失败明确记录，本地缓存回退读数据获取流程的对应分支。

## 辅助校验与停止条件

- 同一市场的日历只请求一次；先按工具schema声明的最大范围选参数。没有明确最大范围时，完整历史连续性标记未核验。参数限制、鉴权或解析失败后停止，不能猜测多个分块长度试错。
- 用 `trace.auxiliaryOnce("calendar:US", fetcher)` 保存成功或失败结果；同一市场共用该key，不把日期范围放进key绕过限制。报价核对用 `quote:供应商:市场`，同一批最多一次。失败保留 `degraded_quality` 与具体限制。
- 日历已有且覆盖窗口时复用；缺失日历只基于已返回交易日检查候选缺口，不能证明历史完整。美股半日市信息未确认时记录 `session_calendar_unverified`。
- 有有效ticker的普通K线分析直接使用同源代码信息。身份歧义、事件风险会改变判断或用户要求事件研究时，才补官方信息；同类辅助查询失败后披露限制。必须执行的外部核验合并一次，不扩展为基本面研究。
- 原始响应可解析且关键位没有字段冲突时，完成一次固定计算后开始报告。已知质量限制不触发重新取数、重读规则或即席重写指标算法。

## 固定处理

处理器无外部依赖，不联网、不写行情文件。可从Node CLI标准输入接收JSON，也可在 `functions.exec` 内使用：

```javascript
// 源码只在工具运行环境加载，不把完整代码打印到模型上下文。
const src = await tools.exec_command({cmd: "cat scripts/batch-analysis.js", max_output_tokens: 18000});
if (src.exit_code !== 0 || src.original_token_count > 18000) throw Error("处理器加载不完整");
const api = new Function(src.output + "\nreturn BatchAnalysis;")();
store("batch-api-source", src.output); // 后续读取会话内存；源码更新才重新加载。
const result = api.analyzeBatch({as_of: "实际分析时间，含时区", series, max_chars: 12000});
store("batch-snapshot", result);
text(result.brief.text);
text(result.metrics);
```

每个 `series` 项提供 `market=cn_equity或us_equity或crypto_spot / source / provider_symbol / interval / adjust_type / trade_session / payload`；回退时补 `source_fallback_reason / fallback_detail`。分钟时间戳语义有证据才给 `timestamp_semantics=open`；日线为交易所当地日期标签时给 `date`，开盘时间给 `open`；未知给 `unknown`，不能根据网格整齐猜测语义。

币圈使用 `source=binance_spot_skill:/api/v3/klines / adjust_type=none / trade_session=continuous / server_time=该批Binance时钟`。支持Binance原始数组与MCP `result` 包装，规范化 `close_time`；按UTC连续交易网格校验，保留 `close_time <= min(server_time,as_of)` 的K线，缺少服务器时钟明确报错，不以本机时钟冒充。币圈不请求股票交易日历。

`trading_days` 必须覆盖全窗口；美股再提供 `calendar_coverage={start,end}` 和 `session_closes_verified=true`，仅在有覆盖范围与半日市证据时设置。`session_closes={"交易日":780}` 表示纽约13:00收盘，其他已确认常规日默认960（16:00）；未知保留质量警告。美股默认使用 `America/New_York`，自动处理夏令时，1h最后15:30开始的K线在16:00完成；半日市12:30开始的末根在13:00完成。日线按交易日收盘判断，不加24小时。

- 接收长桥数组、Binance现货数组、MCP响应或Yahoo chart JSON。先完成排序、去重、OHLC校验、完整性分类和覆盖内时段缺口检查，再计算指标；错误只影响该序列。
- 15:00零量占位、真实收盘成交、不规则时间戳分别保留参考。真实成交归属未知时不取整、不猜测合并，也不宣称其不存在。
- 在有效历史上预热Wilder RSI14、首收盘价初始化的EMA MACD12/26/9（柱=2×(DIF−DEA)）、VMA20和枢轴，再裁剪固定窗口。
- `history_status`表示根数，`data_quality`表示质量，`timeframe_status`表示综合状态。根数足够但时间语义/日历/复权未知，存在冲突或缺口时标 `degraded_quality`；不能以 `complete` 掩盖异常。少于50根不做完整分析。
- 枢轴是局部已确认点，不能代替主要结构；数学背离仅为 `candidate`，有效比较无匹配是 `none`，缺锚点/预热不足是 `insufficient`。
- 原始响应、全部有效历史、完整快照和证据留在当前会话。只有数据修订/计算错误/参数变化才重算受影响项；换格式只调用 `renderBrief`，不重新取数和计算。

## 输出长度与异常停止条件

- 整批交接默认上限12000字符，按标的合并周期，共用供应商参数和质量字典。不要直接 `text(result)` 输出完整快照。
- 输出前逐级减少最近K线和额外枢轴，保留全部标的、周期根数/状态、价位范围、指标和背离锚点；最低证据仍超预算就明确报错，拆分已保存快照，不截断JSON或无声丢标的。
- 可一次分类的异常直接记录并降级。仅当未知语义影响方向/关键位，已有快照不能支持有效判断时，再查官方文档或补失败周期；仍未知则披露限制，不反复探测。
- 摘要 `quality` 索引对应顶层 `quality_codes`，`profile` 对应顶层 `profiles`；最低档行数组按顶层 `columns` 解释。锚点用UTC，报告转交易所时区。时间语义未知时网格空位只是候选缺口，不能宣称已确认缺失。
- `last` 是最后完整周期K线的收盘价，`close_ref` 是未合并的收盘附加参考（时间/价/量），二者不能混称官方收盘报价；需要官方报价时按取数规则同源核对。

## 必要分析规则

1. 按实际请求周期从高到低判断方向、位置和触发；日线＋小时线分别判断后检查一致性，冲突时不输出可执行方案。
2. 主要摆动应有至少3根同向推动，幅度占窗口高低差至少10%；局部枢轴仅定位。比较高低点抬高/降低、结构突破及是否收回，再判断上升、下降、区间或过渡。
3. 列2–3个重复触碰、密集成交或已破位结构支持的价位区域；异常数据的精确高低价不作为可靠触发价。
4. 检查最近3–5根实体、影线和推动/回调强度；形态不清就不命名。候选背离核对成对锚点、主要结构相关性与价格确认，微小差异不升级为反转。
5. 成交量/20根均量≥1.5为放量，≤0.7为缩量；分开末根与近5根均量比值，注意时段差异，结合涨跌/突破行为，量能缺失明确说明。
6. 背离区分“无背离、候选、已确认、无法判断”；已确认需要结构相关性与价格行为支持。超买超卖、金叉死叉不独立提高信心。

## 默认报告与耗时

- 总览表：实际周期方向、最新有效价/日期、当前偏向。逐标的三项：结构证据、关键位、确认/失效条件；只展开影响判断的指标锚点，不重复所有步骤。单标的参考600–1000中文字符，六标的参考1000–1500中文字符，必要证据优先。
- 共用数据说明一次；逐标的紧凑表保留 `data_channel / requested_bars / actual_bars / valid_complete_bars / analysis_bars / timeframe_status`，披露异常，末尾附免责声明。
- 记录 `fetch_wall_ms / normalize_indicator_ms / render_ms / request_count / retry_count / duplicate_request_count / output_chars`。取数从派发到最后任务完成计墙钟，不把并发时长相加。
- 另记录规则加载/能力发现、异常复核次数、工具往返和可观测报告阶段时间。处理器时间不包含模型推理和生成；端到端耗时仅在平台完整记录时报告，不用取数替代总等待。
- 加载处理器后立即初始化 `trace=api.createRunTrace()`，用 `mark(phase,"start"/"end")` 记录后续 `rules / capability_discovery / report`；加载前已发生的耗时写未观测，不能猜测补计。`runAnalysis({tasks,as_of,max_chars}, fetcher, {trace,onResponse,retryable})` 自动记录 `fetch / process`，辅助校验 `auxiliaryOnce` 自动记录各辅助项。
- 跨 `functions.exec` 只保存可序列化状态：结束并await实际请求后 `store("analysis-trace",trace.exportState())`；后续 `api.createRunTrace({state:load("analysis-trace")})` 恢复。不能用 `store` 保存带函数的处理器或计时实例。原始响应、结果摘要和快照同样保存一次。
- `trace.snapshot()` 给出实际开始后的 `observed_elapsed_ms`、各阶段 `phases_ms`、未结束阶段和辅助请求数，`end_to_end_ms` 默认null。最终回复发送耗时只有平台能观测，不能用输出前时间冒充它。跨阶段可能重叠，阶段时长不能简单相加。
- 普通问答以120秒作为停止额外辅助工作的观察预算，超时即使用现有证据给出分析或明确不足；这不是完成时间保证。当前主行情请求失败按取数规则回退，不能为赶时限捏造结果。
- 确定性工具并行即可，不默认增加分析代理。跨会话缓存和持续增量更新仍按用户明确请求启用。
