# Stock Technical Analysis Agent System Design

> 将现有的技术分析 Skill（纯 markdown 流程）改造为基于 Mastra 的多模块智能体系统。

## 1. 背景与动机

### 现状

项目当前是一个 Claude Code Skill，由以下 markdown 文件构成：

- `workflows/chart-analysis-workflow.md` — 8 步图表分析流程（Step 0~7）
- `workflows/trading-decision.md` — Playbook 匹配 + 入场前检查 + 仓位计算
- `workflows/output-templates.md` — 输出格式模板
- `references/` — 核心概念、形态、指标、Playbook、风控参考知识（23 个文件）

AI 读取这些文档后按步骤执行分析，流程本身是完善的。

### 改造动机

| 痛点 | 说明 |
|------|------|
| Skill 体积过大 | 一次分析需加载大量 markdown，上下文效率低 |
| 无法自动获取数据 | 依赖用户手动提供截图或触发 MCP |
| 知识库固定 | Playbook 规则写死在 markdown 里，无法通过历史数据迭代优化 |
| 无闭环 | 分析完就结束，没有信号通知、交易记录、效果回测 |
| 无法并行 | 无法同时分析多个品种 |

### 目标

构建一个 **Orchestrator + 功能模块混合** 的智能体系统：
- 该用 LLM 的地方用 LLM（图表分析、交易决策），不该用的地方用代码（数据获取、仓位计算）
- 通过 RAG 实现知识检索和经验积累
- 通过 Scheduler + Notifier + Trade Journal 实现完整闭环
- 核心分析逻辑保持不变（现有工作流已验证可用）

### 非目标（当前阶段）

- 不做多用户系统、注册登录
- 不做对外 API 服务
- 不做 Web UI
- 不改变现有分析逻辑和 Playbook 规则本身

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────┐
│              Orchestrator Agent                  │
│   (Mastra Agent — 路由、流程控制、上下文管理)       │
└──────┬──────┬──────────┬──────────┬──────────────┘
       │      │          │          │
       ▼      ▼          ▼          ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│  Data    ││  Chart   ││ Trading  ││  Risk    │
│  Module  ││ Analysis ││ Decision ││  Module  │
│(纯代码)  ││(LLM Agent)││(LLM+RAG)││(代码+LLM)│
└──────────┘└──────────┘└──────────┘└──────────┘
       │          │          │          │
       └──────────┴─────┬────┴──────────┘
                        ▼
         ┌────────────────────────────┐
         │       Shared Services      │
         │  ┌──────┐ ┌─────────────┐  │
         │  │ RAG  │ │Trade Journal│  │
         │  └──────┘ └─────────────┘  │
         └────────────────────────────┘
                        ▼
         ┌────────────────────────────┐
         │      Infra Services        │
         │  ┌──────────┐ ┌────────┐  │
         │  │Scheduler │ │Notifier│  │
         │  └──────────┘ └────────┘  │
         └────────────────────────────┘
```

### Mastra 映射

| 模块 | Mastra 概念 | LLM 参与 |
|------|-------------|----------|
| Orchestrator | Agent（带 tools） | 是（轻量路由模型） |
| Data Module | Tool（纯函数） | 否 |
| Chart Analysis | Agent（独立 LLM 调用） | 是（需视觉能力） |
| Trading Decision | Agent（独立 LLM 调用 + RAG tool） | 是 |
| Risk Module | Tool（计算函数）+ 可选 LLM | 部分 |
| RAG Service | Tool + 向量存储 | 否（检索是代码） |
| Trade Journal | Tool + 数据库 | 否 |
| Scheduler | Mastra Workflow trigger / cron | 否 |
| Notifier | Tool（推送函数） | 否 |
| 流程编排 | Mastra Workflow（串联/并联步骤） | — |

### 核心原则

1. **Orchestrator 是唯一入口** — 接收用户请求或定时任务触发，决定调用哪些模块、以什么顺序
2. **Unified Schema** — TypeScript types 定义模块间数据格式，所有模块输入输出遵守同一契约
3. **RAG Service 是共享基础设施** — Chart Analysis 和 Trading Decision 都可查询历史经验
4. **每个模块可独立开发、测试、替换** — 只要遵守 Schema

---

## 3. Unified Schema（数据契约层）

### 3.1 市场数据

```typescript
interface MarketData {
  asset: AssetInfo
  timeframe: Timeframe
  candles: OHLCV[]
  source: DataSource
}

interface AssetInfo {
  symbol: string             // "BTCUSDT" | "AAPL" | "600519"
  market: "crypto" | "us_stock" | "a_stock"
  name?: string
}

type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d" | "1w" | "1M"

interface OHLCV {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type DataSource =
  | { type: "api"; provider: string }          // "binance" | "yahoo" | "daily_stock_analysis"
  | { type: "screenshot"; description?: string }
  | { type: "manual"; note?: string }
```

### 3.2 图表分析输出

```typescript
interface ChartAnalysis {
  marketStructure: MarketStructure
  keyLevels: KeyLevel[]
  priceAction: PriceActionSummary
  patterns: PatternMatch[]
  indicators?: IndicatorSignals
  synthesis: Synthesis
  confidence: ConfidenceLevel
  metadata: AnalysisMetadata
}

interface MarketStructure {
  trend: "uptrend" | "downtrend" | "range" | "chaotic"
  swingPoints: SwingPoint[]        // HH, HL, LH, LL
  bosEvents: BOSEvent[]            // Break of Structure
  chochEvents?: CHoCHEvent[]       // Change of Character
  health: "strong" | "weakening" | "exhausted"
}

interface SwingPoint {
  price: number
  timestamp: number
  type: "HH" | "HL" | "LH" | "LL"
  significance: "major" | "minor"
}

interface BOSEvent {
  level: number
  direction: "bullish" | "bearish"
  confirmed: boolean
  timestamp: number
}

interface CHoCHEvent {
  from: "uptrend" | "downtrend" | "range"
  to: "uptrend" | "downtrend" | "range"
  triggerLevel: number
  confirmed: boolean
}

interface KeyLevel {
  price: number
  type: "support" | "resistance" | "flip"
  strength: "strong" | "moderate" | "weak"
  touchCount: number
  notes?: string
}

interface PriceActionSummary {
  recentCandles: CandleSummary[]
  momentum: "strong_bullish" | "bullish" | "neutral" | "bearish" | "strong_bearish"
  volatility: "high" | "normal" | "low"
  keyObservation: string
}

interface CandleSummary {
  type: "bullish" | "bearish" | "doji"
  bodySize: "large" | "medium" | "small"
  upperWick: "long" | "short" | "none"
  lowerWick: "long" | "short" | "none"
  volume: "above_avg" | "average" | "below_avg"
}

interface PatternMatch {
  name: string                     // "head_and_shoulders" | "bull_flag" | ...
  status: "forming" | "completed" | "confirmed"
  direction: "bullish" | "bearish"
  keyPoints: Record<string, number>
}

interface IndicatorSignals {
  rsi?: {
    value: number
    condition: "overbought" | "oversold" | "neutral"
    divergence?: "bullish" | "bearish"
  }
  macd?: {
    signal: "bullish_cross" | "bearish_cross" | "neutral"
    histogram: "expanding" | "contracting"
    zeroLine: "above" | "below"
  }
}

interface Synthesis {
  bias: "bullish" | "bearish" | "neutral"
  signalStrength: "strong" | "moderate" | "weak" | "none"
  narrative: string
  multiTimeframeAlignment?: "aligned" | "conflicting" | "neutral"
  conflictingSignals?: string[]
}

type ConfidenceLevel = "high" | "medium" | "low"

interface AnalysisMetadata {
  analyzedAt: number
  dataSource: DataSource
  modelUsed: string
  analysisVersion: string
}
```

### 3.3 交易计划

```typescript
interface TradePlan {
  direction: "long" | "short"
  playbook: PlaybookType
  entry: EntryCondition
  stopLoss: PriceLevel
  targets: PriceLevel[]
  position: PositionSize
  checklistResult: ChecklistResult
  ragContext?: RAGMatch[]
  confidence: ConfidenceLevel
}

type PlaybookType =
  | "trend-pullback"
  | "breakout-retest"
  | "range-reversal"
  | "false-breakout-reversal"
  | "flag-wedge-breakout"

interface EntryCondition {
  type: "limit" | "stop" | "conditional"
  price?: number
  condition: string
}

interface PriceLevel {
  price: number
  label: string
  rationale: string
}

interface PositionSize {
  riskPercent: number
  quantity: number
  riskAmount: number
  riskRewardRatio: number
}

interface ChecklistResult {
  passed: boolean
  hardFilters: HardFilterResult[]
  softFilters: SoftFilterResult[]
  totalScore: number
}

interface HardFilterResult {
  name: string                     // "信号强度" | "市场状态" | "多周期一致性"
  passed: boolean
  detail: string
}

interface SoftFilterResult {
  name: string
  score: number                    // 0-1
  detail: string
}

interface NoTradeDecision {
  reason: string
  suggestion: string
  watchConditions?: string[]
}

type TradeDecision = TradePlan | NoTradeDecision
```

### 3.4 RAG 相关

```typescript
interface RAGQuery {
  type: "similar_pattern" | "playbook_performance" | "asset_history"
  context: Partial<ChartAnalysis>
  filters?: {
    market?: AssetInfo["market"]
    playbook?: PlaybookType
    dateRange?: { from: number; to: number }
  }
}

interface RAGMatch {
  similarity: number
  historicalAnalysis: ChartAnalysis
  tradePlan?: TradePlan
  outcome?: TradeOutcome
}

interface TradeOutcome {
  entryPrice: number
  exitPrice: number
  pnlPercent: number
  hitTarget: boolean
  hitStopLoss: boolean
  holdingPeriod: number            // 小时
  exitReason: string
  notes?: string
}
```

### 3.5 Trade Journal 相关

```typescript
interface JournalEntry {
  id: string
  createdAt: number
  asset: AssetInfo
  timeframes: Timeframe[]

  // 分析阶段
  marketData: MarketData
  chartAnalysis: ChartAnalysis
  tradeDecision: TradeDecision

  // 执行阶段（用户手动补充）
  execution?: {
    actualEntry: number
    actualExit: number
    outcome: TradeOutcome
    userNotes?: string
  }

  // 系统字段
  triggerType: "manual" | "scheduled"
  notified: boolean
}
```

### 3.6 Scheduler 相关

```typescript
interface WatchlistItem {
  asset: AssetInfo
  timeframes: Timeframe[]
  schedule: string                 // cron 表达式，如 "0 9 * * 1-5"
  enabled: boolean
}

interface SchedulerConfig {
  watchlist: WatchlistItem[]
  tradingCalendar: TradingCalendar
  maxConcurrent: number
}

interface TradingCalendar {
  market: AssetInfo["market"]
  isOpen(date: Date): boolean
}
```

### 3.7 Notifier 相关

```typescript
interface NotificationChannel {
  readonly type: string
  send(message: NotificationMessage): Promise<boolean>
}

interface NotificationMessage {
  title: string                    // "BTC/USDT 4H 做多信号"
  summary: string
  tradePlan?: TradePlan
  urgency: "high" | "normal"
  asset: AssetInfo
  timestamp: number
}
```

### 3.8 扩展性设计

- 所有 interface 用**组合而非继承** — 新增模块只需定义自己的输入输出 type
- `metadata` 字段统一携带溯源信息（时间戳、数据源、分析版本），方便回测和 RAG 入库
- 枚举类型（`PlaybookType`、`Timeframe`）集中定义，新增 Playbook 只需扩展枚举
- `DataSource` 用 tagged union 支持多种来源，新增来源只加一个 variant
- Schema 变更通过 TypeScript 编译器强制所有模块同步更新

---

## 4. Data Module（数据获取模块）

### 类型：纯代码 Tool

### 职责

将各种数据源统一转换为 `MarketData` 格式。

### 架构

```
用户输入（图片 / API 参数 / 混合）
         │
         ▼
   ┌─ DataModule ─────────────────────────┐
   │                                       │
   │  ┌───────────┐  ┌───────────┐        │
   │  │ Adapter   │  │ Adapter   │  ...   │
   │  │ (DSA API) │  │ (Binance) │        │
   │  └─────┬─────┘  └─────┬─────┘        │
   │        └───────┬───────┘              │
   │                ▼                      │
   │        ┌─────────────┐               │
   │        │  Normalizer  │               │
   │        │ → MarketData │               │
   │        └─────────────┘               │
   │                                       │
   │  ┌───────────────────┐               │
   │  │  Image Passthrough │               │
   │  │ (截图直传分析Agent) │               │
   │  └───────────────────┘               │
   └───────────────────────────────────────┘
```

### Adapter 接口

```typescript
interface DataAdapter {
  readonly source: string
  readonly supportedMarkets: AssetInfo["market"][]
  fetchCandles(params: FetchParams): Promise<OHLCV[]>
  healthCheck(): Promise<boolean>
}

interface FetchParams {
  symbol: string
  timeframe: Timeframe
  limit?: number                             // 默认 200 根 K 线
}

class DataAdapterRegistry {
  register(adapter: DataAdapter): void
  resolve(market: AssetInfo["market"], symbol: string): DataAdapter
  fallback(primary: string, secondary: string): void  // 设置降级链
  list(): DataAdapter[]
}
```

### 数据获取策略：桥接 daily_stock_analysis

**不重新实现数据获取层。** 通过 HTTP 调用 [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 的 FastAPI 服务作为主要数据源。

**理由：**
- DSA 拥有成熟的 6 个数据源（AkShare/Tushare/Yahoo/Baostock/Pytdx/efinance）+ 自动 failover + 反爬策略
- 覆盖 A 股、美股、加密货币，与本项目需求完全匹配
- 在 TypeScript 中重写这些 A 股数据获取逻辑价值极低
- DSA 作为独立服务部署，数据层和分析层解耦

```typescript
class DailyStockAnalysisAdapter implements DataAdapter {
  readonly source = "daily_stock_analysis"
  readonly supportedMarkets: AssetInfo["market"][] = ["a_stock", "us_stock", "crypto"]

  constructor(private baseUrl: string) {}

  // 调用 DSA 的 FastAPI 端点，将返回数据转为 OHLCV[]
  async fetchCandles(params: FetchParams): Promise<OHLCV[]> {
    // GET /api/v1/candles?symbol=xxx&timeframe=xxx&limit=xxx
    // DSA 返回 DataFrame 格式 → 转换为 OHLCV[]
  }

  async healthCheck(): Promise<boolean> {
    // GET /api/v1/health
  }
}
```

**其他 Adapter（按需添加）：**

| Adapter | 优先级 | 用途 |
|---------|--------|------|
| DailyStockAnalysisAdapter | P0 | 主数据源，A股/美股/加密货币 |
| BinanceAdapter | P1 | 加密货币直连（WebSocket 实时数据） |
| YahooAdapter | P2 | 美股补充/DSA 不可用时降级 |

**新增数据源流程：** 实现 `DataAdapter` 接口 → 注册到 Registry → 自动可用。

### 截图处理

Data Module **不做** 图像识别。截图输入时：
1. 标记 `source: { type: "screenshot" }`
2. 基本预处理（尺寸检查、格式验证）
3. 将原始图片直接传递给 Chart Analysis Agent（利用 LLM 视觉能力）

---

## 5. Chart Analysis Agent（图表分析）

### 类型：LLM Agent

### 职责

接收 `MarketData`（或截图），输出 `ChartAnalysis`。

### Agent 定义

```typescript
const chartAnalysisAgent = new Agent({
  name: "chart-analysis",
  instructions: buildAnalysisPrompt(),
  model: openai("gpt-4o"),              // 需要视觉能力
  tools: {
    queryRAG,           // 查询历史相似形态
    calculateSMA,       // 均线计算（纯代码）
    calculateRSI,       // RSI 计算（纯代码）
    calculateMACD,      // MACD 计算（纯代码）
    findSwingPoints,    // 摆动高低点识别（纯代码）
    findKeyLevels,      // 支撑阻力初筛（纯代码）
  },
})
```

### Prompt 策略：从固定 markdown 到动态组装

```
Base Prompt（固定）
  = 分析框架 + 输出格式要求
  = 精简版 chart-analysis-workflow.md（Step 0~7 的核心逻辑）

+ Context Prompt（动态）
  = 当前 MarketData 摘要（品种、周期、最近价格走势）
  + RAG 检索到的历史相似案例（如果有）

+ Reference Prompt（按需注入）
  = 只在需要时加载具体参考知识
  = 例：检测到可能是头肩顶 → 注入 chart-patterns.md 相关段落
  = 例：RSI 出现背离 → 注入 rsi.md 相关段落
```

### 关键改进（相比现有 Skill）

| 现有 Skill | Agent 改进 |
|-----------|-----------|
| 指标数值由 LLM 从截图估算 | RSI/MACD 由代码精确计算，结果传给 LLM 解读 |
| 关键位全靠 LLM 视觉判断 | 代码先做 swing high/low 初筛，LLM 做确认和语义判断 |
| 全量加载 references | 按需检索：RAG 或条件注入 |
| 单一模型处理所有步骤 | 计算密集步骤用代码，推理步骤用 LLM |

### 分析模式兼容

保留现有 Skill 的三种模式：

| 模式 | 触发条件 | Agent 行为 |
|------|---------|-----------|
| 数据模式 | `source.type === "api"` | 使用代码工具精确计算 + LLM 推理 |
| 图片模式 | `source.type === "screenshot"` | LLM 视觉分析为主，保守原则（不输出具体价位） |
| 混合模式 | 同时有 api 和 screenshot | 数据为准，截图辅助验证 |

---

## 6. Trading Decision Agent（交易决策）

### 类型：LLM Agent + RAG

### 职责

接收 `ChartAnalysis`，输出 `TradeDecision`（`TradePlan` 或 `NoTradeDecision`）。

### Agent 定义

```typescript
const tradingDecisionAgent = new Agent({
  name: "trading-decision",
  instructions: buildDecisionPrompt(),
  model: anthropic("claude-sonnet-4-20250514"),
  tools: {
    queryRAG,
    matchPlaybook,         // 代码：规则匹配 Playbook
    runChecklist,          // 代码：执行入场前检查
    calculatePosition,     // 代码：仓位计算公式
  },
})
```

### Hard Gate（代码强制执行）

以下门槛由 **代码 Tool** 直接拦截，不依赖 LLM 判断：

```typescript
function matchPlaybook(analysis: ChartAnalysis): PlaybookType | null {
  // 按 trading-decision.md 的决策树实现
  // 返回 null → 直接输出 NoTradeDecision，不进入 LLM 决策
}

function runChecklist(analysis: ChartAnalysis, plan: Partial<TradePlan>): ChecklistResult {
  // 硬性过滤器任一失败 → passed = false
  // 1. 信号强度 !== "weak"
  // 2. 市场状态 !== "chaotic"
  // 3. 多周期一致性 !== "conflicting"
}
```

**为什么用代码而非 LLM：** 确保交易纪律，LLM 无法"说服自己"绕过规则。

### RAG 使用场景

| 触发时机 | RAG 查询 | 用途 |
|---------|---------|------|
| Playbook 匹配后 | "这个形态 + Playbook 历史胜率如何？" | 提供历史胜负统计 |
| 信号模糊时 | "过去类似模糊信号最终怎么走的？" | 辅助 trade / no-trade 决策 |
| 仓位决策时 | "这个品种最近的波动率和分析历史" | 辅助调整仓位比例 |

---

## 7. Risk Module（风险管理）

### 类型：代码为主 + 可选 LLM

### 核心函数（纯代码）

```typescript
function calculatePositionSize(params: {
  capital: number
  riskPercent: number
  entryPrice: number
  stopLossPrice: number
}): PositionSize

function checkDrawdownLimits(params: {
  recentTrades: TradeOutcome[]
  dailyPnL: number
  weeklyPnL: number
  monthlyPnL: number
}): { canTrade: boolean; maxRiskPercent: number; reason?: string }
```

### 风控规则（代码写死）

- 单笔风险：1-2%，绝对上限 3%
- 连续亏损 → 自动降至 0.5-1%
- 日亏损上限 2%，周 5%，月 10%（触发强制暂停）

### LLM 辅助（后期扩展）

- 事件风险判断："今天有 FOMC，是否降低仓位？"
- 异常波动识别："波动率是平时 3 倍，什么原因？"

---

## 8. RAG Service（共享知识服务）

### 两类数据入库

**8.1 历史分析报告：**

```
每次分析完成后：
  ChartAnalysis + TradeDecision + TradeOutcome（如有）
  → 结构化存储（关系数据库）
  → 关键文本字段向量化（narrative、keyObservation 等）
  → 按形态、品种、Playbook、时间等维度可检索
```

**8.2 Playbook 知识库：**

```
现有 references/ 下的 markdown 文件
  → 按概念/规则粒度分段
  → 向量化存储
  → Agent 按需检索，而非全量注入 prompt
```

### 向量存储

初期使用本地方案：
- **推荐：** PostgreSQL + pgvector（与 Trade Journal 共用数据库）
- **备选：** SQLite + sqlite-vss（更轻量）
- 数据量不大（几百到几千条分析记录），不需要云端向量数据库

### Playbook 迭代闭环

```
分析 → 交易计划 → 执行 → 结果记录（Trade Journal）→ 入库 RAG
                                                      ↓
                              RAG 检索时自动提供胜率反馈
                                                      ↓
                              逐步发现哪些 Playbook/条件组合更有效
                                                      ↓
                              人工审核后更新 Playbook 规则
```

---

## 9. Trade Journal（交易日志）

### 类型：代码 Tool + 数据库

### 职责

记录每次分析和交易结果，为 RAG 提供数据源，为回测提供素材。

### 存储

- 使用 PostgreSQL（与 RAG 的 pgvector 共用同一数据库）
- `JournalEntry` 完整存储在关系表中
- 文本字段（narrative、notes）同时写入向量索引，供 RAG 检索
- "无信号"的分析也记录（用于统计"不做的准确率"）

### 回测支持

```
Trade Journal 积累足够数据后：
  → 按 Playbook 分组统计胜率
  → 按品种/时间段切片分析
  → 识别 "哪些条件组合效果最好"
  → 反馈到 Playbook 规则迭代
```

### 数据录入

| 阶段 | 自动/手动 | 数据 |
|------|----------|------|
| 分析完成 | 自动 | ChartAnalysis + TradeDecision |
| 交易执行 | 手动 | 实际入场价、出场价 |
| 交易结束 | 手动 | TradeOutcome + 复盘笔记 |

---

## 10. Scheduler（定时任务）

### 类型：代码

### 职责

按 watchlist 和时间规则自动触发分析任务。

### 执行流程

```
Cron 触发
  ↓
检查是否交易日 → 否 → 跳过
  ↓ 是
遍历 watchlist（启用的品种）
  ↓
每个品种 → Orchestrator.analyze(asset, timeframes)（可并行）
  ↓
  ├─ 发现信号（High/Medium confidence）→ Notifier 推送
  └─ 无信号 → 记录到 Trade Journal
```

### 交易日历

| 市场 | 交易时间 | 休市规则 |
|------|---------|---------|
| A 股 | 09:30-15:00 北京时间，周一至周五 | 中国法定节假日 |
| 美股 | 09:30-16:00 ET，周一至周五 | 美国法定节假日 |
| 加密货币 | 24/7 | 无 |

### 配置

通过 `config/watchlist.json` 配置关注品种和扫描时间：

```json
{
  "watchlist": [
    {
      "symbol": "BTCUSDT",
      "market": "crypto",
      "timeframes": ["4h", "1d"],
      "schedule": "0 */4 * * *",
      "enabled": true
    },
    {
      "symbol": "AAPL",
      "market": "us_stock",
      "timeframes": ["1d"],
      "schedule": "0 16 * * 1-5",
      "enabled": true
    }
  ],
  "maxConcurrent": 3
}
```

---

## 11. Notifier（信号通知）

### 类型：代码 Tool

### 职责

发现交易信号时推送到用户终端。

### 通知渠道（按优先级实现）

| 渠道 | 优先级 | 说明 |
|------|--------|------|
| Telegram Bot | P0 | 最适合交易通知，支持富文本 + 图表 |
| Webhook | P1 | 通用接口，可对接任意系统 |
| Email | P2 | 备份通道 |
| 其他（微信/钉钉/Slack） | P3 | 后期按需扩展 |

### 通知规则

| 场景 | 是否推送 | 紧急度 |
|------|---------|--------|
| High confidence 信号 | 是 | high |
| Medium confidence 信号 | 是 | normal |
| Low confidence / 无信号 | 否（仅记录） | — |
| 系统错误 / 数据获取失败 | 是 | high |

### 通知内容格式

```
📊 BTC/USDT 4H 做多信号

方向: Long | Playbook: trend-pullback
入场: 回踩 68000 出现 Pin Bar 后
止损: 66500 (-2.2%)
目标: T1 72000 (+5.9%) | T2 76000 (+11.8%)
仓位: 1.5% 风险
置信度: High

历史参考: 过去 12 次类似形态，胜率 67%
```

### 配置

通过 `config/notification.json`：

```json
{
  "channels": [
    {
      "type": "telegram",
      "botToken": "${TELEGRAM_BOT_TOKEN}",
      "chatId": "${TELEGRAM_CHAT_ID}",
      "enabled": true
    },
    {
      "type": "webhook",
      "url": "https://...",
      "enabled": false
    }
  ],
  "rules": {
    "minConfidence": "medium",
    "notifyOnError": true
  }
}
```

---

## 12. Orchestrator Agent（编排层）

### Agent 定义

```typescript
const orchestrator = new Agent({
  name: "orchestrator",
  instructions: `你是一个技术分析编排器。根据用户输入或定时任务触发，
    决定调用哪些模块、以什么顺序执行。`,
  model: anthropic("claude-haiku-4-5-20251001"),  // 路由不需要强模型
  tools: {
    fetchData,              // → Data Module
    analyzeChart,           // → Chart Analysis Agent
    makeTradingDecision,    // → Trading Decision Agent
    calculateRisk,          // → Risk Module
    queryHistory,           // → RAG Service
    recordJournal,          // → Trade Journal
    notify,                 // → Notifier
  },
})
```

### 典型流程（Mastra Workflow）

**完整分析流程：**
```
fetchData → analyzeChart → makeTradingDecision → calculateRisk
                                                       ↓
                                              recordJournal → notify（如有信号）
```

**快速查询：**
```
queryHistory → 直接返回
```

**多品种并行：**
```
┌→ fetchData(BTC) → analyzeChart(BTC) ─┐
│→ fetchData(AAPL) → analyzeChart(AAPL)─┤→ 汇总对比 → notify
└→ fetchData(600519) → analyzeChart(...)─┘
```

**定时批量扫描：**
```
Scheduler 触发
  ↓
for each watchlist item (并行, 受 maxConcurrent 限制):
  fetchData → analyzeChart → makeTradingDecision
  ↓
  有信号？→ calculateRisk → recordJournal → notify
  无信号？→ recordJournal（记录"无信号"）
```

---

## 13. 错误处理策略

| 模块 | 失败场景 | 处理方式 |
|------|---------|---------|
| Data Module | API 超时/不可用 | 尝试 fallback Adapter；都失败则提示用户手动输入 |
| Data Module | 数据格式异常 | Normalizer 做 schema 校验，不合规数据丢弃并记录日志 |
| Chart Analysis | LLM 返回格式不符合 Schema | Zod 校验输出，失败则重试一次（附格式纠正提示），仍失败则返回低置信度结果 |
| Chart Analysis | 截图模糊/无法识别 | 标记 `confidence: "low"`，跳过无法确认的字段 |
| Trading Decision | Playbook 无匹配 | 正常路径：输出 NoTradeDecision，不视为错误 |
| Trading Decision | LLM 试图绕过 Hard Gate | 代码层强制拦截，不依赖 LLM 自律 |
| RAG Service | 向量库不可用 | 降级运行：跳过 RAG，Agent 仅用自身知识，标注"无历史参考" |
| Notifier | 推送失败 | 重试一次；仍失败则记录日志，不阻塞主流程 |
| Scheduler | 某品种分析失败 | 记录错误，继续分析其他品种；推送错误通知 |
| Orchestrator | 子模块超时 | 每模块最大等待时间，超时后返回已完成部分 |

**总原则：** 降级优于失败。任何模块出错不应阻塞整个流程，而是降低输出质量并明确告知用户。

---

## 14. 测试策略

| 层级 | 范围 | 方法 |
|------|------|------|
| Schema 校验 | 所有模块的输入输出 | Zod schema 验证，单元测试覆盖所有 type |
| 工具单测 | 指标计算、swing point、仓位计算等纯函数 | 用已知数据集验证计算结果正确性 |
| Adapter 测试 | 各数据源适配器 | Mock API 响应，验证 Normalizer 输出符合 MarketData schema |
| Agent 测试 | Chart Analysis / Trading Decision | 固定 MarketData 输入 + snapshot 对比输出结构（不验证分析内容，只验证格式） |
| Workflow 集成测试 | 完整分析流程 | 端到端测试：输入 → 各模块串联 → 验证最终输出结构完整 |
| RAG 测试 | 入库和检索 | 固定数据入库后验证检索结果的相关性 |
| Notifier 测试 | 通知推送 | Mock 通知渠道，验证消息格式和推送规则 |

**不测什么：** LLM 的分析"正确性"（主观判断无法自动化验证）。分析质量通过 RAG 迭代闭环逐步优化。

---

## 15. 项目结构

```
stock-technical-analysis/
├── src/
│   ├── agents/
│   │   ├── orchestrator.ts          # Orchestrator Agent 定义
│   │   ├── chart-analysis.ts        # Chart Analysis Agent 定义
│   │   └── trading-decision.ts      # Trading Decision Agent 定义
│   │
│   ├── tools/
│   │   ├── data/
│   │   │   ├── adapters/            # DataAdapter 实现
│   │   │   │   ├── interface.ts     # DataAdapter 接口定义
│   │   │   │   ├── daily-stock-analysis.ts  # DSA 桥接
│   │   │   │   ├── binance.ts       # 加密货币直连
│   │   │   │   └── yahoo.ts         # 美股补充
│   │   │   ├── registry.ts          # DataAdapterRegistry
│   │   │   └── normalizer.ts        # → MarketData 转换
│   │   │
│   │   ├── indicators/              # 技术指标计算（纯代码）
│   │   │   ├── rsi.ts
│   │   │   ├── macd.ts
│   │   │   ├── sma.ts
│   │   │   └── swing-points.ts      # 摆动高低点检测
│   │   │
│   │   ├── risk/                    # 风险计算
│   │   │   ├── position-sizing.ts
│   │   │   └── drawdown-check.ts
│   │   │
│   │   ├── playbook/                # Playbook 匹配 + Checklist
│   │   │   ├── matcher.ts           # 决策树规则匹配
│   │   │   └── checklist.ts         # Hard Gate + Soft Filter
│   │   │
│   │   └── journal/                 # Trade Journal
│   │       ├── record.ts            # 记录分析/交易
│   │       └── query.ts             # 查询/统计
│   │
│   ├── services/
│   │   ├── rag/                     # RAG Service
│   │   │   ├── index.ts
│   │   │   ├── ingest.ts            # 数据入库（分析报告 + references）
│   │   │   └── query.ts             # 向量检索
│   │   │
│   │   ├── scheduler/               # 定时任务
│   │   │   ├── index.ts
│   │   │   ├── watchlist.ts         # Watchlist 管理
│   │   │   └── trading-calendar.ts  # 交易日判断
│   │   │
│   │   └── notifier/                # 通知推送
│   │       ├── index.ts             # NotificationChannel 注册
│   │       ├── telegram.ts
│   │       └── webhook.ts
│   │
│   ├── schema/                      # Unified Schema（TypeScript types）
│   │   ├── market-data.ts
│   │   ├── chart-analysis.ts
│   │   ├── trade-plan.ts
│   │   ├── journal.ts
│   │   ├── rag.ts
│   │   └── index.ts                 # re-export all
│   │
│   ├── prompts/                     # LLM Prompt 模板
│   │   ├── chart-analysis.ts        # Base + Context + Reference prompt 构建
│   │   └── trading-decision.ts
│   │
│   ├── workflows/                   # Mastra Workflow 定义
│   │   ├── full-analysis.ts         # 完整分析流程
│   │   ├── batch-scan.ts            # 定时批量扫描
│   │   └── quick-query.ts           # 快速历史查询
│   │
│   └── index.ts                     # Mastra 实例初始化
│
├── references/                      # 现有知识库（保留，供 RAG 入库）
│   ├── core/
│   ├── patterns/
│   ├── playbooks/
│   ├── indicators/
│   ├── checklists/
│   └── risk/
│
├── workflows/                       # 现有 Skill workflow（保留作为参考）
│   ├── chart-analysis-workflow.md
│   ├── trading-decision.md
│   └── output-templates.md
│
├── config/
│   ├── watchlist.json               # 关注品种列表 + 扫描时间
│   └── notification.json            # 通知渠道配置
│
├── package.json
├── tsconfig.json
└── README.md
```

---

## 16. 开发优先级

分阶段交付，每个阶段是一个可独立运行的版本。

### Phase 1：核心分析能力（MVP）

**目标：** 替代现有 Skill，能通过 Agent 完成一次完整分析。

| 任务 | 模块 |
|------|------|
| 初始化 Mastra 项目 | 项目骨架 |
| 定义 Unified Schema | `src/schema/` |
| 实现指标计算工具（RSI、MACD、SMA、swing points） | `src/tools/indicators/` |
| 实现 Chart Analysis Agent + prompt | `src/agents/chart-analysis.ts` |
| 实现 Playbook 匹配 + Checklist（Hard Gate） | `src/tools/playbook/` |
| 实现仓位计算 | `src/tools/risk/` |
| 实现 Trading Decision Agent + prompt | `src/agents/trading-decision.ts` |
| 实现 Orchestrator（简版） | `src/agents/orchestrator.ts` |
| 实现完整分析 Workflow | `src/workflows/full-analysis.ts` |

**验证标准：** 手动输入 MarketData → 输出 TradePlan，结果质量不低于现有 Skill。

### Phase 2：数据接入 + 闭环

**目标：** 自动获取数据，分析结果有记录、有通知。

| 任务 | 模块 |
|------|------|
| 实现 DataAdapter 接口 + Registry | `src/tools/data/` |
| 实现 DailyStockAnalysisAdapter（桥接 DSA） | `src/tools/data/adapters/` |
| 实现 Trade Journal（记录 + 查询） | `src/tools/journal/` |
| 实现 Notifier（Telegram） | `src/services/notifier/` |
| 实现 Scheduler + Watchlist + 交易日历 | `src/services/scheduler/` |
| 实现批量扫描 Workflow | `src/workflows/batch-scan.ts` |
| 实现回撤控制 | `src/tools/risk/drawdown-check.ts` |

**验证标准：** 配置 watchlist → 定时自动分析 → 有信号时收到 Telegram 通知 → 结果自动记录。

### Phase 3：RAG + 知识迭代

**目标：** Agent 能参考历史经验，Playbook 规则可基于数据优化。

| 任务 | 模块 |
|------|------|
| 搭建 PostgreSQL + pgvector | 基础设施 |
| 实现 RAG 入库（历史分析报告） | `src/services/rag/ingest.ts` |
| 实现 RAG 入库（references/ markdown） | `src/services/rag/ingest.ts` |
| 实现 RAG 检索 | `src/services/rag/query.ts` |
| 将 RAG 集成到 Chart Analysis + Trading Decision | Agent tools |
| 实现 Playbook 胜率统计 | Trade Journal 聚合查询 |
| 导入已有的历史分析数据 | 数据迁移 |

**验证标准：** 分析时能检索到历史相似案例，Playbook 统计显示各 setup 胜率。

### Phase 4：扩展（后续）

- 更多数据源 Adapter（Binance WebSocket 等）
- 更多通知渠道（微信、钉钉等）
- Risk Module 的 LLM 辅助（宏观事件判断）
- Web UI（产品形态待定）
- 多用户支持（接入自己的 API key）

---

## 17. 技术栈总结

| 层面 | 选型 |
|------|------|
| 语言 | TypeScript |
| Agent 框架 | Mastra |
| LLM（视觉分析） | GPT-4o（需视觉能力） |
| LLM（交易决策） | Claude Sonnet（推理能力强） |
| LLM（路由） | Claude Haiku（轻量快速） |
| 数据获取 | 桥接 daily_stock_analysis FastAPI + 自有 Adapter |
| 数据库 | PostgreSQL（关系 + pgvector） |
| 定时任务 | node-cron / Mastra Workflow trigger |
| 通知 | Telegram Bot API（P0）+ Webhook（P1） |
| Schema 校验 | Zod |
| 测试 | Vitest |

---

## 18. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Chart Analysis Agent 质量不如现有 Skill | 分析结果退步 | Phase 1 用现有 Skill 做对照测试，逐步迁移 prompt |
| DSA 服务不稳定或 API 变化 | 数据获取失败 | Adapter 模式 + fallback 链，可随时切换数据源 |
| RAG 检索噪声大 | 历史案例干扰决策 | 设置相似度阈值，初期 RAG 结果仅作参考，不影响 Hard Gate |
| 多 Agent 调用成本高 | Token 消耗大 | 代码能做的不用 LLM；Orchestrator 用 Haiku；按需调用 |
| Playbook 匹配代码化后丧失灵活性 | 无法处理边界情况 | Hard Gate 用代码，边界判断仍交给 LLM Agent |
| daily_stock_analysis 与本项目技术栈不同（Python vs TS） | 集成复杂度 | 通过 HTTP API 解耦，DSA 作为独立服务运行 |
