# CLAUDE.md

This file provides guidance to AI agents working with this repository.

## 项目性质与唯一真源

本仓库是交易与技术分析 AI 技能套件的**唯一真源（Single Source of Truth）**，采用 Monorepo 结构统一纳管交易核心能力链条。通过 `~/.agents/skills/` 软链接挂载，供 Codex / Gemini / Antigravity / Claude Code 等智能体平台共同加载使用。

## 技能生态与职责分工

| Skill 目录 | 职责范围 | 输入/依赖 | 关键产出 |
|---|---|---|---|
| `skills/market-data` | 无缓存、确定性多市场 OHLCV 抓取、清洗、完整性切分与指标预计算 | 标的代码/市场/周期 | 结构化行情事实与预计算指标 JSON |
| `skills/stock-technical-analysis` | 通用市场结构（HH/HL/BOS/CHoCH）、关键位、量价背离、形态与通用 Playbook | 行情快照 / K线图 | 结构化技术分析与通用交易计划 |
| `skills/price-action-decision` | Al Brooks 价格行为独立平级分析器（Always In / 周期 / 最佳动作） | 行情事实与微结构 | Brooks 价格行为分析与执行计划 |
| `skills/trade-risk` | 交易仓位计算、逻辑止损校验与组合风险管理 | 已确认交易计划与账户约束 | 确定性仓位大小与风险计划 |

## 目录结构

```text
skills/
├── market-data/               ← 行情与指标底座（含多市场直连与预计算脚本）
├── stock-technical-analysis/  ← 通用技术分析（工作流、Playbook、形态与指标库）
├── price-action-decision/     ← Al Brooks 价格行为决策器（基于阿布核心课体系）
└── trade-risk/                ← 仓位与风险管理规范
docs/                          ← 架构演进与多维决策设计规范
tests/                         ← 全套件集成与契约测试入口
```

## 开发与协作约定

1. **职责单一化**：
   - 不要在分析层技能（`stock-technical-analysis` / `price-action-decision`）中重新引入网络爬虫或抓取代码；行情与指标预计算统一归 `$market-data`。
   - 不要在分析层固定写死账户风险比例或硬编码固定手数；仓位计算统一委托 `$trade-risk`。
2. **测试与回归**：
   - 任何改动后需运行套件测试，确保各技能契约完整：
     - `python3 tests/run_all_tests.py`
3. **软链接同步**：
   - 全局运行环境通过 `~/.agents/skills/{skill-name}` 指向本仓库对应子目录，修改即生效，无需手工多处复制。
