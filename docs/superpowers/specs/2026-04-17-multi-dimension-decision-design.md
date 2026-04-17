# 多维度决策增强设计文档（Draft v1）

> 状态：Draft v1 — 待 review | 作者：wei.he + Claude | 日期：2026-04-17
>
> 在纯技术分析（K 线 / 结构 / 形态 / 指标）基础上，新增**基本面 / 舆情 / 财务**三条线，
> 并定义"多维度信息如何综合成一次交易决策"的判断逻辑。
>
> 本方案与 `2026-04-17-skill-optimization.md`（内部 bug 修复）正交，假设那份先行落地。

---

## 0. TL;DR

- 采用 **"风格分层（C）+ 硬否决（A）"** 组合：按持仓周期分 4 层（日内 / 短线 / 波段 / 中长线），每层用不同的维度组合与权重；**事件 / 财务塌方 / 舆情暴雷**作为所有层的一票否决。
- 技术面依然是**触发器**（决定"什么时候进"），其他维度是**过滤器 / 加权器**（决定"要不要进、进多大"）。
- 新增 3 个 data-acquisition 子流程、1 个新 workflow（`multi-dimension-context.md`）、1 份决策逻辑升级（`trading-decision.md` 8.x → 9.x）、snapshot schema 向后兼容扩展。
- 分 4 个迭代（M1~M4）上线，M1 只做"事件/财报倒计时"硬否决这一个最高 ROI 的切口，不要求一次做完。

---

## 1. 背景与现状

### 1.1 当前 Skill 的能力边界

- **100% 技术面驱动**：结构判断（BOS/CHoCH）→ 关键位 → 形态 → 指标背离 → Playbook 匹配 → Checklist → 仓位。
- **Checklist 已预留一个软口子**：`pre-trade-checklist` 第 6 项"事件与宏观"——但只是一句话描述，没有数据源、没有取数流程、没有判断规则。
- **信号归档机制成熟**：`snapshot.json + report.md + index.jsonl` 已被 backtest 和 dashboard 消费，schema 改动需向后兼容。

### 1.2 暴露的问题（为什么要做）

| 场景 | 纯技术分析的盲区 |
|---|---|
| 财报前 2 天建仓做多，财报跳空低开 | 技术面完全看不见"财报日"这个最大变量 |
| 某币圈项目技术形态完美，但基金会被查、TVL 连续下滑 | 缺舆情 + 链上基本面 |
| A 股某标的突破放量，但当季毛利率暴跌、应收账款激增 | 缺财务健康度 |
| 大盘风险偏好塌方（VIX 暴涨 / 恐贪指数<20），个股图形还是漂亮的 | 缺宏观舆情 |
| 社交媒体集中唱多后 3 天，价格往往见顶 | 缺情绪反向指标 |

### 1.3 非目标

- 不做**选股 / 选币**：本 Skill 是"拿到标的后怎么决策"，不是"去哪找标的"。
- 不做**量化因子**：没有回测多因子模型的能力，也不是本 Skill 的定位。
- 不做**自动执行**：依旧输出决策建议，不触发下单。
- 不承诺**实时性**：舆情/财务/基本面数据可以有小时级甚至天级延迟，在 report 里明确标注时效。

---

## 2. 核心架构决策

### 2.1 方案选择：C + A 组合

经过 4 选项对比（见 brainstorming 记录），最终选择：

- **C. 风格分层**——按持仓周期决定每个维度的权重
- **A. 硬门槛否决**——新增 4 项一票否决规则，跨所有风格

**为什么不是 B（加权融合）？**

加权评分的问题是"一个好技术信号 + 一个差基本面 = 中等总分 → 做"，但真实交易里这两者是**非对称**的——基本面崩塌时，技术信号的失败率非线性飙升。硬否决 + 分层 + 背景信息更贴近人工决策逻辑。

**为什么不是 D（只展示不决策）？**

太懦弱，本质上没解决用户说的"决策逻辑"问题。既然新增了三条线，就必须进入决策闭环。

### 2.2 关键原则

1. **触发与过滤分离**：技术面负责触发（"可以进"），其他维度负责过滤（"能不能进"）。
2. **维度间 AND，不是 OR**：任一硬否决命中 → 直接观望；多维度"提示"则综合打分降仓。
3. **缺数据 ≠ 失败**：任何一条线没数据时，降级为"数据不可用"标签，**不阻断交易**，但在 report 显式写明并降一档信心。
4. **按风格区分默认强度**：日内几乎不看基本面，中长线几乎不看 5m 结构，模板不能一刀切。
5. **决策可解释**：每个维度结论必须写清"来源 + 时效 + 置信度"，不要黑盒分数。

---

## 3. 架构总览

### 3.1 分层模型

```
                   ┌──────────────────────────────────┐
                   │      交易风格识别（新增）          │
                   │  日内 / 短线 / 波段 / 中长线        │
                   └──────────────┬───────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  技术面（已有）  │    │  新增三维度      │    │  硬否决规则      │
│  chart-analysis │    │  ─ 基本面         │    │  ─ 事件日        │
│  Step 0~7       │    │  ─ 舆情/情绪      │    │  ─ 财务塌方      │
│  (触发)          │    │  ─ 财务           │    │  ─ 监管黑天鹅    │
│                 │    │  (过滤 + 加权)   │    │  ─ 舆情暴雷      │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │   综合决策（升级 8.x → 9.x）  │
                  │   ─ 硬否决先跑                 │
                  │   ─ 分层加权得"置信修正"        │
                  │   ─ 置信修正回写 Playbook 仓位 │
                  └──────────────────────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │   信号归档（schema 扩展）      │
                  │   snapshot.json 新增 context 段 │
                  └──────────────────────────────┘
```

### 3.2 目录新增

```
workflows/
  multi-dimension-context.md     ← 新增：三维度取数 + 判断流程
  event-calendar.md              ← 新增：事件日历（财报/解禁/经济数据）的取数与否决规则

references/
  context/                       ← 新增目录
    INDEX.md
    fundamentals-equity.md       ← A 股 / 美股基本面判断规则
    fundamentals-crypto.md       ← 链上 + tokenomics
    financials-equity.md         ← 财务指标阈值与评分
    sentiment-social.md          ← 社交 / 搜索 / 恐贪指数
    sentiment-market.md          ← 宏观风险情绪（VIX / 资金费率 / 北向资金）
    hard-veto-rules.md           ← 硬否决条目集中管理

  checklists/
    pre-trade-checklist.md       ← 已有，追加第 8~12 项新维度
    context-health-check.md      ← 新增：风格识别后的分层检查表

strategies/                       ← 不需要改结构，仅在 _defaults.yaml 增加 style_gates 段
```

---

## 4. 新增数据维度规格

### 4.1 基本面（Fundamentals）

| 市场 | 数据内容 | 数据源候选 |
|------|---------|-----------|
| A 股 | 行业景气 / 公司业务定性 / 同业比较 / 产品管线 | AKShare 行业数据、东财公告、券商研报摘要 |
| 美股 | 行业地位 / 护城河 / 管理层 / 产品线 | 用户手工输入 + 可选 MCP 接入 Finnhub/Yahoo |
| 币圈 | tokenomics（流通/解锁）/ TVL / 生态活跃度 / 团队背景 | DefiLlama、链上 RPC、CoinGecko metadata |

**判断粒度**（避免陷入无底洞）：只打 3 档标签 `健康 / 中性 / 恶化`，配 1 句理由。**不做 DCF/估值**。

### 4.2 舆情（Sentiment）

分 2 层：

**A. 个股/币种舆情**
- A 股：东财/雪球讨论热度、研报情绪、龙虎榜
- 美股：Twitter / Reddit 讨论量（StockTwits / WSB），大 V 点名
- 币圈：LunarCrush / Santiment / Twitter 热度、KOL 点名

**B. 市场情绪（宏观）**
- 共用：VIX、恐惧贪婪指数、美元指数、Put/Call Ratio
- A 股加：北向资金、两融余额、涨停板数量
- 币圈加：BTC.D、资金费率、永续 OI、长短仓比

**输出粒度**：`极度恐慌 / 恐慌 / 中性 / 贪婪 / 极度贪婪` 五档 + 趋势箭头（上升/下降/持平）。

### 4.3 财务（Financials，仅股票）

分 4 个维度做**量化评分**（和基本面的定性不同）：

| 维度 | 核心指标 | 健康阈值（参考，跨行业需对齐行业均值） |
|------|---------|-----------------------------------|
| 盈利 | ROE、毛利率、净利率、净利润同比 | ROE > 10%、毛利率稳定/上升 |
| 成长 | 营收同比、净利润同比、扣非同比 | 连续 3 个季度 > 0 |
| 现金流 | 经营性现金流/净利润、自由现金流 | 比值 > 0.8 且为正 |
| 杠杆 | 资产负债率、流动比率、速动比率 | 负债率 < 行业均值、流动比 > 1 |

**产出**：4 档评分（优秀 / 健康 / 一般 / 风险），跨维度**短板决定下限**（任一维度"风险" → 整体"风险"）。

**数据源**：AKShare（`stock_financial_abstract`、`stock_financial_report_sina`）、用户手工补充。

### 4.4 事件日历（独立子系统）

- 财报日（3 日窗口：财报前 2 日 + 财报当日 + 财报后 1 日）
- 经济数据日（CPI / 非农 / 利率决议）
- 行业重大事件（解禁、分红、ETF 审批、硬分叉）
- 监管事件（SEC 诉讼、交易所暂停、政策出台）

**这是最高 ROI 的一块**——M1 里单独实现，因为纯粹的"何时不做交易"规则就能让胜率显著提升。

---

## 5. 决策逻辑（核心章节）

> 这是用户最关心的部分：拿到这些信息后，怎么做判断。

### 5.1 风格识别（新增 Step）

在 chart-analysis Step 0 后插入 **Step 0.3 风格识别**：

| 判据 | 风格 |
|---|---|
| 周期模板以 ≤15m 为主 + 用户明示日内 | `intraday` |
| 周期模板 1H ~ 4H，用户想"持有几天" | `swing` |
| 周期模板 1D ~ 1W，持有 2 周~数月 | `position` |
| 周期模板含 1M，或用户提"价值/长期" | `long-term` |
| 模糊 | 按周期默认：A 股 → swing，币圈 → swing/intraday |

### 5.2 各风格维度权重矩阵

事件日历**不在权重矩阵里**——它走 5.3 Step 9.1 硬否决通道。下表只列进入"置信修正"的 5 个维度，每行权重合计 100%。

```
                  技术   基本面  财务   舆情(个股)  舆情(市场)
intraday          75%    0%      0%     10%         15%
swing             55%    10%     5%     20%         10%
position          40%    25%     20%    10%         5%
long-term         20%    40%     35%    0%          5%
```

**读法**：
- `intraday` 几乎全靠技术面 + 市场情绪，基本面/财务置 0。
- `long-term` 技术面降到 20%，基本面 + 财务合计 75%——这时候技术面仅做择时微调。
- 权重只影响"置信修正"算法（见 5.3 Step D），不是对各维度做加权求和打总分。

### 5.3 决策步骤（trading-decision.md 9.x）

执行顺序严格串行：

#### 9.1 硬否决先跑（Hard Veto）

任一命中 → 输出"不做，理由：xxx" → 不再进入后续决策。

| 否决条目 | 规则 | 数据源 |
|---------|------|--------|
| 财报倒计时 | T-2 ~ T+1 日窗口内禁止建仓（reduce-only 例外） | 事件日历 |
| 重大监管事件 | 48h 内出现监管利空（SEC 诉讼、交易所下架） | 舆情 + 新闻 |
| 财务红线 | 财务评分 = 风险（仅 position / long-term 触发） | 财务模块 |
| 舆情暴雷 | 个股舆情 24h 内出现明确造假 / 退市警示 / 团队跑路 | 个股舆情 |
| 宏观极端风险 | VIX > 40，或 BTC 恐贪 < 10，或大盘单日跌 > 3% | 市场舆情 |

> 硬否决规则的完整条目存在 `references/context/hard-veto-rules.md`，这里只列最高频 5 条。

#### 9.2 维度评估（Context Assessment）

对当前风格要求的维度，逐个产出**评估卡**：

```yaml
基本面:
  评级: 健康 / 中性 / 恶化 / 数据不可用
  要点: 一句话结论
  置信: 高 / 中 / 低
  时效: 截至 YYYY-MM-DD

财务:
  总评: 优秀 / 健康 / 一般 / 风险 / 数据不可用
  短板: 现金流（经营现金流/净利润 = 0.3，低于 0.8 阈值）
  时效: 2026 Q4 报

个股舆情:
  情绪: 极度贪婪 / 贪婪 / 中性 / 恐慌 / 极度恐慌
  方向: 上升 / 下降 / 持平
  异常: 无 / 突然爆量讨论 / 反向信号

市场舆情:
  VIX: 18.3（中性）
  恐贪: 62（贪婪）
  资金费率: 0.02%（中性，币圈专用）
```

#### 9.3 置信修正（核心决策算法）

把技术面原本给出的**信心等级**做修正：

**Step A：基准分 = 技术面信心（高=3 / 中=2 / 低=1）**

**Step B：对每个维度，按该风格权重算"修正票"**
- 评级"健康/优秀/贪婪向上/支持技术方向" → +1 票（带权重）
- 评级"中性" → 0
- 评级"恶化/风险/反向情绪/极端恐慌" → -1 票（带权重）
- 评级"数据不可用" → 算 -0.5 票（保守策略）

**Step C：加权求和 → 修正量**

```
修正量 = Σ（维度票 × 风格权重）
        范围 -1 ~ +1

修正后信心 = clamp(基准 + 修正量, 0, 3)
```

**Step D：把"修正后信心"映射回操作**

| 修正后信心 | 操作 |
|---|---|
| ≥ 2.5 | 按正常仓位（1~2%）执行 |
| 1.5 ~ 2.5 | 降仓（0.5~1%） |
| 0.5 ~ 1.5 | 只给观察建议，不建仓 |
| < 0.5 | 放弃该信号 |

#### 9.4 冲突显式化（可解释性）

在 report 里**强制**输出一段"冲突说明"（即便没冲突也要写"无冲突"）：

```
置信修正明细：
  基准（技术面）: 中 (2)
  + 基本面 健康 (+1 × 0.10) = +0.10
  + 财务   一般 (-0.3 × 0.05) = -0.015
  + 个股舆情 恐慌 (-1 × 0.15) = -0.15
  + 市场舆情 中性 (0 × 0.10) = 0
  合计修正: -0.065
修正后信心: 1.935 → 降仓执行（0.75%）
冲突点: 个股舆情转弱，与技术面多头触发方向冲突；
        但权重较低（15%），未触发否决。
```

### 5.4 与现有 8.x 的衔接

- `8.1 前置检查`不变，硬性门槛（价格刻度、信号强度、混乱状态、多周期冲突）全部保留。
- `8.2 Playbook 匹配`不变。
- `8.3 入场前检查`追加 8~12 项：基本面 / 财务 / 个股舆情 / 市场舆情 / 事件日历。
- `8.4 仓位风控`接受"修正后信心"作为额外降仓乘数。
- 新增 `9.x 多维度决策` 在 8.x 全部通过后运行（8.x 不通过时根本进不到 9.x）。

### 5.5 伪代码

```
def decide(symbol, style, tech_result):
    # 0. 硬否决
    veto = check_hard_veto(symbol, style)
    if veto.hit:
        return Decision(action="观望", reason=veto.reason)

    # 1. 技术面未通过，不进入多维度
    if tech_result.signal_strength == "弱":
        return Decision(action="观察", reason="技术信号弱")

    # 2. 风格化维度评估
    ctx = assess_context(symbol, style)
    # ctx = { fundamentals, financials, sentiment_asset, sentiment_market }

    # 3. 置信修正
    base = {"高": 3, "中": 2, "低": 1}[tech_result.confidence]
    weights = STYLE_WEIGHTS[style]
    delta = sum(
        dimension_vote(ctx[d]) * weights[d]
        for d in ctx
    )
    adjusted = clamp(base + delta, 0, 3)

    # 4. 映射仓位
    size_multiplier = confidence_to_size(adjusted)
    return Decision(
        action="做" if adjusted >= 1.5 else "观察",
        base_risk=1% * size_multiplier,
        confidence_adjusted=adjusted,
        breakdown=build_explanation(tech_result, ctx, weights, delta),
    )
```

---

## 6. 信号 Schema 演进（向后兼容）

### 6.1 当前 schema（简化）

```json
{
  "signal_id": "BTCUSDT_20260417_103000",
  "symbol": "BTCUSDT",
  "direction": "long",
  "playbook": "trend-pullback",
  "confidence": "中",
  "entry": 62300,
  "stop": 61500,
  "targets": [63800, 65200],
  "timeframe_status": {...}
}
```

### 6.2 扩展后 schema

```json
{
  // 原字段全部保留，向后兼容
  "signal_id": "...",
  "confidence": "中",                // 技术面原始信心

  // 新增字段（可选，老代码不读就忽略）
  "style": "swing",
  "context": {
    "fundamentals": { "rating": "健康", "note": "...", "asof": "..." },
    "financials": { "total": "健康", "weak_point": "...", "quarter": "..." },
    "sentiment_asset": { "level": "中性", "trend": "持平" },
    "sentiment_market": { "vix": 18.3, "fear_greed": 62 },
    "events": { "nearest": "earnings", "days_to": 7 }
  },
  "hard_veto": { "hit": false, "checked": ["event", "regulation", "financial", "sentiment_spike", "macro"] },
  "confidence_adjusted": 1.935,
  "confidence_breakdown": [...],     // 结构化的 Step D 明细
  "size_multiplier": 0.5
}
```

### 6.3 兼容性影响

- `stock-skill-backtest`：回测引擎只读原字段 → 无感知，继续跑。后续升级可读 `confidence_adjusted` 做更精细回测。
- `stock-dashboard`：展示层可逐步加卡片展示 `context` 段，老信号缺字段时显示"—"。
- `index.jsonl`：追加 `style`、`confidence_adjusted`、`hard_veto.hit` 三个字段方便筛选。

---

## 7. 迭代路线图

严格按 ROI 排序，**每个 milestone 独立可交付**，不要求一次做完：

### M1（最高 ROI）：事件日历硬否决 🔥

**范围**：只做"财报倒计时"和"监管重大事件"两个硬否决。
**原因**：这俩是"纯粹避坑"，不涉及任何主观判断，规则简单，但立即减少最常见的踩雷类型。
**交付**：
- `workflows/event-calendar.md`
- `references/context/hard-veto-rules.md` 初版
- `trading-decision.md` 追加 9.1 硬否决段
- snapshot 扩展 `hard_veto` + `events` 字段
**预估工作量**：1~2 天

### M2：市场舆情（宏观风险过滤）

**范围**：VIX / 恐贪指数 / 资金费率 / 北向资金；只做"极端档位触发观望或降仓"。
**原因**：数据源公开易得，对所有标的一视同仁，是全局过滤器。
**交付**：
- `references/context/sentiment-market.md`
- `data-acquisition-workflow.md` 新增市场情绪子流程
- Step 9.2~9.3 初版（只含市场舆情维度）
**预估工作量**：2~3 天

### M3：风格分层 + 财务评分

**范围**：实现 swing 以上风格的财务评分（position / long-term），Step 9 全量决策算法上线。
**原因**：财务数据 A 股 AKShare 完备，美股可用性 OK，量化阈值明确。
**交付**：
- `references/context/financials-equity.md`
- `data-acquisition-workflow.md` 新增财报子流程
- `trading-decision.md` 完整 9.x
- snapshot 扩展 `context.financials` + `confidence_breakdown`
**预估工作量**：3~5 天

### M4：基本面 + 个股舆情（弹性块）

**范围**：
- 基本面 3 档标签（最大不确定性的一块）
- 个股舆情（数据源挑战最大）
**原因**：主观度高、数据源贵或不稳定，放最后做，且允许"数据不可用"降级。
**交付**：
- `references/context/fundamentals-equity.md`、`fundamentals-crypto.md`
- `references/context/sentiment-social.md`
- 完整 `multi-dimension-context.md` workflow
**预估工作量**：5~7 天

---

## 8. 风险与开放问题

### 8.1 数据源不稳定

- 舆情数据源（LunarCrush / StockTwits）可能限流 / 收费 / 结构变化。
- **缓解**：每个维度都设计 "数据不可用" 降级分支；M4 延后；允许用户手工填。

### 8.2 权重调参缺回测

- 5.2 的权重矩阵是直觉设定，没有回测验证。
- **缓解**：snapshot 同时保留"修正前"和"修正后"信心，`stock-skill-backtest` 上线多维度回测后再调。
- **开放问题**：是否要在 `strategies/_defaults.yaml` 允许用户 override 权重？

### 8.3 硬否决过于保守

- 财报 3 日窗口可能让趋势策略错过"财报后暴涨"。
- **缓解**：在 `hard-veto-rules.md` 明确标注"建仓禁止 vs 持仓减仓 vs 完全不动"的差异化规则，reduce-only 不受影响。

### 8.4 跨市场定义不一致

- "基本面健康" 对 A 股、美股、币圈的含义差异巨大。
- **缓解**：`references/context/fundamentals-{equity,crypto}.md` 分开写，`overview.md` 不做统一定义。

### 8.5 舆情噪音

- 社交媒体舆情极容易被带节奏，反向指标比顺向更可靠。
- **开放问题**：个股舆情"极度贪婪"是否应该直接翻转为**负面票**（类似反向指标）？M4 时需要根据少量样本确认。

### 8.6 与现有 skill-optimization 方案的交互

- `2026-04-17-skill-optimization.md` 正在修 5 个 Playbook 中的 2 个 Playbook 缺失文档等 bug。
- **约定**：本方案假设那份先落地，9.x 基于修好后的 8.x 增量。

---

## 9. 验收标准

M1 上线后至少要满足：

- [ ] `signal_id` 为财报前 2 日建仓的场景 → 100% 命中硬否决
- [ ] snapshot 里 `hard_veto.hit=true` 时 report.md 顶部有"⛔ 硬否决"醒目段
- [ ] dashboard 读老信号（无 `hard_veto` 字段）不报错
- [ ] backtest 读老信号不报错

M3 上线后额外要满足：

- [ ] 所有 swing 及以上风格的信号 `confidence_adjusted` 字段非空
- [ ] `confidence_breakdown` 逐项可读、可追溯
- [ ] 有冲突的信号 report.md 必须有"冲突说明"段

---

## 10. 下一步

1. **用户 review 本文档**（尤其第 2 节架构选择、第 5 节决策逻辑、第 7 节迭代顺序）
2. Review 通过后 → 调用 `superpowers:writing-plans` 生成 M1 的落地实施计划
3. M1 落地 → 在 `~/.trading-data/` 上跑 2~4 周观察 → 根据数据决定 M2 起步时机

---

## 附录 A：与 brainstorming 过程的对应

- 选项 A（硬门槛）→ 第 5.1 节（硬否决）
- 选项 B（加权融合）→ 放弃，理由见 2.1
- 选项 C（风格分层）→ 第 5.1~5.3 节（分层权重矩阵）
- 选项 D（只展示不决策）→ 放弃，理由见 2.1

## 附录 B：本方案不改动的东西

- `chart-analysis-workflow.md` Step 0~7（技术面分析完全不动）
- 5 个 Playbook 定义（仍是触发条件 + 止损 + 目标的原结构）
- 仓位公式（`仓位 = 风险金额 / 止损距离`）
- 信号归档路径与文件名规则
- A 股 / 币圈默认周期模板
