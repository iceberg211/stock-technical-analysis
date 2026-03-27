# 回测报告 (summary.md) 优化方案

当前的回测报告 ([eval/report.py](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/report.py) 生成) 存在以下问题：
1. **过多中间状态数据**：给人类看时不应该罗列 `missed_entry`, `t1_hit`, `t2_hit`, `sl_hit`, `neither` 等机械计数，这让表格变得非常宽且难以抓住重点。
2. **缺乏核心 KPI**：业界看策略首先看 **Win Rate (胜率)**、**Profit Factor (盈亏比/利润因子)** 和 **Expected Value (单笔期望 R 值)**，当前报告只有胜率。
3. **冗余工程信息**：“与 output-templates.md 的对应关系”这类开发调试信息不应占据报告篇幅。

---

## 业界最佳实践 (Tearsheet 风格)

专业量化框架（如 QuantConnect, Backtrader）的回测报告都遵循 **"由总到分，先 KPI 后明细"** 的原则。

我建议将报告重构为以下三个清晰的层级：

### 1. 核心业务指标 (Executive Summary)
用最简短的文字或微型表格展示全局表现。
* **回测样本覆盖**: 总 Case 数 / 实际触发交易数 
* **全局胜率 (Win Rate)**: %
* **平均每笔实现 R (Average Realized R)**: 每做一笔交易，平均净赚多少 R。（这是评判策略是否赚钱的唯一真理）
* *(可选)* 计算最大的回撤阶段或总盈利 R。

### 2. 策略表现明细 (Strategy Breakdown)
将目前的 `Playbook 胜率` 升级为核心表格，隐藏所有繁琐的中间计数字段，只保留投资人关心的字段：

| Playbook | 识别次数 | 执行次数 | 胜率 | 平均预估回报 (Avg RR) | 平均实现回报 (Avg Realized R) |
|----------|---------|---------|------|--------------------|----------------------------|
| 顺势回调 | 10 | 8 | 65% | 1.8R | +0.45R |
| 突破回踩 | 5 | 3 |  33% | 2.0R | -0.10R |

*人类只需要看最后两列：预估好不好？实际赚不赚 (Realized R)？*

### 3. AI 稳定性监控 (AI Diagnostics)
把 AI 特有的监控降级到报告的后半部分：
* **信心校准 (Confidence Calibration)**：简化为 `Confidence | 执行次数 | 胜率 | 平均实现 R`。取消繁杂的具体 hit 计数。
* **一致性率 (Consistency)**：结构保留，仅在有多次 Run 时展示，折叠或简化显示，避免刷屏。

### 4. 移除或降级无用数据
* **移除“与 output-templates.md 的对应关系”**（或将其写入单独的 `.log` 文件中）。
* **整合 `neither` 和 `missed_entry` 概念**：只在总览里提一句“X 次未触发入场，Y 次未到止盈止损自动平仓”，不需要在每个表格里都占据一列。

---

## Part 2: 数据目录 (data/) 架构重组方案

### 当前结构分析
您目前的结构为 `data/{数据源_kline}/{SYMBOL}/{频次}_{状态}.csv`（例如 [data/binance_kline/BTCUSDT/kline_1h.csv](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/data/binance_kline/BTCUSDT/kline_1h.csv) 与 `kline_1h_indicators.csv` 混放）。
这在初期能跑通，但**混合了“原始数据 (Raw)”与“特征工程 (Features/Indicators)”**，且 `binance/mcp/opend` 级别划分有点像平铺，当标的增多时容易混乱。

### 业界最佳实践 (Feature Store 模式)
在 QuantConnect、Freqtrade 或工业界量化团队中，主流是将**贴源层数据 (Raw Data)** 和**特征层数据 (Feature Store)** 物理隔离：

```text
data/
├── raw/                         # 纯净的 OHLCV 贴源数据（不可篡改）
│   ├── binance/                 # 按交易所 / 数据源分类
│   │   └── BTCUSDT/
│   │       ├── 1h.csv
│   │       └── 4h.csv
│   └── mcp/
│       └── BTCUSDT/
└── features/                    # 附加了技术指标 (MA/RSI等) 或清洗后 (clean) 的回测输入
    └── BTCUSDT/
        ├── 1h_basic_indicators.csv  # 对应之前的 kline_1h_indicators.csv
        └── 1h_mcp_merged.csv        # 对应之前的 merged/clean 版本
```

### 兼容历史回测的平滑升级策略 (Backward Compatibility)
为了绝对保证**“优化后依然能利用之前的分析数据（`eval/results/` 下的数据历史报告）”**，我们采用以下策略：

1. **配置驱动 (Config-Driven) 机制**
   当前 `eval/score_eval.py` 在计算旧报告时，是**通过读取 `eval/results/*/config.json` 中的 `csv_path` 字段**来回溯 K 线的。只要我们保证这个路径能找到文件，历史评估报告就永远不会失效。

2. **迁移工具 (Migration Script)**
   我们提供一个统一的 `scripts/migrate_data_v2.py`。当你准备好升级时运行它：
   - 步骤一：按业界标准创建 `raw/` 和 `features/` 目录。
   - 步骤二：自动将所有现有的 `.csv` 移动/重命名到对应的新 V2 目录标准中。
   - **步骤三（最关键）：自动扫描所有 `eval/results/` 下的 `config.json`，将其内部的 `csv_path` 指向新位置**。

**结论**：使用 Migration Script 统一转换，历史的回测得分（`scored.jsonl`）一字不改全额保留，事后重新生成 `.md` 报告也丝毫不受影响。

---

## 最终执行计划

如您认可上述综合方案，我们可以分**两步走**：
1. **先改计分板**：立即重构 `eval/report.py`，因为这完全不影响底层数据，能立刻让您看到漂亮、聚焦核心业务逻辑的回测总结表（引入 `Realized R` 和 EV 等指标）。
2. **再搞搬家工具**：编写 `migrate_data_v2.py` 清洗数据目录层级并升级老配置，完成彻底的量化架构标准化转换。
