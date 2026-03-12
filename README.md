# stock-technical-analysis

面向多 AI Agent 复用的 `stock-technical-analysis` Skill 仓库。

该仓库采用“**单 Skill 仓库**”标准布局：仓库根目录就是 Skill 本体，便于被不同 Agent 平台直接读取或分发。

## Standard Layout

```text
stock-technical-analysis/
├── SKILL.md                    # 必需：触发描述 + 核心工作流入口
├── agents/                     # 推荐：平台 UI 元数据
│   └── openai.yaml
├── workflows/                  # 推荐：主工作流（高频执行）
│   └── chart-analysis-workflow.md
├── references/                 # 可选：按需加载的详细知识库
│   ├── core/
│   ├── patterns/
│   ├── indicators/
│   ├── playbooks/
│   ├── checklists/
│   └── risk/
├── scripts/                    # 可选：确定性脚本（当前可按需新增）
└── assets/                     # 可选：模板/静态资源（当前可按需新增）
```

## Design Principles

- `SKILL.md` 只保留高价值指令和触发语义，避免冗长背景描述。
- 高频规则优先内嵌在 `workflows/`，降低 Agent 机械读取大量 references 的成本。
- `references/` 只放边界情况、复杂定义、扩展知识，按需读取。
- 目录保持一层可见、可预期，避免深层嵌套导致可移植性下降。

## Use With Different AI Agents

### Codex / 类 Codex Agent

将本仓库作为 skill 根目录使用，或复制到：

- `$CODEX_HOME/skills/stock-technical-analysis`

### 通用 Agent（自定义 Skill Loader）

最小可用集合：

1. `SKILL.md`
2. `workflows/`
3. `references/`（可选但建议）

解析规则建议：

1. 先读 `SKILL.md` frontmatter (`name` + `description`)
2. 再按 `SKILL.md` 指引加载 workflow
3. 最后按需读取 references

## Maintenance Guide

- 将仓库根目录视为单一事实源（single source of truth）。
- 变更 workflow 时，优先保持向后兼容，不随意改动关键输出字段名。
- 新增脚本时放入 `scripts/` 并附最小可运行示例。

## Current Scope

当前版本聚焦：

- 图表与行情数据驱动分析
- 多时间框架联动
- 条件式交易计划与风险控制

不包含：

- 交易日志与复盘数据目录（已从 skill 仓库剥离）
