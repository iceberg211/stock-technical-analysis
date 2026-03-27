# 项目结构重构设计 — Medallion Architecture

> 状态：Draft → 待确认
> 日期：2026-03-27

## 1. 问题总结

### 输入侧（data/）

- **同一份 BTCUSDT 1h K 线数据存了 7 个文件**：`kline_1h.csv`, `kline_1h_latest.csv`, `kline_1h_accum.csv`, `kline_1h_accum_indicators.csv`, `kline_1h_indicators.csv`, 加 2 个 `live_*/` 快照副本。
- **3 个数据源目录做同一件事**：`opend_kline/`(36行), `mcp_kline/`(204行), `binance_kline/`(8761行) 都是 BTCUSDT。
- **列名不统一**：opend 用 `time`，其余用 `timestamp`。
- **live_* 快照目录无限增长**，无清理策略。
- **36 个数据文件被 git 追踪**，行情数据本应 .gitignore。

### 输出侧（outputs/）

- **human/machine/data/debug 四层嵌套过度设计**：实际每个 symbol 只有 6-8 个文件。
- **manifest.json 写死绝对路径**：`"/Users/hewei/..."` 换机器全废。
- **现有 3 次回测的 runs.jsonl 全是 0 行**：没有产生有效交易记录。
- **模型分析信号（核心资产）散落在 data/binance_kline/BTCUSDT/ 中**：`analysis_skill_snapshot.json` + `analysis_skill_report.md` 没有纳入统一管理。

### 最严重的问题：对话式分析信号丢失

用户日常工作流是**在对话中**让 Claude 拉取 K 线并分析，而非通过 pipeline 脚本。每次分析都会覆盖同一个 `analysis_skill_snapshot.json`，导致**历史分析信号全部丢失**——只保留了最后一次。

更关键的是：**"观望"（watch）结论同样包含完整的点位数据**（条件入场价、止损、目标、市场结构、背离信号），这些都是可回测的信号，但目前全被覆盖丢弃。

### 代码侧

- `eval/` 作为包名与 Python 内置 `eval()` 冲突。
- `reanalyze_with_opend.py` 自建 `runs/`+`logs/` 子目录，与 pipeline layout 脱节。
- `DataSource` 按优先级搜 3 个目录本质是给混乱打补丁。

---

## 2. 核心资产定义

在动手之前，明确什么是**必须保留、不可重新生成**的核心资产：

| 资产 | 当前位置 | 说明 |
|---|---|---|
| **模型分析信号** | `data/binance_kline/BTCUSDT/analysis_skill_snapshot.json` | AI 模型输出的点位、结构、背离等信号 |
| **分析报告** | `data/binance_kline/BTCUSDT/analysis_skill_report.md` | 人可读的完整分析 |
| **累积 K 线** | `data/binance_kline/BTCUSDT/kline_{1h,4h}_accum.csv` | 8760+ 行，一年的历史数据 |

**可重新生成（可删）**：
- `kline_*_indicators.csv` — 指标列可重算
- `kline_*_latest.csv` — 是 accum 的副本
- `kline_*_indicators_summary.json` — 可重算
- `live_*` 快照目录 — 完整副本
- `opend_kline/`, `mcp_kline/` — binance_kline 的 accum 已包含全部数据

---

## 3. 目标目录结构

```
stock-technical-analysis/
│
├── src/                              ← 所有 Python 代码（原 eval/ + scripts/）
│   ├── __init__.py
│   ├── indicators/                   ← 技术指标计算（唯一来源）
│   │   ├── __init__.py
│   │   └── calc.py                   ← 原 indicator_calc.py
│   ├── pipeline/                     ← 编排 + 数据管理
│   │   ├── __init__.py
│   │   ├── cli.py                    ← CLI 参数解析
│   │   ├── layout.py                 ← 目录结构定义
│   │   ├── ingest.py                 ← 数据摄入（拉取 → raw → clean）
│   │   ├── catalog.py                ← 数据目录索引管理
│   │   ├── manifest.py               ← 运行清单 + 全局注册表
│   │   ├── backtest.py               ← 回测执行
│   │   ├── analyze.py                ← 本地规则引擎
│   │   └── retention.py              ← 产物清理策略
│   ├── scoring/                      ← 评分引擎
│   │   ├── __init__.py
│   │   ├── engine.py                 ← 原 score_eval.py
│   │   └── validator.py              ← backtest_sample 校验
│   ├── reporting/                    ← 报告生成
│   │   ├── __init__.py
│   │   ├── metrics.py                ← 指标聚合
│   │   ├── markdown.py               ← Markdown 渲染
│   │   └── templates.py              ← 报告模板
│   ├── prompt/                       ← LLM prompt 构建
│   │   ├── __init__.py
│   │   └── builder.py                ← 原 prompt_builder.py
│   └── config.py                     ← 全局配置常量
│
├── data/                             ← 行情数据（.gitignore，catalog.json 除外）
│   ├── catalog.json                  ← 数据目录索引（唯一入 git）
│   ├── raw/                          ← 层 1：原始 API 响应
│   │   └── {exchange}/               ← binance / futu / yahoo
│   │       └── {symbol}/
│   │           └── {interval}/
│   │               └── {YYYYMMDD_HHMMSS}.json
│   └── clean/                        ← 层 2：标准化后的唯一真相
│       └── {symbol}/
│           └── {interval}.parquet    ← 统一列：timestamp,open,high,low,close,volume
│
├── outputs/                          ← 回测 + 分析产物（.gitignore）
│   ├── signals/                      ← ★ 模型分析信号（核心资产）
│   │   └── {symbol}/
│   │       └── {YYYYMMDD_HHMMSS}/
│   │           ├── snapshot.json     ← 结构化点位数据
│   │           └── report.md         ← 人可读分析报告
│   ├── runs/                         ← 回测运行产物
│   │   └── {run_id}/
│   │       ├── manifest.json         ← 批次清单（相对路径）
│   │       └── {symbol}/
│   │           ├── config.json       ← 运行配置（可复现）
│   │           ├── input.parquet     ← 本次用的数据切片（自包含）
│   │           ├── runs.jsonl        ← 原始运行记录
│   │           ├── scored.jsonl      ← 评分结果
│   │           ├── metrics.json      ← 统计指标
│   │           ├── summary.md        ← 人可读总结
│   │           └── details.md        ← 人可读明细
│   └── registry.jsonl                ← 全局运行索引
│
├── tests/                            ← 测试（原 eval/tests/）
│   └── test_scoring.py
│
├── workflows/                        ← Skill prompt 模板（保持不变）
├── references/                       ← 知识库（保持不变）
├── docs/                             ← 文档
└── agents/                           ← Mastra agent 定义（保持不变）
```

---

## 4. 设计决策详解

### 4.1 数据层：Medallion Architecture

```
拉取脚本 → raw/{exchange}/{symbol}/{interval}/{timestamp}.json
               ↓  ingest 步骤（标准化 + 去重 + 追加）
           clean/{symbol}/{interval}.parquet
```

**规则：**
- `raw/` 保留最近 7 天，自动过期。原始 JSON 不做任何处理，保持 API 原始响应。
- `clean/` 是唯一真相。所有消费方（回测、指标计算、分析）只从这里读。
- 用 **Parquet** 格式：体积约 CSV 的 1/5，保留列类型，读取快。
- `catalog.json` 记录每个 symbol 的可用数据范围和最后更新时间。

**对比现状的改进：**
- 消灭 `opend_kline/`, `binance_kline/`, `mcp_kline/` 三个冗余目录
- 消灭 `_accum`, `_latest`, `_indicators`, `live_*` 等 7 种副本
- 不同数据源（Binance/富途/yfinance）统一走 ingest 写入 clean/
- indicators 不再存文件，运行时按需计算

### 4.2 信号层：模型输出是第一等公民

```
outputs/signals/{symbol}/{YYYYMMDD_HHMMSS}/
├── snapshot.json     ← 结构化信号（entry/stop/targets/structure/divergence）
└── report.md         ← 人可读分析
```

**这是全项目最重要的资产。** 不再散落在 `data/binance_kline/` 里。

**索引方式：** `outputs/signals/{symbol}/` 目录下按时间戳排列，天然有序。后续可加 `index.jsonl` 做快速查询。

### 4.3 回测层：扁平化 + 自包含

**现状：** `human/machine/data/debug` 四层嵌套，6 个文件分散在 4 个子目录。

**改为：** 扁平结构，所有文件直接放在 `{symbol}/` 下。

```
outputs/runs/{run_id}/{symbol}/
├── config.json       ← 运行配置
├── input.parquet     ← 本次用的数据切片（自包含，可复现）
├── runs.jsonl        ← 运行记录
├── scored.jsonl      ← 评分结果
├── metrics.json      ← 统计指标
├── summary.md        ← 回测总结报告
└── details.md        ← 回测明细报告
```

**关键改进：**
- `input.parquet` 把本次用的数据保存下来，即使 `data/clean/` 数据更新或清空，历史回测仍可审计和复现。
- `manifest.json` 只用**相对路径**（`"BTCUSDT/"` 而非 `"/Users/hewei/.../BTCUSDT"`）。
- 不需要 `debug/cases/` — 如果需要逐 case 审计，在 `details.md` 里展开即可。

### 4.4 代码层：`eval/` → `src/`，按职责分包

| 原文件 | 新位置 | 说明 |
|---|---|---|
| `eval/indicator_calc.py` | `src/indicators/calc.py` | 唯一指标来源 |
| `eval/pipeline/*.py` | `src/pipeline/*.py` | 编排逻辑 |
| `eval/score_eval.py` | `src/scoring/engine.py` | 评分引擎 |
| `eval/run_eval.py` | `src/scoring/validator.py` + `src/pipeline/backtest.py` | 拆分：校验逻辑 vs 执行逻辑 |
| `eval/report.py` | `src/reporting/metrics.py` + `src/reporting/markdown.py` | 拆分：计算 vs 渲染 |
| `eval/prompt_builder.py` | `src/prompt/builder.py` | prompt 构建 |
| `eval/config.py` | `src/config.py` | 配置 |
| `eval/generate_sample_data.py` | `src/pipeline/ingest.py` | 合并到数据摄入 |
| `scripts/run_pipeline.py` | `src/pipeline/cli.py` + `__main__` | 入口 |
| `scripts/reanalyze_with_opend.py` | `src/pipeline/ingest.py` | 合并到数据摄入 |
| `scripts/calc_data_mode_indicators.py` | 删除 | 功能被 `src/indicators/calc.py` 覆盖 |

### 4.5 .gitignore 策略

```gitignore
# 行情数据（可重新拉取）
data/raw/
data/clean/

# 回测产物（可重新生成）
outputs/runs/

# 保留：数据目录、信号、全局索引
# data/catalog.json — 入 git
# outputs/signals/ — 入 git（核心资产）
# outputs/registry.jsonl — 入 git
```

### 4.6 多交易所/多标的扩展

目标标的：BTCUSDT, ETHUSDT, A股(SH.xxx), 美股(US.xxx)

**数据目录按 symbol 分，不按交易所分：**
```
data/clean/BTCUSDT/1h.parquet
data/clean/ETHUSDT/1h.parquet
data/clean/SH.600410/1d.parquet
data/clean/US.AAPL/1d.parquet
```

**原始数据按交易所分（因为 API 响应格式不同）：**
```
data/raw/binance/BTCUSDT/1h/20260327_120000.json
data/raw/futu/SH.600410/1d/20260327.json
data/raw/yahoo/US.AAPL/1d/20260327.json
```

交易所差异在 `ingest.py` 的适配器中消化，clean/ 层对上层完全透明。

### 4.7 信号持久化：对话式分析的核心缺失

#### 问题

用户的日常工作流是在 Claude 对话中触发分析（而非通过 pipeline 脚本）。当前流程：

```
用户: "请用 MCP 拉 BTC 4h+1h K 线，用 Skill 分析"
Claude: → 拉取 K 线数据
       → 计算指标
       → 输出分析报告 + snapshot.json
       → 覆盖写入 analysis_skill_snapshot.json  ← 上一次的分析被销毁
```

每次分析都覆盖同一个文件，**历史分析信号全部丢失**。

#### "观望"也是信号

"观望"结论并非"空白"，它包含完整的可回测信息：

| 字段 | 示例值 | 回测价值 |
|---|---|---|
| 市场结构 | 4h+1h 双降趋势 | 验证结构判断准确率 |
| 阻力/支撑 | R=72000, S=67377 | 验证关键位有效性 |
| 背离信号 | RSI 常规看涨背离 | 验证背离信号可靠性 |
| **条件入场** | 反弹到 70050~70300 转弱做空 | **有明确点位，可回测！** |
| 止损/目标 | SL=70680, T1=68150, T2=67450 | 完整交易方案 |

所以"观望"本质是 **"条件触发的信号"**，跟"立即入场"的区别仅在于多了一个前置条件。

#### 解决方案：Signal Append + Index

```
outputs/signals/{symbol}/
├── index.jsonl                      ← 信号索引（追加写入，一行一条）
├── 20260325_090000/
│   ├── snapshot.json
│   └── report.md
├── 20260326_170000/
│   ├── snapshot.json
│   └── report.md
└── 20260327_120000/
    ├── snapshot.json
    └── report.md
```

**index.jsonl 每行格式：**
```json
{
  "signal_id": "20260326_170000",
  "symbol": "BTCUSDT",
  "timestamp_utc": "2026-03-26T17:00:00Z",
  "price_at_signal": 68987.56,
  "decision": "watch",
  "bias": "bearish",
  "confidence": "medium",
  "playbook": "trend-pullback",
  "conditional_entry": 70050,
  "stop_loss": 70680,
  "t1": 68150,
  "t2": 67450,
  "market_state_4h": "downtrend",
  "market_state_1h": "downtrend",
  "rsi_divergence": "bullish_regular",
  "path": "20260326_170000/"
}
```

**写入规则：**
- 每次分析完成后，**追加**一条到 `index.jsonl`，同时创建新的时间戳目录。
- **永不覆盖**已有信号。
- Skill workflow 的输出钩子负责调用持久化函数。
- `decision=watch` 的信号如果包含 `conditional_entry`，则归类为 **conditional signal**，后续可单独回测"条件是否触发 + 触发后点位是否有效"。

**回测扩展：**
- 现有回测只处理 `decision=long/short`
- 新增 **conditional backtest**：读取 `decision=watch` 且有 `conditional_entry` 的信号，先在 forward bars 中检查条件是否满足，满足后按正常 entry/sl/t1/t2 评分

---

## 5. 回答你的问题

**Q1: 会清理之前模型输出吗？**
不会。`analysis_skill_snapshot.json` + `analysis_skill_report.md` 是核心资产，Phase 1 第一步就是把它们迁移到 `outputs/signals/` 下的独立目录。

**Q2: 回测数据哪些给人看、哪些给机器读？**
现有设计用 human/machine 分目录，但只有 6 个文件，4 层嵌套反而让人找不到。新方案扁平化：
- **人看**：`summary.md`（一页纸总结）、`details.md`（明细表）
- **机器读**：`metrics.json`（统计指标）、`scored.jsonl`（逐 case 评分）、`runs.jsonl`（原始记录）
- **复现用**：`config.json`（参数）、`input.parquet`（数据切片）

都放同一个目录，文件名本身就足够清晰。

**Q3: 历史回测结果？**
现有 3 次回测的 `runs.jsonl` 全是 0 行——没有实际交易记录。可以安全删除，用新结构重新跑。真正有价值的模型信号在 `analysis_skill_snapshot.json`，会保留迁移。

**Q4: 只要有模型输出的点位数据就能重新跑回测？**
是的。回测流程是：K线数据 + 模型信号 → 评分。K线可重新拉取，模型信号是核心资产。所以新方案把信号单独放 `outputs/signals/`，给予最高优先级保护。

---

## 6. 完整数据流图

```
                     ┌──────────────┐
                     │  Binance API │
                     │  Futu OpenD  │
                     │  Yahoo Fin.  │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │   ingest.py  │  拉取 → raw/ → 标准化 → clean/
                     └──────┬───────┘
                            │
                   ┌────────▼────────┐
                   │  data/clean/    │  唯一行情真相
                   │  BTCUSDT/1h.pq  │  （parquet, .gitignore）
                   └───┬────────┬───┘
                       │        │
            ┌──────────▼──┐  ┌──▼──────────────┐
            │  Skill 分析  │  │  Pipeline 回测   │
            │  (对话式)    │  │  (批量)          │
            └──────┬──────┘  └────────┬─────────┘
                   │                  │
         ┌─────────▼────────┐   ┌────▼──────────────┐
         │ outputs/signals/ │   │ outputs/runs/      │
         │ BTCUSDT/         │   │ {run_id}/BTCUSDT/  │
         │  {ts}/           │   │  config.json       │
         │   snapshot.json  │   │  input.parquet     │
         │   report.md      │   │  runs.jsonl        │
         │  index.jsonl     │   │  scored.jsonl      │
         │                  │   │  metrics.json      │
         │  ★ 核心资产      │   │  summary.md        │
         │  ★ 入 git        │   │  details.md        │
         └──────────────────┘   └────────────────────┘
                   │                      │
                   └──────────┬───────────┘
                              │
                    ┌─────────▼──────────┐
                    │ 信号回测引擎       │
                    │ (Phase 5 新增)     │
                    │ 读 signals/ 信号   │
                    │ + clean/ K线       │
                    │ → 逐信号评分       │
                    │ → backtest_report  │
                    └────────────────────┘
```

---

## 7. 迁移计划

### Phase 1：数据整理 + 信号保全（不动代码结构）

1. 创建 `outputs/signals/BTCUSDT/20260326_170000/`
2. 迁移 `analysis_skill_snapshot.json` → `snapshot.json`
3. 迁移 `analysis_skill_report.md` → `report.md`
4. 创建 `index.jsonl`（从 snapshot 提取一行摘要）
5. 转换 `kline_{1h,4h}_accum.csv` → `data/clean/BTCUSDT/{1h,4h}.parquet`
6. 创建 `data/catalog.json`
7. 删除 `data/opend_kline/`, `data/mcp_kline/`, `data/binance_kline/`
8. 更新 `.gitignore`
9. git rm 被追踪的数据文件

### Phase 2：代码重命名（eval/ → src/）

1. 创建 `src/` 目录结构
2. 移动所有 Python 文件到新位置
3. 批量更新 import 路径
4. 更新 tests
5. 验证 `python -m src.pipeline.cli --symbols BTCUSDT` 可运行

### Phase 3：Layout 重构 + Signal Append

1. 重写 `layout.py`：消灭 human/machine/data/debug 四层，改为扁平
2. 重写 `data_source.py` → `catalog.py`：只从 `clean/` 读
3. 新增 `signals.py`：`append_signal()` 追加写入机制
4. manifest.json 改用相对路径
5. 改造 Skill 输出流程，调用 `append_signal()`
6. 端到端测试

### Phase 4：数据摄入标准化

1. 实现 Binance adapter（从 `generate_sample_data.py` 提取）
2. 实现 Futu adapter（从 `reanalyze_with_opend.py` 提取）
3. 实现 Yahoo adapter
4. ingest CLI：`python -m src.pipeline.ingest --source binance --symbol BTCUSDT --interval 1h`
5. 删除旧的 `generate_sample_data.py` 和 `reanalyze_with_opend.py`

### Phase 5：信号回测引擎（新增）

1. 读取 `outputs/signals/{symbol}/index.jsonl` 所有历史信号
2. 对每个信号（含 `decision=watch` 条件单），从 `data/clean/` 切出 forward 窗口
3. 评估：条件是否满足 → 是否命中 SL/T1/T2
4. 输出统计：整体命中率、观望触发率、条件单 vs 即时单胜率
5. 生成信号回测报告到 `outputs/signals/{symbol}/backtest_report.md`

---

## 8. 验收标准

- [ ] `data/clean/` 下每个 symbol 只有 `{interval}.parquet`，无冗余副本
- [ ] `outputs/signals/` 每次分析追加、永不覆盖，历史信号可追溯
- [ ] `outputs/runs/` 每次回测自包含，manifest 只用相对路径
- [ ] 所有 Python 代码在 `src/`，`eval/` 目录不再存在
- [ ] 指标计算只有一份（`src/indicators/calc.py`），其他模块 import
- [ ] 行情数据不入 git（`.gitignore`），信号入 git（核心资产）
- [ ] `python -m src.pipeline.cli --symbols BTCUSDT --interval 1h` 端到端可跑
- [ ] `python -m src.pipeline.ingest --source binance --symbol BTCUSDT --interval 1h` 可拉取写入 clean/
- [ ] 现有 pytest 测试全部通过
