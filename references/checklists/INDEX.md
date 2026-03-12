# 执行检查单索引 (Checklists Index)

> **分析完成≠可以交易。检查单是"分析"和"入场"之间的最后一道门。**

---

## 检查单一览

| 检查单 | 使用时机 | 核心作用 | 文件 |
|--------|---------|---------|------|
| **入场前检查** | 匹配 Playbook 后、入场前 | 最后过滤：过滤掉不该做的交易 | `pre-trade-checklist.md` |
| **持仓管理** | 入场后、持仓中 | 管理规则：什么时候动止损、减仓、离场 | `in-trade-management.md` |

---

## 使用流程

```
Step 7 综合研判
  │
  ├── 匹配 Playbook（playbooks/INDEX.md）
  │     │
  │     └── 通过 Playbook 的入场条件
  │           │
  │           └── 📋 pre-trade-checklist.md ← 最后过滤
  │                 │
  │                 ├── 全部 ✅ → 入场
  │                 │       │
  │                 │       └── 📋 in-trade-management.md ← 持仓管理
  │                 │
  │                 └── 任一 ❌ → 不做
  │
  └── 不匹配任何 Playbook → 观望
```

---

## AI 使用指引

- 每次给出交易方案（chart-analysis-workflow Step 8）前，**必须**先跑一遍 `pre-trade-checklist.md`
- 入场后如果用户问持仓管理问题，加载 `in-trade-management.md`
- 检查单中的每一项都是硬性规则，不能跳过或"差不多就行"
