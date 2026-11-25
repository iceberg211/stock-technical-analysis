# Skill 自查优化方案

> 状态：Draft v2 → In Progress | 作者：wei.he + Claude | 日期：2026-04-17
>
> **v2 扩充**：把 stock-skill-backtest 纳入同一方案，修复跨 Skill 契约漂移、命令归属错位、编排错位等三类问题。环境扫描（`2026-04-16-multi-dimension-context-check-design.md`）仍独立，不在此方案。

---

## 1. 背景

对 stock-technical-analysis（以下简称 **analysis**）和 stock-skill-backtest（以下简称 **backtest**）做全量审查后，共发现 7 类 24 个问题。

| 类别 | 范围 | 问题数 | 影响 |
|------|-----|-------|------|
| A. 硬 bug | analysis | 3 | AI 照文档执行会报错或产出不可用结论 |
| B. 内部一致性 | analysis | 2 | AI 输出不稳定、数值打架 |
| C. 设计盲区 | analysis | 2 | 写了规则但 Skill 实际无法执行 |
| D. 次要改进 | analysis | 4 | 不会立即报错，但会累积偏差 |
| E. backtest 自身 | backtest | 3 | 归档策略不一致、模块路由不清 |
| F. 跨 Skill 契约 | 两端 | 5 | schema/字段/yaml/命令归属漂移 |
| G. 编排错位 | 两端 | 1 | daily-review 一份文件跨两个 Skill 能力，易让 AI 错跑 |

**核心判断**：analysis 的问题多数是"写得不完整"（A/C/D）或"写得矛盾"（B）；backtest 的问题是"写得太少"（E）；真正最隐蔽的是两边"各自演化"导致的契约漂移（F），需要两端同步修。

---

## 2. A 类：analysis 硬 bug

### A1. Playbook 清单对不上——有声明，无定义

**现状**：
- `workflows/trading-decision.md` 8.2 和 `output-templates.md` 的 TypeScript schema 声明了 5 个 playbook：
  `trend-pullback / breakout-retest / range-reversal / false-breakout-reversal / flag-wedge-breakout`
- 但 `references/playbooks/` 下只有前 3 个 md，`strategies/` 下只有前 3 个 yaml。
- `references/playbooks/INDEX.md` 里明说后两个 "已内联至 trading-decision.md 8.2，无独立文件"——自知而故意的缺口。

**后果**：
- 假突破反转有一个容易搞错的细节（"止损必须在假突破极值外，不是回调低点"），单靠 8.2 一行字无法完整传达。
- 旗形/楔形突破 的前置 Impulse 判定、形态内部特征，8.2 也覆盖不全。
- 下游 backtest 的 `strategies/` 副本也没有这两个，回测无法覆盖。

**修复**：
- 新增 `references/playbooks/false-breakout-reversal.md`
- 新增 `references/playbooks/flag-wedge-breakout.md`
- 新增 `strategies/false-breakout-reversal.yaml`
- 新增 `strategies/flag-wedge-breakout.yaml`
- 更新 `references/playbooks/INDEX.md`，移除 "已内联" 说明
- 与 F4 绑定：两个新 yaml 同步至 backtest（或迁至共享目录）

### A2. 信号归档是强约束但没有执行工作流

**现状**：
- `SKILL.md` / `CLAUDE.md` / memory 三处都写 "必须归档到 `~/.trading-data/signals/{SYMBOL}/{signal_id}/`"
- 但全仓库没有任何 workflow 解释：signal_id 规则、触发时机、schema、容错。

**消费方契约**（来自 backtest 的 `src/pipeline/signal_writer.py` 与 `signal_loader.py`）：

| 项 | 规则 |
|----|------|
| `signal_id` | `YYYYMMDD_HHMMSS`（基于 `time_utc` 派生，UTC 时区） |
| snapshot 必需字段 | `time_utc / price_now / decision / bias / confidence` |
| snapshot MTF 键 | `"4h"` / `"1h"`（币圈）；A 股需提供 `"1d"` / `"60m"` 且兼容下游读取（见 A2.2） |
| `index.jsonl` 字段 | `signal_id / symbol / timestamp_utc / price_at_signal / market_state_4h / market_state_1h / decision / bias / confidence / playbook / conditional_entry / stop_loss / t1 / t2 / path` |
| 文件结构 | `{SIGNALS_DIR}/{SYMBOL}/{signal_id}/snapshot.json + report.md` + 目录同级 `index.jsonl` |
| 同 id 冲突 | 默认 raise；`overwrite=True` 才允许覆盖（`write_signal` 新路径）；legacy 导入路径走 `append_signal`，自动加 `_001` 后缀——见 E1 |

> **与 F1 联动**：本工作流只写"触发时机 + 如何调用"，**字段权威 schema 放 `references/contracts/signal-snapshot.md`**（由 F1 新增），避免双处维护。

**修复**：
- 新增 `workflows/signal-archival.md`（signal_id 规则、触发条件、冲突处理、A 股字段兼容、快速调用示例）。
- schema 细节由 F1 的契约文件承担。
- `SKILL.md` 模式路由表加一行 "产出交易方案后归档信号 → `workflows/signal-archival.md`"。
- `workflows/trading-decision.md` 在 8.6（回测锚点）之后追加一行 "按 `workflows/signal-archival.md` 归档"。

**A2.1 触发条件**：

| 场景 | 是否归档 |
|------|---------|
| 完整模式 + 有交易方案（decision ∈ {long, short}） | ✅ 必须 |
| 完整模式 + 观望（decision = watch） | ✅ 必须（用于记录 "不做" 的理由，便于 Phase 5 验证） |
| 精简模式（追问、参数微调） | ❌ 不归档（防止重复、ID 冲突） |
| 快问快答（单点问题） | ❌ 不归档 |

**A2.2 A 股字段兼容**：

`index.jsonl` 字段 `market_state_4h / market_state_1h` 是币圈命名。A 股信号（默认 `1D + 60m`）按以下规则填充：
- `market_state_4h` ← HTF 周期状态（A 股填 `1D` 状态）
- `market_state_1h` ← LTF 周期状态（A 股填 `60m` 状态）
- snapshot 内的 MTF 键保留本周期真实名：`snapshot["1d"]`, `snapshot["60m"]`（便于人类阅读）
- A 股场景在 **snapshot.json** 内追加 `htf_interval / ltf_interval` 字段记录真实周期名；**不进 index.jsonl**（受限于 `_build_index_entry` 固定结构，强行改会拉 backtest 下水，见 §6）

> 这是一个**暂时契约**。理想做法是 backtest 端改成 `market_state_htf / market_state_ltf`，双方同步演进。本次方案先不改 backtest 的 index 结构，只在 signal-archival.md + contracts 里说清。

### A3. daily-review.md 调用的是已删除的 pipeline

**现状**：`workflows/daily-review.md` Phase 1 和 Phase 3 仍在跑：

```bash
python3 -m src.pipeline.ingest --source binance ...
python3 -m src --symbols BTCUSDT ...
```

但 commit `af1c167 Drop pipeline & dashboard; make repo Skill-only` 已把 pipeline 从 analysis 删掉。这些命令只能在 **backtest** 仓库里执行，放在本 Skill 里违反 "纯知识 Skill" 定位，且 AI 照抄会让用户报错。

**修复**：与 F5 / G1 联动，改用 Skill 名字引用：
- Phase 1（拉取行情）：说明 "前提：行情数据已就绪在 `~/.trading-data/clean/`；如需刷新，请切换到 **stock-skill-backtest** Skill"。
- Phase 3（历史信号验证）：说明 "切换到 **stock-skill-backtest** Skill，调用其信号回测能力"。
- 移除所有硬编码的 `python3 -m src.xxx` 命令。
- 文件头部标注"**编排型工作流**"（G1），提醒 AI 本文件会跨 Skill 切换。

---

## 3. B 类：analysis 内部一致性

### B1. Pre-trade Checklist 类别和判定规则自相矛盾

**现状**：`pre-trade-checklist.md` 头部声明：

> 软降级项（① HTF 方向、② 位置、⑥ 事件、⑦ 否决理由）：⚠️ 不否决但必须降仓

但 ① 的状态表里写着 "HTF 方向冲突 → ❌ 不做"；② 里写着 "两个关键位中间 → ❌ 等靠近关键位"。**软降级定义 = 不否决，但规则里写了 ❌ 不做**，自相矛盾。

**修复**（两者取其一）：
- 方案 A：把 ① 和 ② 改为 "混合项"——区分不同子状态（冲突 = 硬否决；震荡/中间 = 软降级）。
- 方案 B：把 ① 冲突 和 ② 中间 的 ❌ 改为 "⚠️ 降仓后若 < 25% 则放弃"，保持软降级的纯净定义。

**选定**：方案 A。理由：
- HTF 冲突是强信号（顺大势不逆），不应被降仓规则稀释成 "小仓位搏一把"。
- 明示 "混合项" 比改写成温和警告更诚实。

改完后 ① 和 ② 的规则表保持不变，但**类别定义写明**：

```
① HTF 方向 / ② 位置 = 混合项：子状态 ❌ 仍属硬否决，⚠️ 才按软降级处理
```

### B2. YAML 参数和 playbook md 数值打架

**现状**：
- `_defaults.yaml`：`stop_loss.atr_multiplier: 1.0`
- `trend-pullback.md` / 8.2：止损 buffer = `ATR × 0.3~0.5`
- 两个是不同概念（ATR 基于的整体止损距离 vs. 结构位之外的 buffer），但共存且无说明。T1/T2 同样：YAML 用 ATR 倍数投射，md 用结构位（前高/前低）。

**根因**：README 说 "策略 YAML 修改后需通知 stock-skill-backtest 同步副本"——**YAML 本质是回测参数**，不是 AI 分析的规则。

**修复**：
1. 每个 `strategies/*.yaml` 头部加注释：
   ```yaml
   # 本 YAML 仅供 stock-skill-backtest 回测引擎使用，由简化的 ATR 基准规则表达。
   # AI 分析输出的止损/目标以 references/playbooks/*.md 为权威（基于结构位）。
   # 两者的数值差异是"回测近似 vs 真实结构分析"的必然差距，不是 bug。
   ```
2. `SKILL.md` 知识加载段补充一行：
   > `strategies/*.yaml` 为回测输入参数，AI 分析不读取；AI 以 `references/playbooks/*.md` 为准。
3. `CLAUDE.md` 已有一条 "策略 YAML 修改后需通知 stock-skill-backtest"，补充 "YAML 与 md 允许数值不同，不视为漂移"。
4. 与 F4 联动：如采用共享目录方案，本条第 2/3 款措辞会随之调整。

---

## 4. C 类：analysis 设计盲区

### C1. position-sizing 账户级规则悬空

**现状**：`references/risk/position-sizing.md` 里：
- "连亏 3 笔 → 仓位降至 50%"
- "日最大亏损 3-5% → 当日停止交易"
- "同一品种最多 1 笔持仓"
- "总暴露上限 5%"

**问题**：Skill 是无状态的——每次对话不知道用户的连亏次数、今日 PnL、当前持仓。这些规则永远不会被自发执行。

**修复**：`position-sizing.md` 开头加一段"作用范围"：

```markdown
## 作用范围

本文件规则分两层：
- **单笔计算**（总是可用）：仓位公式、单笔风险上限、降仓规则、R:R 门槛。
- **账户级风控**（需用户提供状态）：连亏处理、日/周熔断、相关性、杠杆限制。

账户级风控依赖 "连亏次数 / 今日 PnL / 当前持仓" 等上下文。当用户未提供时，
AI 只输出单笔仓位建议，并在输出末尾提示 "本建议未纳入账户级风控，请自行叠加"。

如果用户明确说明当前账户状态（如 "今日已亏 2 笔"），AI 必须应用对应规则。
```

### C2. 信号强度 5 分制在数据缺失场景下系统性低估

**现状**：`chart-analysis-workflow.md` Step 5.3：

```
形态成立 +1 | 位置 +1 | 方向 +1 | 指标 +1 | 成交量 +1
总分 ≥ 4 = 强；2~3 = 中；≤ 1 = 弱
```

**问题**：截图模式常无可读指标，A 股常缺 volume。两项一扣最高 3 分，强信号永远打不出来。

**修复**：改为**归一化评分**。修改 Step 5.3 为：

```
每项若"不适用"（如无 volume、截图模式无可读指标）标记为 N/A，不计入分母。

score_ratio = hits / applicable_items

阈值：
  score_ratio ≥ 0.75 = 强（且 applicable_items ≥ 3）
  score_ratio 0.4 ~ 0.75 = 中
  score_ratio < 0.4 = 弱

硬约束：applicable_items < 3 时，信心自动降一档（数据基础薄弱）。
```

示例：
- 3 项可评估，全部命中（3/3 = 1.0，applicable ≥ 3）→ 强
- 5 项可评估，命中 4（4/5 = 0.8）→ 强
- 2 项可评估，全部命中（2/2 = 1.0，但 applicable < 3）→ 中（被硬约束降档）

---

## 5. D 类：analysis 次要改进

### D1. SKILL.md description / routing 补齐

**问题**：description 没提 "复盘 / 持仓巡检 / 信号归档"，导致 daily-review 场景不一定主动触发此 Skill。路由表中 daily-review 行已存在，但缺归档的一行。

**修复**：
- description 末尾加 "定期持仓复盘、信号归档" 两个触发词。
- 路由表**新增一行**：产出交易方案后需归档 → `workflows/signal-archival.md`
- daily-review 行措辞不变（spec v1 写 "改措辞"不准确）。

### D2. Step 6 "无背离" 锚点字段处理

**问题**：Step 6 强制输出 `价格锚点: x->y, 指标锚点: a->b`，但当 divergence = none 时没说锚点怎么填。AI 容易虚构锚点反而误导。

**修复**：Step 6 明确：
- 当 `divergence = none` 时，锚点字段写 `N/A`，不得虚构。
- `output-templates.md` 的 TypeScript schema：`anchor_price: [number, number] | null`，null 表示 N/A。

### D3. 免责声明规则统一

**问题**：
- `SKILL.md` 说 "每次输出含交易分析的回复，末尾必须附加免责声明"
- `output-templates.md` AI 注意事项 15 说 "每次文本输出末尾都要附加免责声明"
- 措辞不同，精简模式/快问快答时要不要加模糊。

**修复**：统一规则写入 SKILL.md：
- 完整模式 + 交易决策卡：**必须**附加免责声明
- 精简模式：若更新涉及价位（入场/止损/目标）→ 附加；若仅澄清概念 → 不必
- 快问快答：一律不附加（避免噪音）

同步更新 `output-templates.md` AI 注意事项第 15 条。

### D4. 清理已过时 memory

**问题**：memory 中 `project_agent_transformation.md` 指向 `docs/superpowers/specs/2026-03-26-stock-agent-design.md`，但该文件不存在（`docs/superpowers/specs/` 下只有本 spec 和 `2026-04-16-multi-dimension-context-check-design.md`）。memory 自身已过期 21 天，方向已从"改造成 Mastra 多 agent"改为"修当前 Skill"。

**修复**：
- 更新 memory：标注 "方向已改为修复当前 Skill，见 `docs/superpowers/specs/2026-04-17-skill-optimization.md`"，或直接删除该 memory。

---

## 6. E 类：backtest Skill 自身

### E1. 归档函数有两套，策略不一致

**现状**：backtest 存在两个归档 API，且 index.jsonl 去重策略不同：

| 函数 | 来源 | signal_id 冲突 | index.jsonl 去重 | 当前用途 |
|------|------|--------------|----------------|---------|
| `signal_writer.write_signal` | `src/pipeline/signal_writer.py` | raise（除非 `overwrite=True`） | 扫描 `existing_ids` 去重 | 新生成信号（推荐 API） |
| `append_signal` | `src/pipeline/signals.py` | 自动加 `_001 / _002` 后缀 | 不去重，直接 append | legacy 导入（`import_legacy_signals`） |

**问题**：
- SKILL.md 只字未提，AI 上手会随机挑一个，容易引入冲突或重复 index 行。
- 两个函数都从 `SIGNALS_DIR` 写，默默产出结构不一致的归档（有的目录带 `_001` 后缀）。

**修复**：
- **规范分工**：新生成信号一律 `write_signal`；只有从旧目录迁入历史分析时才允许 `append_signal`。
- 两个函数的 docstring 顶部互相引用，说明分工。
- backtest `SKILL.md` 新增 "归档 API 选择" 段，默认推荐 `write_signal`。
- 中期计划：`append_signal` 降级为内部函数（`_append_signal_legacy`），外部不再导出——spec v3 再做。

### E2. SKILL.md 模块职责表缺失

**现状**：`SKILL.md` 只讲命令行用法（`python3 -m src.pipeline.ingest`、`python3 -m src`），不讲 `src/` 目录结构。AI 要排查问题时不知道去哪个文件。

**实际模块**：
- `src/pipeline/ingest.py` — 拉行情
- `src/pipeline/signal_writer.py` — 归档信号（新 API）
- `src/pipeline/signal_loader.py` — 读信号（支持 legacy 字段回退）
- `src/pipeline/signals.py` — legacy 归档 API
- `src/pipeline/signal_backtest.py` — 信号重放主逻辑
- `src/pipeline/backtest.py` — 回测入口
- `src/scoring/` — 指标计算
- `src/reporting/` — 报告生成

**修复**：SKILL.md 新增一段"核心模块"表格，列出每个模块的职责、输入输出，以及典型调用链：

```
ingest (行情) → signal_writer (归档) → signal_backtest (重放) → scoring + reporting
                         ↑                      ↓
                   analysis Skill         signal_loader
```

### E3. 缺少 README.md 和 CLAUDE.md

**现状**：backtest 仓库根部只有 `SKILL.md`，没有 `README.md`、没有 `CLAUDE.md`。

**问题**：
- 人类视角：新开发者 clone 仓库后没有入口说明
- AI 视角（别的工具）：Claude Code 之外的 AI 工具（如 Cursor / Codex）不一定读 SKILL.md，但都读 README.md

**修复**：
- 新增最小化 `README.md`（指向 SKILL.md，说明与 analysis skill 的关系）
- 新增 `CLAUDE.md`（开发约定，对应 analysis 的 CLAUDE.md）

> **如果时间紧张，E3 可单独延后**——不阻塞 E1 / E2。

---

## 7. F 类：跨 Skill 契约与协同

### F1. signal snapshot schema 没有单一权威来源

**现状**：三处各自维护：

| 位置 | 性质 | 覆盖度 |
|------|-----|-------|
| `output-templates.md` EvalJSON TS schema | analysis 输出结构 | 完整但嵌套复杂（decision 是 dict） |
| `signal_writer._REQUIRED`（5 字段 tuple） | backtest 最小验证 | 只校验 5 个顶层字段 |
| `signal_loader._extract_signal_meta` | 读端兼容适配 | 吃 dict/str、`conditional_entry`/`entry_price`/`trade.entry_price` 三义 |

**问题**：
- loader 能兼容不同写入格式，但"兼容"掩盖了不一致，让 analysis 一端感觉"随便怎么写都行"
- 新加 playbook 字段值（A1 的 5 种）、新字段（A2.2 的 `htf_interval`）只能靠人脑同步，没文档

**修复**：
- 新增 `references/contracts/signal-snapshot.md`（**在 analysis 仓库，作为单一权威**）
  - 顶层 snapshot schema（JSON Schema 或精简 TS）
  - index.jsonl schema
  - 字段命名规范（规范名 vs 别名，见 F3）
  - 各字段允许的枚举值（含 A1 的 5 个 playbook）
  - A 股兼容规则（对齐 A2.2）
  - **明确标注**：本文件变更需同步修改 `signal_writer.py` / `signal_loader.py`
- analysis `SKILL.md` 和 backtest `SKILL.md` 顶部都加一行 "信号契约见 `analysis/references/contracts/signal-snapshot.md`"
- `workflows/signal-archival.md`（A2 新增）内部引用本契约

### F2. decision 字段写端未做 dict→str 扁平化

**现状**：
- analysis 的 EvalJSON：`decision` 是嵌套 dict（`{action, playbook, checklist, ...}`）
- backtest snapshot 顶层期望：`decision` 是字符串（`"long" | "short" | "watch"`）
- `signal_loader._extract_signal_meta` 读端已做兼容（`isinstance(decision, dict)` 判断）
- `signal_writer._build_index_entry` 写端**没做**，会把 dict 原样塞进 `index.jsonl`

**后果**：`index.jsonl` 的 `decision` 字段可能同时存在 str 和 dict 两种值，下游 `grep`/聚合工具会坏。

**修复**：
- 修改 `signal_writer._build_index_entry`：
  ```python
  decision = snapshot.get("decision")
  if isinstance(decision, dict):
      decision = decision.get("action")
  ```
- 在契约文件（F1）**明确**：归档时 snapshot 顶层 `decision` 必须是 str；如果想保留嵌套结构，放到 snapshot 顶层的 `decision_detail` 字段。
- `workflows/signal-archival.md` 示例代码演示"把 EvalJSON 扁平化成 snapshot"的转换。

### F3. 字段命名三义化

**现状**：`signal_loader._extract_signal_meta` 回退链：

```python
"conditional_entry": snapshot.get("conditional_entry")
                  or snapshot.get("entry_price")
                  or trade.get("entry_price")
```

三个字段名都在活跃使用，loader 不得不打补丁。

**修复**：
- 契约（F1）规定规范名：**`trade.entry_price` / `trade.stop_loss` / `trade.t1` / `trade.t2`**（与 EvalJSON 对齐）。
- `index.jsonl` 保留 `conditional_entry / stop_loss / t1 / t2` 字段名（历史原因，改动涉及回测历史数据），但在契约里标注"index 字段名 ≠ snapshot 字段名"。
- `signal_loader._extract_signal_meta` 保留回退链，但在函数顶部注释 "v2 之后归档应只用规范名；legacy 兼容待 v3 移除"。

### F4. strategies/*.yaml 双仓冗余

**现状**：
- `analysis/strategies/*.yaml` 和 `backtest/strategies/*.yaml` 目前**逐字节一致**（已验证）
- 靠 CLAUDE.md 一句"YAML 修改后需通知 stock-skill-backtest 同步副本"维护
- A1 新增 2 个 yaml 后，两边都要加，漂移风险翻倍

**三个方向**：

| 方案 | 做法 | 代价 | 是否本次落地 |
|------|-----|------|------------|
| A. 共享目录 | yaml 迁至 `~/.trading-data/strategies/`，两端都读 | 需改 backtest `strategy.py` 的读取路径 | 推荐，本次落地 |
| B. backtest 从 analysis 读 | backtest 配置路径指向 `../stock-technical-analysis/strategies/` | 假设相邻目录，CI/其他机器不一定满足 | 不推荐 |
| C. 保留双份 + CI 校验 | 加 `scripts/check_strategies_sync.py`，在 analysis CI 里跑 diff | 简单，但双仓没 CI 时脚本只能手动跑 | 作为 A 的降级 |

**选定**：A 方案。
- 实施：
  - analysis：`strategies/` 目录保留（作为模板），启动时 copy 到 `~/.trading-data/strategies/`（若不存在）
  - backtest：`src/config.py` 新增 `STRATEGIES_DIR = TRADING_DATA_DIR / "strategies"`，`strategy.py` 优先读 `STRATEGIES_DIR`，fallback 到 repo 内
  - A1 的 2 个新 yaml 直接放共享目录
- **如 A 方案实施有阻力**（比如 strategy.py 改动面太大），降级为 C：保留双份 + 加 diff 校验脚本进 analysis 的 `.claude/hooks/`

### F5. 命令归属不清

**现状**：
- `python3 -m src.pipeline.ingest`（拉行情）：backtest `SKILL.md:40` 是权威，analysis `daily-review.md:34` 也在写（要被 A3 删）
- `python3 -m src` / `python3 -m src.pipeline.backtest`（跑回测）：backtest `SKILL.md:46` 是权威，analysis `daily-review.md:81` 也在写（要被 A3 删）

**A3 已删 analysis 这边**，但没写"谁是权威"。

**修复**：
- analysis `SKILL.md` 知识加载段新增一行：
  > 数据拉取、信号回测、历史验证 → 切换到 **stock-skill-backtest** Skill；本 Skill 不执行 `python3 -m src.xxx` 命令。
- backtest `SKILL.md` 顶部新增一行：
  > 技术分析、Playbook 匹配、交易方案输出 → 切换到 **stock-technical-analysis** Skill；本 Skill 不产出分析结论。
- 两边互相"点名"，AI 切换清晰。

---

## 8. G 类：编排错位

### G1. daily-review 一份文件横跨两个 Skill 能力

**现状**：`workflows/daily-review.md` 的四个 Phase 归属：

| Phase | 实际能力归属 | 当前放在 |
|-------|------------|---------|
| Phase 1 拉取行情 | backtest（`ingest.py`） | analysis |
| Phase 2 并行分析 | analysis（chart + trading-decision） | analysis ✅ |
| Phase 3 验证历史信号 | backtest（`signal_backtest.py`） | analysis |
| Phase 4 汇总输出 | analysis（格式化） | analysis ✅ |

**问题**：
- AI 读这份文件时会假设"全在 analysis Skill 里执行"，Phase 1/3 的命令就是这么混进来的（A3 的根因）
- 即使 A3 删了命令改写成"切到 backtest Skill"，文件性质仍是编排型，单 Skill 归属是错的
- 真正的跨 Skill 能力调度没有一级支持（slash command、独立 orchestrator 都没）

**修复**（本次）：
- daily-review.md 文件头部**明确标注**：
  ```markdown
  > **编排型工作流**：本文件按顺序跨两个 Skill 执行。AI 读到本文件时应：
  > 1. 识别每个 Phase 的能力归属（见下方归属表）
  > 2. 在 Phase 开始前切换到对应 Skill
  > 3. Phase 结束后返回本文件推进下一阶段
  ```
- 新增"Phase 能力归属表"（即上面的对照表）
- 每个 Phase 小节首行注明 `> 能力归属：analysis | backtest`

**不在本次做的**（§9）：
- 把 daily-review 抽到独立的编排层（第三个 Skill 或 slash command）
- 写一个 orchestrator Skill 专门处理多 Skill 调度

---

## 9. 不在本方案处理但记下来

| 问题 | 说明 | 处理时机 |
|------|------|---------|
| MTF 知识重复（chart-analysis Step 1.5 vs Step 7） | 三层 MTF 定义写在两处，改动易漂移 | 下一次 workflow 重构 |
| `volume-analysis.md` 日期早于其他 references | 可能未跟上 4 月 15 日大更新 | 单独审查一次 volume 规则 |
| 环境扫描（多维 context check） | 见 `2026-04-16-multi-dimension-context-check-design.md` | 本方案落地 + 1~2 周真实信号数据后评估 |
| backtest index.jsonl 字段 `market_state_4h/1h` 硬编码 | 影响 A 股信号的命名清晰度；A2.2 的 `htf_interval` 字段暂不进 index | 双端同步演进，spec v3 |
| `append_signal` 降级为内部函数 | E1 的中期演进 | spec v3 |
| daily-review 抽到独立编排层 | G1 的中期演进 | spec v3 或更晚 |
| Step 编号 0/0.5/1/1.5/... 叙述不精确 | `output-templates.md:243` 注意事项 2 写 "Step 0~7"，实际有半整数步 | 下次 workflow 重构 |

---

## 10. 文件清单

### 新增（analysis 侧，7 份）

| 路径 | 说明 | 对应任务 |
|------|------|---------|
| `docs/superpowers/specs/2026-04-17-skill-optimization.md` | 本方案 | — |
| `references/playbooks/false-breakout-reversal.md` | A1 | #2 |
| `references/playbooks/flag-wedge-breakout.md` | A1 | #3 |
| `strategies/false-breakout-reversal.yaml` | A1 | #2 |
| `strategies/flag-wedge-breakout.yaml` | A1 | #3 |
| `workflows/signal-archival.md` | A2 | #4 |
| `references/contracts/signal-snapshot.md` | F1（权威契约） | #12 |

### 新增（backtest 侧，2 份）

| 路径 | 说明 | 对应任务 |
|------|------|---------|
| `README.md` | E3（最小化，指向 SKILL.md） | #15 |
| `CLAUDE.md` | E3（开发约定） | #15 |

### 修改（analysis 侧）

| 路径 | 改动 | 对应任务 |
|------|------|---------|
| `references/playbooks/INDEX.md` | 移除 "已内联" 表述，链接到新 playbook | #2/#3 |
| `workflows/daily-review.md` | 移除 pipeline 命令；加编排型标注 + Phase 归属表 | #5 / #G1 |
| `references/checklists/pre-trade-checklist.md` | ① / ② 改为 "混合项"，类目定义修正 | #6 |
| `strategies/_defaults.yaml` 等 4 份 YAML | 顶部加回测专用注释；**如 F4 选 A 方案**：yaml 文件迁至 `~/.trading-data/strategies/`，repo 内保留模板副本 | #7 / #13 |
| `references/risk/position-sizing.md` | 开头加 "作用范围" 段 | #8 |
| `workflows/chart-analysis-workflow.md` | Step 5.3 归一化；Step 6 N/A 说明 | #9 / #11 |
| `workflows/output-templates.md` | 更新 TypeScript schema 与 AI 注意事项 15 | #11 / D3 |
| `SKILL.md` | description + 路由表 + 知识加载段 + 免责声明规则 + 契约引用 + Skill 切换声明 | #10 / F1 / F5 |
| `CLAUDE.md` | YAML 与 md 数值差异说明；yaml 位置变更（若 F4 选 A） | #7 / #13 |

### 修改（backtest 侧）

| 路径 | 改动 | 对应任务 |
|------|------|---------|
| `SKILL.md` | 契约引用（F1）+ 模块职责表（E2）+ 归档 API 选择（E1）+ Skill 切换声明（F5） | #12 / #14 / #16 |
| `src/pipeline/signal_writer.py` | `_build_index_entry` 加 decision dict→str 扁平化 | #12 (F2) |
| `src/pipeline/signal_loader.py` | `_extract_signal_meta` 顶部注释 "v3 移除 legacy 兼容" | #12 (F3) |
| `src/pipeline/signals.py` | `append_signal` docstring 说明"仅用于 legacy 导入" | #14 (E1) |
| `src/config.py` | 新增 `STRATEGIES_DIR`（若 F4 选 A 方案） | #13 |
| `src/pipeline/strategy.py` | 优先读 `STRATEGIES_DIR`，fallback 到 repo 内（若 F4 选 A 方案） | #13 |

### 不动

- `workflows/data-acquisition-workflow.md`
- `workflows/trading-decision.md`（仅 8.6 追加一行归档提示）
- `references/core/*`、`references/patterns/*`、`references/indicators/*`
- `strategies/*.yaml`（仅顶部加注释，不改参数）
- backtest 的 `src/scoring/`、`src/reporting/`、`src/indicators/`、`tests/`

---

## 11. 落地顺序

按依赖拓扑而非类别顺序：

1. **F1 契约文件先行**（analysis/references/contracts/signal-snapshot.md）——A2、F2、F3、E2 都依赖它
2. **A 类硬 bug**：
   - A1 补 2 个 playbook + 2 个 yaml
   - A2 建 signal-archival workflow（引用 F1）
   - A3 修 daily-review（联动 G1 的编排标注）
3. **F 类契约同步**：
   - F2 写端扁平化（小改）
   - F3 loader 兼容注释
   - F5 两边 SKILL.md 加 Skill 切换声明
4. **F4 yaml 共享目录**（若选 A 方案，改动面较大，单独落）
5. **B/C 类一致性与盲区**：B1 checklist、B2 yaml 注释、C1 作用范围、C2 归一化
6. **E 类 backtest 自身**：E1 归档 API 分工、E2 模块表、E3 README/CLAUDE
7. **G1 daily-review 编排标注**（与 A3 合并提交亦可）
8. **D 类次要改进**：SKILL.md / Step 6 / 免责声明 / memory 清理
9. 两仓一次性提交，同步文档；A1 的 2 个新 yaml 跟着 F4 方案落在共享目录

> **拆 PR 建议**：analysis 和 backtest 两个仓库可以分别提 PR，但 A2 / F1 / F2 需要两仓的改动配套（analysis 发契约、backtest 按契约改 writer），先合 analysis 再合 backtest。

## 12. 验收

### analysis 侧

- [ ] 5 个 playbook md 和 5 个 yaml 都存在且完整
- [ ] `references/contracts/signal-snapshot.md` 存在，覆盖 snapshot schema + index.jsonl schema + A 股兼容 + 字段规范名
- [ ] `workflows/signal-archival.md` 内容引用契约文件，不自行维护字段清单
- [ ] `workflows/daily-review.md` 无 `python3 -m src.xxx` 字样；文件头有"编排型工作流"标注；每个 Phase 有归属行
- [ ] `pre-trade-checklist.md` ①/② 的类目与规则一致
- [ ] `strategies/*.yaml` 每份都有 "仅回测专用" 注释；若 F4 选 A，共享目录有对应 yaml
- [ ] `position-sizing.md` 有 "作用范围" 段
- [ ] chart-analysis Step 5.3 用 score_ratio，不是绝对 5 分
- [ ] chart-analysis Step 6 有 divergence=none 时填 N/A 的说明
- [ ] `SKILL.md` description 提 "复盘 / 归档"
- [ ] `SKILL.md` 知识加载段/顶部有"数据拉取/回测 → 切换到 backtest"的 Skill 切换声明
- [ ] memory `project_agent_transformation.md` 指向的文件存在或 memory 已更新

### backtest 侧

- [ ] `SKILL.md` 有模块职责表、归档 API 选择段、契约引用、Skill 切换声明
- [ ] `SKILL.md` 说清 `write_signal` vs `append_signal` 的适用场景
- [ ] `signal_writer._build_index_entry` 对 `decision` 字段做 dict→str 扁平化
- [ ] `index.jsonl` 中 `decision` 字段仅含字符串（抽查最近 20 条）
- [ ] `signal_loader._extract_signal_meta` 顶部有 "v3 移除 legacy 兼容" 注释
- [ ] 若 F4 选 A 方案：`STRATEGIES_DIR` 配置生效，`strategy.py` 能从共享目录读策略
- [ ] `README.md` 和 `CLAUDE.md` 存在（E3，非阻塞项）

### 跨 Skill 一致性

- [ ] analysis 和 backtest 两边 SKILL.md 都引用 `references/contracts/signal-snapshot.md`
- [ ] 两边 SKILL.md 都有"本 Skill 不做 XXX，切换到另一 Skill" 的声明
- [ ] 命令行指令（`python3 -m src.xxx`）只在 backtest SKILL.md 出现
- [ ] 两仓 `strategies/*.yaml` 在 F4 落地后逐字节一致（或由共享目录统一）
