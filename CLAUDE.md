# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## 项目性质

这是一个**纯知识型 Skill**——技术分析的工作流、知识库和策略定义。不含任何代码。

## 目录结构

```
SKILL.md              ← Skill 入口（模式路由、使用规则）
workflows/            ← 分析工作流（图表分析、数据获取、交易决策、输出模板）
references/           ← 知识库（市场结构、价格行为、指标、形态、策略、风险）
strategies/           ← 策略定义 YAML（trend-pullback、breakout-retest、range-reversal）
outputs/signals/      ← 信号归档（核心资产，git 跟踪）
```

## 信号归档

每次技术分析产出交易方案后，必须将信号写入共享数据目录：

```
~/.trading-data/signals/{SYMBOL}/{signal_id}/
  snapshot.json    — 完整分析快照
  report.md        — 人可读报告
~/.trading-data/signals/{SYMBOL}/index.jsonl  — 追加索引
```

## 关联项目

| 项目 | 用途 | 位置 |
|------|------|------|
| stock-skill-backtest | 信号回测验证（Python） | 同级目录 |
| stock-dashboard | 可视化看板（React） | 同级目录 |

三者通过 `~/.trading-data/` 共享数据目录串联。

## 开发约定

- Skill 知识更新时检查 `SKILL.md` 的模式路由表是否需要同步
- 新增 playbook 需同时在 `strategies/` 添加 YAML 和 `references/playbooks/` 添加文档
- 策略 YAML 修改后需通知 stock-skill-backtest 同步副本
