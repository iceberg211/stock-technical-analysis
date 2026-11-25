# 交易剧本索引 (Playbooks Index)

> **Playbook = 一套完整的入场规则。不在 Playbook 里的交易，不做。**

| Playbook | 适用场景 | 执行规则位置 |
|----------|---------|------------|
| **顺势回调** `trend-pullback` | 明确趋势 + 健康回调 | `trend-pullback.md`（详细）/ `trading-decision.md 8.2`（快速） |
| **突破回踩** `breakout-retest` | 关键位被有效突破 | `breakout-retest.md`（详细）/ `trading-decision.md 8.2`（快速） |
| **区间反转** `range-reversal` | 成熟震荡区间边缘 | `range-reversal.md`（详细）/ `trading-decision.md 8.2`（快速） |
| **假突破反转** `false-breakout-reversal` | 关键位被穿后快速收回 | ✅ **已内联至 `trading-decision.md 8.2`**，无独立文件 |
| **旗形/楔形突破** `flag-wedge-breakout` | 趋势中继形态突破 | ✅ **已内联至 `trading-decision.md 8.2`**，无独立文件 |

不匹配任何 Playbook → 输出"当前不满足任何已定义 setup，建议观望"

匹配后，还需通过 `checklists/pre-trade-checklist.md` 的最终过滤才能输出方案
